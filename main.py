from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, Request
import openai
import os
import json
import re
from matcher import match_studies
from utils import format_matches_for_gpt
from push_to_monday import push_to_monday
from datetime import datetime
from geopy.geocoders import GoogleV3

openai.api_key = os.getenv("OPENAI_API_KEY")

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

geolocator = GoogleV3(api_key=os.getenv("GOOGLE_MAPS_API_KEY"))

SYSTEM_PROMPT = """You are a clinical trial assistant named Hey Hope. Ask the user one friendly question at a time to collect the following information:

- Full Name
- Email Address
- Phone Number
- City
- State
- ZIP Code
- Best Time to Reach You
- Can we contact you via text message?
- Date of birth (e.g., March 14, 1992)
- Gender Identity
- Race / Ethnicity
- Are you a U.S. Veteran?
- Are you Native American or identify as Indigenous?
- Do you have health insurance?
- Are you currently receiving any form of mental health care?
- Have you ever been diagnosed with any of the following? Depression, Anxiety, PTSD, Other, or None
- Have you ever tried SSRIs or antidepressants?
- Have you ever been diagnosed with bipolar disorder?
- Do you currently have high blood pressure that is not medically managed?
- Have you used ketamine recreationally?
- Are you currently pregnant or breastfeeding? (only if applicable)
- Are you open to remote or at-home participation options?
- Are you willing to participate in brief screening calls?
- Preferred participation format: In-person / Remote / No preference
- Do you speak a language other than English at home?
- Are you open to future studies?
- Anything else you'd like us to know?

💬 Say “Thanks for that!” after each response. Be friendly and conversational.
❌ Do NOT summarize or repeat back responses.
✅ Once all information is collected, return ONLY a single JSON object with all fields.
"""

chat_histories = {}
river_pending_confirmation = {}
last_participant_data = {}

def calculate_age(dob_str):
    try:
        dob = datetime.strptime(dob_str, "%B %d, %Y")
        today = datetime.today()
        return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    except Exception as e:
        print("⚠️ Error parsing date of birth:", dob_str, "→", str(e))
        return None

def contains_red_flag(text):
    text = text.lower()
    red_flags = ["kill myself", "end my life", "can’t do this anymore", "suicidal", "want to die"]
    return any(flag in text for flag in red_flags)

def get_coordinates(city, state, zip_code):
    try:
        query = f"{city}, {state} {zip_code}".strip()
        loc = geolocator.geocode(query)
        if loc:
            return (loc.latitude, loc.longitude)
    except Exception as e:
        print("⚠️ Failed to geocode location:", query, "→", str(e))
    return None

def is_eligible_for_river(participant):
    age = participant.get("age")
    state = participant.get("state", "").strip().upper()
    diagnosis = (participant.get("diagnosis_history") or "").lower()
    
    return (
        age is not None and 21 <= age <= 75 and
        state in ["CA", "MT"] and
        any(cond in diagnosis for cond in ["depression", "anxiety", "ptsd"]) and
        participant.get("bipolar", "").strip().lower() == "no" and
        participant.get("blood_pressure", "").strip().lower() not in ["yes", "unsure"] and
        participant.get("ketamine_use", "").strip().lower() != "yes"
    )

