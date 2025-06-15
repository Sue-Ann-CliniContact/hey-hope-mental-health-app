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

SYSTEM_PROMPT = """You are a clinical trial assistant named Hey Hope. Ask the user one friendly question at a time to collect the following information to help match them to research studies for mental health.

Start with general mental health questions, then proceed to personal and logistical questions. If the user is located in California or Montana, is between 21–75 years old, and has depression, anxiety, or PTSD, then include the River Program follow-up section.

---

### 🧠 Mental Health & Diagnosis
- What brings you here today? (Optional)
- Do you experience depression, anxiety, PTSD, or any other mental health condition?
- Have you been officially diagnosed by a healthcare provider?
- Are you currently receiving any form of treatment or therapy?
- Are you currently taking any medication for your condition? If so, which ones?
- Have you ever tried ketamine therapy?
- How long have you been experiencing these symptoms?

---

### 👤 Personal Details
- What is your full name?
- What is your date of birth? (e.g., June 20, 1990)
- What is your gender identity?
- Are you currently pregnant or breastfeeding? (only if applicable)
- What is your race / ethnicity?
- Are you a U.S. Veteran?
- Do you identify as Native American or Indigenous?
- What city and state do you live in?
- What is your ZIP code?
- What is your current profession or field of work?

---

### 📞 Contact & Participation Preferences
- What is your email address?
- What is your phone number?
- Can we contact you via text message?
- What is the best time to reach you?
- Do you prefer in-person or remote participation?
- Do you have access to a computer, phone, or internet for telehealth?
- Are you open to participating in brief screening calls?
- Do you speak a language other than English at home?
- Are you open to future studies?
- Is there anything else you’d like us to know?

---

### 🌊 River Program Follow-Up (Ask only if eligible by Age + State + Diagnosis)
> “Thanks — based on what you’ve shared, you may be eligible for our River Program for ketamine therapy. I’ll ask a few follow-up questions to check your eligibility.”

- Have you ever been diagnosed with bipolar disorder?
- Do you currently have high blood pressure that is not medically managed?
- Have you used ketamine recreationally?
- Are you currently pregnant or breastfeeding? (ask again only if applicable)

---

💬 After each user reply, say something encouraging like “Thanks for that” or “Got it!” to keep it conversational.
❌ Do NOT summarize or repeat back their answers.
✅ Once all answers are collected, return a single JSON object with all fields.

If the user gives an unclear answer, gently rephrase the question and ask again.
If a response isn’t formatted correctly (e.g. wrong date format), clarify and retry.
"""

chat_histories = {}
river_pending_confirmation = {}
last_participant_data = {}

US_STATES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY", "district of columbia": "DC"
}

def normalize_state(state_input):
    s = state_input.strip().lower()
    return US_STATES.get(s, state_input.upper())

def normalize_phone(phone):
    digits = re.sub(r"\D", "", phone)
    if not digits.startswith("1"):
        digits = "1" + digits
    return "+" + digits

def calculate_age(dob_str):
    if not dob_str.strip():
        return None
    formats = [
        "%B %d, %Y", "%b %d, %Y", "%m/%d/%Y", "%m/%d/%y", 
        "%d %B %Y", "%d %b %Y", "%Y-%m-%d", "%d-%m-%Y"
    ]
    for fmt in formats:
        try:
            dob = datetime.strptime(dob_str.strip(), fmt)
            today = datetime.today()
            return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        except ValueError:
            continue
    print("⚠️ Unrecognized DOB format:", dob_str)
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

def flatten_dict(d, parent_key='', sep=' - '):
    items = {}
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.update(flatten_dict(v, new_key, sep=sep))
        else:
            items[new_key] = v
    return items

def normalize_participant_data(raw):
    key_map = {k.lower(): k for k in raw}

    def get_any(*keys):
        for key in keys:
            match = next((raw[v] for k, v in key_map.items() if key.lower() in k), None)
            if match:
                return match
        return ""

    raw["dob"] = raw.get("dob") or get_any("date of birth")
    raw["city"] = raw.get("city") or get_any("city")
    raw["state"] = normalize_state(raw.get("state") or get_any("state"))
    raw["zip"] = raw.get("zip") or get_any("zip code")
    raw["gender"] = raw.get("gender") or get_any("gender identity")
    raw["phone"] = normalize_phone(raw.get("phone") or get_any("phone number", "mobile"))

    raw["diagnosis_history"] = raw.get("diagnosis_history") or get_any("diagnosed with any of the following", "mental health conditions")
    if isinstance(raw["diagnosis_history"], list):
        raw["diagnosis_history"] = ", ".join(raw["diagnosis_history"])

    raw["age"] = calculate_age(raw["dob"])
    raw["location"] = f"{raw['city']}, {raw['state']}"
    raw["coordinates"] = get_coordinates(raw["city"], raw["state"], raw["zip"])

    raw["bipolar"] = raw.get("bipolar") or get_any("bipolar disorder")
    raw["blood_pressure"] = raw.get("blood_pressure") or get_any("high blood pressure")
    raw["ketamine_use"] = raw.get("ketamine_use") or get_any("ketamine recreationally")

    if raw.get("gender", "").lower() == "male":
        raw["pregnant"] = "No"

    return raw

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
            raw_json = match.group()
            print("🔍 Raw JSON extracted:", raw_json)

            flattened_raw = flatten_dict(json.loads(raw_json))
            participant_data = normalize_participant_data(flattened_raw)

            required_fields = ["dob", "city", "state", "zip", "diagnosis_history", "age", "gender"]
            missing_fields = [k for k in required_fields if not participant_data.get(k)]
            if missing_fields:
                print("⚠️ Missing fields:", missing_fields)
                return {"reply": "Thanks! I’ve saved your info so far. Let’s keep going — I still need a few more details before I can match you to studies."}

            # RIVER CHECK FIRST
            if is_eligible_for_river(participant_data):
                river_pending_confirmation[session_id] = participant_data
                return {"reply": (
                    "🌊 You've been matched to our **River Program** for at-home ketamine therapy via telehealth, designed for individuals with depression, PTSD, or anxiety.\n\n"
                    "Would you like to apply now? (Yes or No)"
                )}

            with open("indexed_studies_with_coords.json", "r") as f:
                all_studies = json.load(f)

            matches = match_studies(participant_data, all_studies)

            if not matches:
                last_participant_data[session_id] = participant_data
                push_to_monday(participant_data)
                return {"reply": "😕 I couldn’t find any matches at the moment, but your info has been saved. We’ll reach out when a good study comes up."}

            push_to_monday(participant_data)
            last_participant_data[session_id] = participant_data
            return {"reply": format_matches_for_gpt(matches)}

        except Exception as e:
            print("❌ Exception while processing GPT match JSON:", str(e))
            print("📨 GPT message was:", gpt_message)
            return {"reply": "We encountered an error processing your info. Please try again or contact support."}

    return {"reply": gpt_message}
