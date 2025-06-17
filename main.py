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

SYSTEM_PROMPT = """You are a clinical trial assistant named Hey Hope. Start by asking one question at a time to collect just enough information to match the user with mental health studies.

First, collect:
- Name
- Email
- Phone number
- Date of birth
- Gender
- ZIP code
- Their main mental health concern(s) like depression, anxiety, or PTSD

Once these are collected, perform initial matching using:
- Age
- Location
- Gender
- Main condition(s)

Return a broad list of studies (10–20), including the River Program if eligible.

Then, ask smart follow-up questions (e.g. about bipolar, pregnancy, cancer, etc.) based on what's needed to confirm matches from that list. Never ask all questions upfront.

Once enough information is gathered, return a structured JSON object of their info.

After each user reply, say “Got it!” or “Thanks!” to keep it conversational. Do not summarize their answers or repeat them back.

Follow-up rules:
- Ask about bipolar only if a study excludes it.
- Ask about gender-specific requirements only if needed.
- If eligible, ask River Program follow-ups.
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
    raw["gender"] = raw.get("gender") or get_any("gender", "gender identity")
    raw["zip"] = raw.get("zip") or get_any("zip", "zip code")

    loc = raw.get("location") or get_any("location")
    if loc and "," in loc:
        parts = [p.strip() for p in loc.split(",")]
        raw["city"] = parts[0]
        raw["state"] = normalize_state(parts[1]) if len(parts) > 1 else ""
    else:
        raw["city"] = raw.get("city") or get_any("city")
        raw["state"] = normalize_state(raw.get("state") or get_any("state"))

    conds = raw.get("diagnosis_history") or get_any("diagnosed with", "mental health conditions", "conditions")
    if isinstance(conds, list):
        raw["diagnosis_history"] = ", ".join(conds)
    else:
        raw["diagnosis_history"] = conds

    raw["age"] = calculate_age(raw["dob"])
    raw["location"] = f"{raw['city']}, {raw['state']}"
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

        for match in selected:
            title = match["study"].get("study_title", "Untitled Study")
            tags = match["study"].get("tags", [])
            q_set = []
            for tag in tags:
                if tag in tag_question_map:
                    q_set.append(tag_question_map[tag])
            if q_set:
                questions.append(f"📝 For **{title}**:\n- " + "\n- ".join(q_set))

        del study_selection_stage[session_id]

        return {
            "reply": (
                "Great choice! Just a few quick questions to confirm your fit for these studies:\n\n"
                + "\n\n".join(questions)
            )
        }

    # ... (rest of your existing River flow, GPT JSON handling, and study matching logic continues below as-is)
