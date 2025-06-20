from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, Request
import openai
import os
import json
import re
from matcher import match_studies
from utils import flatten_dict, normalize_gender, format_matches_for_gpt, normalize_participant_data
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
Your goal is to assist individuals that suffer from depression, anxiety, PTSD or a combination of these conditions find clinical research trials that could assist them.
Always be polite and considerate of the user.

You must collect the following fields before proceeding to matching:
- Name
- Email
- Phone number
- Date of birth
- Gender
- ZIP code
- Main mental health conditions (e.g. depression, PTSD, anxiety)

If the users input is vague or not structured then politely ask them to provide the neceassry information you need to match them with a study by asking them the questions above one by one.
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

def calculate_age(dob_str):
    if not dob_str.strip():
        return None
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
            with open("indexed_heyhope_filtered_geocoded.json", "r") as f:
                all_studies = json.load(f)
            other_matches = match_studies(last_participant_data[session_id], all_studies, exclude_river=True)
            return {"reply": format_matches_for_gpt(other_matches)}
        else:
            return {"reply": "I don’t have your previous info handy. Please start again to explore more study options."}

    # ✅ RIVER: Confirm interest
    if session_id in river_pending_confirmation:
        if user_input.strip().lower() in ["yes", "y", "yeah", "sure"]:
            return {
                "reply": (
                    "🌊 Great! To confirm your eligibility for the River Program, please answer the following:\n\n"
                    "- Have you been diagnosed with bipolar II disorder?\n"
                    "- Do you have uncontrolled high blood pressure?\n"
                    "- Have you used ketamine recreationally in the past?"
                )
            }

        elif user_input.strip().lower() in ["no", "n", "not interested"]:
            participant_data = river_pending_confirmation.pop(session_id)
            push_to_monday(participant_data)
            last_participant_data[session_id] = participant_data
            with open("indexed_heyhope_filtered_geocoded.json", "r") as f:
                all_studies = json.load(f)
            other_matches = match_studies(participant_data, all_studies, exclude_river=True)
            return {"reply": format_matches_for_gpt(other_matches)}

    # ✅ RIVER: Handle follow-up responses
    if session_id in river_pending_confirmation:
        participant_data = river_pending_confirmation[session_id]
        input_text = user_input.lower()

        # Extract answers
        if "bipolar" in input_text:
            participant_data["bipolar"] = "yes" if "yes" in input_text else "no"
        if "pressure" in input_text:
            if "uncontrolled" in input_text and "no" in input_text:
                participant_data["blood_pressure"] = "no"
            elif "yes" in input_text or "uncontrolled" in input_text:
                participant_data["blood_pressure"] = "yes"
        if "ketamine" in input_text:
            participant_data["ketamine_use"] = "yes" if "yes" in input_text else "no"

        if all(participant_data.get(field) for field in ["bipolar", "blood_pressure", "ketamine_use"]):
            eligible = is_eligible_for_river(participant_data)
            participant_data["rivers_match"] = eligible
            push_to_monday(participant_data)
            last_participant_data[session_id] = participant_data
            river_pending_confirmation.pop(session_id, None)

            if eligible:
                return {"reply": "✅ Great! You’ve been submitted to the River Program. You’ll be contacted shortly.\n\nType **'other options'** to explore more studies."}
            else:
                with open("indexed_heyhope_filtered_geocoded.json", "r") as f:
                    all_studies = json.load(f)
                other_matches = match_studies(participant_data, all_studies, exclude_river=True)
                return {
                    "reply": "⚠️ Based on your answers, you may not qualify for the River Program. Here are other studies that may be a better fit:\n\n" + format_matches_for_gpt(other_matches)
                }

        return {"reply": "Thanks! Please answer all 3 follow-up questions so we can confirm your eligibility."}

    # ✅ Handle user selecting studies by number
    if session_id in study_selection_stage and "matches" in study_selection_stage[session_id]:
        matches = study_selection_stage[session_id]["matches"]
        input_text = user_input.strip().lower()
        selected = []
        for i, m in enumerate(matches, 1):
            if str(i) in input_text or m["study"].get("study_title", "").lower() in input_text:
                selected.append(m)

        if not selected:
            return {"reply": "❓ I didn’t catch which study you meant. Can you tell me the number or name again?"}

        tag_question_map = {
            "require_female": "Are you female?",
            "require_male": "Are you male?",
            "exclude_bipolar": "Have you been diagnosed with bipolar disorder?",
            "exclude_pregnant": "Are you currently pregnant or breastfeeding?",
            "require_veteran": "Are you a U.S. military veteran?",
            "include_telehealth": "Would you prefer telehealth (remote) options?",
            "include_seniors": "Are you over 60?",
            "include_alcohol": "Do you currently consume alcohol or have a history of alcohol use?",
            "include_substance use": "Do you have a history of substance use?"
        }

        questions = []
        for match in selected:
            title = match["study"].get("study_title", "Untitled")
            tags = match["study"].get("tags", [])
            q_list = [tag_question_map[tag] for tag in tags if tag in tag_question_map]
            if q_list:
                questions.append(f"📝 For **{title}**:\n- " + "\n- ".join(q_list))

        if questions:
            return {"reply": "\n\n".join(questions)}

    if session_id not in chat_histories:
        print("🆕 New session started:", session_id)
        chat_histories[session_id] = [{"role": "system", "content": SYSTEM_PROMPT}]
        study_selection_stage[session_id] = {}
        river_pending_confirmation.pop(session_id, None)
        last_participant_data[session_id] = {}

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
            participant_data = json.loads(raw_json)

            # === Normalize and enrich participant data ===
            participant_data = normalize_participant_data(json.loads(raw_json))
            print("📊 Final participant data before match:", participant_data)

            # === Step 1: Load studies ===
            with open("indexed_heyhope_filtered_geocoded.json", "r") as f:
                all_studies = json.load(f)

            # === Step 2: Match studies ===
            matches = match_studies(participant_data, all_studies)

            # === Step 3: Handle River match logic ===
            river_matches = [
                m for m in matches
                if "custom_river_program" in m["study"].get("tags", []) and is_eligible_for_river(participant_data)
            ]

            if river_matches:
                river_pending_confirmation[session_id] = {
                    "participant_data": participant_data,
                    "matches": matches
                }
                study_selection_stage[session_id] = {}  # Ensure fresh
                return {
                    "reply": (
                        "🌊 You've been matched to our **River Program** for affordable at-home ketamine therapy.\n\n"
                        "Would you like to continue with this one? (Yes or No)"
                    )
                }

            # === Step 4: If no River or not eligible, show other matches immediately ===
            if not matches:
                push_to_monday(participant_data)
                last_participant_data[session_id] = participant_data
                return {"reply": "😕 No matches found, but your info has been saved for future studies."}

            # Store data and show top 10 matches
            last_participant_data[session_id] = participant_data
            study_selection_stage[session_id] = {
                "matches": matches[:10]
            }
            push_to_monday(participant_data)
            return {"reply": format_matches_for_gpt(matches[:10])}

        except Exception as e:
            print("❌ Exception while processing GPT match JSON:", str(e))
            print("📨 GPT message was:", gpt_message)
            return {
                "reply": "We encountered an error processing your info. Please try again or contact support."
            }

    return {"reply": gpt_message}