@app.post("/chat")
async def chat_handler(request: Request):
    body = await request.json()
    session_id = body.get("session_id", "default")
    user_input = body.get("message")

    if contains_red_flag(user_input):
        return {"reply": "🚨 If you’re in immediate danger, call 911 or contact the 988 Suicide & Crisis Lifeline."}

    if user_input.strip().lower() in ["other options", "other studies", "more studies"]:
        if session_id in last_participant_data:
            with open("indexed_studies_with_coords.json", "r") as f:
                all_studies = json.load(f)
            other_matches = match_studies(last_participant_data[session_id], all_studies, exclude_river=True)
            return {"reply": format_matches_for_gpt(other_matches)}
        else:
            return {"reply": "I don’t have your previous info handy. Please start again to explore more study options."}

    if session_id in river_pending_confirmation:
        if user_input.strip().lower() in ["yes", "y", "yeah", "sure"]:
            participant_data = river_pending_confirmation.pop(session_id)
            participant_data["rivers_match"] = True
            push_to_monday(participant_data)
            last_participant_data[session_id] = participant_data
            return {"reply": "✅ Great! You've been submitted to the River Program. You'll be contacted shortly.\n\nType 'other options' to explore more studies."}
        elif user_input.strip().lower() in ["no", "n", "not interested"]:
            participant_data = river_pending_confirmation.pop(session_id)
            push_to_monday(participant_data)
            last_participant_data[session_id] = participant_data
            with open("indexed_studies_with_coords.json", "r") as f:
                all_studies = json.load(f)
            other_matches = match_studies(participant_data, all_studies, exclude_river=True)
            return {"reply": format_matches_for_gpt(other_matches)}
        else:
            return {"reply": "Just to confirm — would you like to apply to the River Program? Yes or No?"}

    if session_id not in chat_histories:
        chat_histories[session_id] = [{"role": "system", "content": SYSTEM_PROMPT}]

    chat_histories[session_id].append({"role": "user", "content": user_input})

    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=chat_histories[session_id],
        temperature=0.5
    )

    gpt_message = response.choices[0].message["content"]
    chat_histories[session_id].append({"role": "assistant", "content": gpt_message})

    match = re.search(r'{[\s\S]*}', gpt_message)
    if match:
        try:
            participant_data = json.loads(match.group())

            dob_value = next((participant_data.get(k) for k in ["dob", "Date of birth"] if participant_data.get(k)), "")
            participant_data["age"] = calculate_age(dob_value)
            participant_data["dob"] = dob_value

            city = participant_data.get("city") or participant_data.get("City", "")
            state = participant_data.get("state") or participant_data.get("State", "")
            zip_code = participant_data.get("zip") or participant_data.get("ZIP Code", "")
            participant_data["location"] = f"{city}, {state}"
            participant_data["city"] = city
            participant_data["state"] = state
            participant_data["zip"] = zip_code
            participant_data["coordinates"] = get_coordinates(city, state, zip_code)

            diagnosis = participant_data.get("Have you ever been diagnosed with any of the following?")
            participant_data["diagnosis_history"] = ", ".join(diagnosis) if isinstance(diagnosis, list) else diagnosis or ""

            participant_data["bipolar"] = next((v for k, v in participant_data.items() if k.lower() == "have you ever been diagnosed with bipolar disorder?"), "")
            participant_data["blood_pressure"] = next((v for k, v in participant_data.items() if k.lower() == "do you currently have high blood pressure that is not medically managed?"), "")
            participant_data["ketamine_use"] = next((v for k, v in participant_data.items() if k.lower() == "have you used ketamine recreationally in the past?"), "")
            participant_data["gender"] = next((v for k, v in participant_data.items() if k.lower() == "gender identity"), "")

            with open("indexed_studies_with_coords.json", "r") as f:
                all_studies = json.load(f)

            required_fields = ["dob", "city", "state", "zip", "diagnosis_history", "age", "gender"]
            if any(not participant_data.get(k) for k in required_fields):
                return {"reply": "Thanks! I’ve saved your info so far. Let’s keep going — I still need a few more details before I can match you to studies."}

            matches = match_studies(participant_data, all_studies)

            if not matches:
                push_to_monday(participant_data)
                last_participant_data[session_id] = participant_data
                return {"reply": "😕 I couldn’t find any matches at the moment, but your info has been saved. We’ll reach out when a good study comes up."}

            for m in matches:
                if "river" in m.get("study_title", "").lower() and is_eligible_for_river(participant_data):
                    river_pending_confirmation[session_id] = participant_data
                    return {"reply": (
                        "🌊 You've been matched to our **River Program** for affordable at-home ketamine therapy with telehealth support.\n\n"
                        "Would you like to apply now?"
                    )}

            push_to_monday(participant_data)
            last_participant_data[session_id] = participant_data
            return {"reply": format_matches_for_gpt(matches)}

        except Exception as e:
            print("❌ Exception while processing match:", str(e))
            return {"reply": "We encountered an error processing your info."}

    return {"reply": gpt_message}
