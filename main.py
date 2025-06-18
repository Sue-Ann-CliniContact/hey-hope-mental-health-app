from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, Request
import openai
import os
import json
import re
from matcher import match_studies
from utils import flatten_dict, normalize_gender, format_matches_for_gpt
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

SYSTEM_PROMPT = """You are a clinical trial assistant named Hey Hope.

You must collect the following fields before proceeding to matching:
- Name
- Email
- Phone number
- Date of birth
- Gender
- ZIP code
- Main mental health conditions (e.g. depression, PTSD, anxiety)

After collecting just those fields, stop and return ONLY a JSON object with those values. Do NOT ask follow-up questions yet.

❗️Important rules:
- Always return ONLY a JSON object with those fields.
- DO NOT return natural language, greetings, summaries, or follow-up questions.
- DO NOT include any lists of study titles or explanations.
- DO NOT include "Thanks", "Got it", or "Here's what I found".
- If the user message already contains all required fields, extract them and return them immediately as a JSON object.

✅ Example output:
{
  "Name": "Jane Doe",
  "Email": "jane@example.com",
  "Phone number": "(555) 123-4567",
  "Date of birth": "March 10, 1990",
  "Gender": "Female",
  "ZIP code": "94110",
  "Conditions": ["Depression", "PTSD"]
}

Return a broad list of studies (10–20), including the River Program if eligible.

Then, ask smart follow-up questions (e.g. about bipolar, pregnancy, cancer, etc.) based on what's needed to confirm matches from that list. Never ask all questions upfront.

Once enough information is gathered, return a structured JSON object of their info.

After each user reply, say “Got it!” or “Thanks!” to keep it conversational. Do not summarize their answers or repeat them back.

Follow-up rules:
- Ask about bipolar only if a study excludes it.
- Ask about gender-specific requirements only if needed.
- If eligible, ask River Program follow-ups.

Important: Do NOT include any introductory or summary text in your replies. Only return a JSON object.
Always return only a JSON object with participant answers. Do NOT return any lists of study titles or commentary.
"""

