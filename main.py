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

openai.api_key = os.getenv("OPENAI_API_KEY")

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SYSTEM_PROMPT = """You are a clinical trial assistant named Hey Hope. Your job is to collect the following info one-by-one in a conversational tone:
- Full Name
- Email Address
- Phone Number
- City
- State
- ZIP Code
- Best Time to Reach You
- Can we contact you via text message? (Yes / No)
- - Date of birth (e.g., March 14, 1992)
- Gender Identity
- Race / Ethnicity
- Are you a U.S. Veteran? (Yes / No)
- Are you Native American or identify as Indigenous? (Yes / No)
- Employment Status (Employed, Unemployed, Retired, Student, Other)
- Annual Income Range
- Do you have health insurance? (Yes / No / Prefer not to say)
- Are you currently receiving any form of mental health care? (Yes / No)
- Have you ever been diagnosed with any of the following? Depression, Anxiety, PTSD, Other (specify), or None
- Have you ever tried prescribed treatments such as SSRIs or antidepressants? (Yes / No / Unsure)
- Have you ever been diagnosed with bipolar disorder? (Yes / No)
- Do you currently have high blood pressure that is not medically managed? (Yes / No / Unsure)
- Have you used ketamine recreationally in the past? (Yes / No / Prefer not to say)
- Are you currently pregnant or breastfeeding? (Yes / No / Prefer not to say)
- Are you open to remote or at-home participation options? (Yes / No / Maybe)
- Are you willing to participate in brief screening calls with a study team? (Yes / No / Maybe)
- Preferred participation format: In-person / Remote / No preference
- Do you speak a language other than English at home? If yes, what language(s)?
- Are you open to being contacted about future mental health studies?
- Anything else you'd like us to know about your mental health journey or study preferences?

Ask one question at a time in a friendly tone. Use previous answers to skip ahead. Once all answers are collected, return only this dictionary: { ... all answers as key-value pairs ... } Do not summarize or explain."""

chat_histories = {}
river_pending_confirmation = {}

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
    red_flags = [
        "kill myself", "end my life", "can’t do this anymore", "suicidal", "want to die"
    ]
    return any(flag in text for flag in red_flags)

@app.post("/chat")
async def chat_handler(request: Request):
    body = await request.json()
    session_id = body.get("session_id", "default")
    user_input = body.get("message")

    if contains_red_flag(user_input):
        return {"reply": "🚨 It sounds like you’re going through a really difficult time. Please know that you’re not alone. If you’re in immediate danger, call 911. You can also call or text the 988 Suicide & Crisis Lifeline at 988 for free, 24/7 support."}

    # Handle River program confirmation logic
    if session_id in river_pending_confirmation:
        if user_input.strip().lower() in ["yes", "y", "yeah", "sure"]:
            participant_data = river_pending_confirmation.pop(session_id)
            push_to_monday(participant_data)  # Include match tagging in your push_to_monday
            return {"reply": "✅ Great! You've been submitted to the River Program. You'll be contacted shortly for the next steps."}
        elif user_input.strip().lower() in ["no", "n", "not interested"]:
            participant_data = river_pending_confirmation.pop(session_id)
            with open("indexed_studies.json", "r") as f:
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
            participant_data["age"] = calculate_age(participant_data.get("dob", ""))
            participant_data["location"] = f"{participant_data.get('city','')}, {participant_data.get('state','')}"
            print("📥 Extracted participant data:", json.dumps(participant_data, indent=2))

            with open("indexed_studies.json", "r") as f:
                all_studies = json.load(f)

            matches = match_studies(participant_data, all_studies)

            # Check for River match
            for m in matches:
                if "river" in m.get("study_title", "").lower():
                    river_pending_confirmation[session_id] = participant_data
                    return {"reply": (
                        "🌊 You've been matched to our **River Program**, which provides affordable at-home ketamine therapy with telehealth support. "
                        "Sessions are ~$5 each, and the $350 study fee is waived for Veterans and Native American participants.\n\n"
                        "Would you like to apply now?"
                    )}

            push_to_monday(participant_data)
            match_summary = format_matches_for_gpt(matches)
            return {"reply": match_summary}

        except Exception as e:
            print("❌ Exception while processing match:", str(e))
            return {"reply": "We encountered an error processing your info.", "error": str(e)}

    return {"reply": gpt_message}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