chat_histories = {}
river_pending_confirmation = {}
last_participant_data = {}
study_selection_stage = {}

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
    raw["phone"] = normalize_phone(raw.get("phone") or get_any("phone number"))
    raw["zip"] = raw.get("zip") or get_any("zip", "zip code")

    raw_gender = raw.get("gender") or get_any("gender", "gender identity")
    raw["gender"] = normalize_gender(raw_gender)

    raw["city"] = raw.get("city") or get_any("city")
    raw["state"] = normalize_state(raw.get("state") or get_any("state"))

    if (not raw["city"] or not raw["state"]) and raw.get("zip"):
        try:
            loc = geolocator.geocode(raw["zip"])
            if loc and hasattr(loc, 'raw'):
                address = loc.raw.get("address", {})
                raw["city"] = raw["city"] or address.get("city") or address.get("town") or address.get("village")
                raw["state"] = raw["state"] or normalize_state(address.get("state", ""))
        except Exception as e:
            print("⚠️ ZIP enrichment failed:", e)

    raw["city"] = raw.get("city") or "Unknown"
    raw["state"] = raw.get("state") or "Unknown"
    raw["location"] = f"{raw['city']}, {raw['state']}"

    conds = raw.get("diagnosis_history") or get_any("diagnosed with", "mental health conditions", "conditions")
    raw["diagnosis_history"] = ", ".join(conds) if isinstance(conds, list) else conds

    raw["age"] = calculate_age(raw["dob"])
    raw["coordinates"] = get_coordinates(raw["city"], raw["state"], raw["zip"])

    raw["bipolar"] = raw.get("bipolar") or get_any("bipolar disorder")
    raw["blood_pressure"] = raw.get("blood_pressure") or get_any("high blood pressure")
    raw["ketamine_use"] = raw.get("ketamine_use") or get_any("ketamine therapy", "ketamine use")

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

    # ✅ If River follow-up confirmation is expected
    if session_id in river_pending_confirmation and user_input.strip().lower() in ["yes", "yeah", "sure"]:
        river_qs = [
            "Have you been diagnosed with bipolar II disorder?",
            "Do you have uncontrolled high blood pressure?",
            "Have you used ketamine recreationally in the past?"
        ]
        study_selection_stage.pop(session_id, None)
        return {
            "reply": (
                "Great! To confirm your eligibility for the River Program, please answer the following:\n\n- " +
                "\n- ".join(river_qs)
            )
        }

    # ✅ Handle multi-selection of study matches (e.g., "1, 11")
    if session_id in study_selection_stage:
        matches = study_selection_stage[session_id]["matches"]
        input_text = user_input.strip().lower()
        selected = []

        for i, m in enumerate(matches, 1):
            if str(i) in input_text or m["study"].get("study_title", "").lower() in input_text:
                selected.append(m)

        if not selected:
            return {"reply": "❓ I didn’t catch which study you meant. Can you tell me the number or name again?"}

        questions = []
        tag_question_map = {
            "require_female": "Are you female?",
            "require_male": "Are you male?",
            "require_bipolar": "Have you been diagnosed with bipolar disorder?",
            "require_diabetes": "Do you have diabetes?",
            "exclude_bipolar": "Have you been diagnosed with bipolar disorder (this study may exclude it)?",
            "exclude_pregnant": "Are you currently pregnant or breastfeeding?",
            "require_veteran": "Are you a U.S. military veteran?"
        }

        river_included = False
        for match in selected:
            title = match["study"].get("study_title", "Untitled Study")
            tags = match["study"].get("tags", [])
            q_set = [tag_question_map[tag] for tag in tags if tag in tag_question_map]
            if q_set:
                questions.append(f"📝 For **{title}**:\n- " + "\n- ".join(q_set))
            if "river" in title.lower():
                river_included = True

        if river_included:
            river_pending_confirmation[session_id] = last_participant_data.get(session_id, {})
            return {
                "reply": (
                    "🌊 Great choice! The River Program offers at-home ketamine therapy via telehealth.\n\n"
                    "**Would you like to continue with this one? (Yes or No)**"
                )
            }

        del study_selection_stage[session_id]
        return {
            "reply": (
                "Great choice! Just a few quick questions to confirm your fit for these studies:\n\n"
                + "\n\n".join(questions)
            )
        }

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
    if not match or not gpt_message.strip().startswith("{"):
        return {
            "reply": (
                "⚠️ I expected a structured summary of your answers so I can match you to studies. "
                "Please start again or type your details directly."
            )
        }

    try:
        raw_json = match.group()
        print("🔍 Raw JSON extracted:", raw_json)

        # ✅ Special handler if this is a River follow-up
        if session_id in river_pending_confirmation:
            try:
                river_answers = flatten_dict(json.loads(raw_json))
                river_answers = {k.lower(): v for k, v in river_answers.items()}
                participant_data = river_pending_confirmation.pop(session_id)
                participant_data.update(river_answers)

                # Re-check required fields
                required_fields = ["dob", "city", "state", "zip", "diagnosis_history", "age", "gender"]
                missing_fields = [k for k in required_fields if not participant_data.get(k)]
                if missing_fields:
                    print("⚠️ Missing fields in River follow-up:", missing_fields)
                    return {
                        "reply": (
                            "Thanks! Just one last step before we confirm your eligibility:
\n\n" +
                            "- " + "\n- ".join(missing_fields).replace("_", " ").title()
                        )
                    }

                last_participant_data[session_id] = participant_data
                push_to_monday(participant_data)
                return {
                    "reply": "Thanks! You’re all set for the River Program. A coordinator will reach out to you soon."
                }
            except Exception as e:
                print("❌ River processing failed:", str(e))
                return {"reply": "Sorry, I couldn’t process your River Program answers. Please try again briefly."}

        flattened_raw = flatten_dict(json.loads(raw_json))
        participant_data = normalize_participant_data(flattened_raw)

        required_fields = ["dob", "city", "state", "zip", "diagnosis_history", "age", "gender"]
        missing_fields = [k for k in required_fields if not participant_data.get(k)]
        if missing_fields:
            print("⚠️ Missing fields:", missing_fields)
            return {
                "reply": (
                    "Thanks! I’ve saved your info so far. To match you to studies, I still need a few more details:\n\n" +
                    "- " + "\n- ".join(missing_fields).replace("_", " ").title()
                )
            }

        with open("tagged_indexed_studies_heyhope_final.json", "r") as f:
            all_studies = json.load(f)

        print("🧠 Matching studies using participant data:", participant_data)
        matches = match_studies(participant_data, all_studies)
        print("📋 Found matches:", [m["study"]["study_title"] for m in matches])

        if not matches:
            last_participant_data[session_id] = participant_data
            push_to_monday(participant_data)
            return {"reply": "😕 I couldn’t find any matches at the moment, but your info has been saved. We’ll reach out when a good study comes up."}

        last_participant_data[session_id] = participant_data
        study_selection_stage[session_id] = {"matches": matches}
        push_to_monday(participant_data)

        if session_id not in river_pending_confirmation and is_eligible_for_river(participant_data):
            river_pending_confirmation[session_id] = participant_data
            return {"reply": (
                "🌊 You've been matched to our **River Program** for at-home ketamine therapy via telehealth, designed for individuals with depression, PTSD, or anxiety.\n\n"
                "**Would you like to apply now? (Yes or No)**"
            )}

        reply_text = format_matches_for_gpt(matches)
        print("✅ FORMATTED MATCHES:\n", reply_text)

        return {
            "reply": reply_text +
                     "\n\n🔍 Let me know which of these you'd like to explore. Just type the number or name."
        }

    except Exception as e:
        print("❌ Exception while processing GPT match JSON:", str(e))
        print("📨 GPT message was:", gpt_message)
        return {"reply": "We encountered an error processing your info. Please try again or contact support."}
