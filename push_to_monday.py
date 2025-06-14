
import os
import requests
import json
from datetime import datetime

MONDAY_API_KEY = os.getenv("MONDAY_API_KEY")
BOARD_ID = 2003358867
GROUP_ID = "topics"

def sanitize(value):
    if isinstance(value, str):
        return value.replace("–", "-").strip()
    return value

def push_to_monday(participant_data):
    url = "https://api.monday.com/v2"
    headers = {
        "Authorization": MONDAY_API_KEY,
        "Content-Type": "application/json"
    }

    email = sanitize(participant_data.get("email", ""))
    phone = sanitize(participant_data.get("phone", ""))
    if phone and not phone.startswith("+"):
        phone = "+" + phone.lstrip("+")

    column_values = {}

    if email:
        column_values["email_mkrwp3sg"] = {"email": email, "text": email}
    if phone and len(phone) > 1:
        column_values["phone_mkrwnw09"] = {"phone": phone}

    def safe_add(key, field):
        val = sanitize(participant_data.get(field, ""))
        if val:
            column_values[key] = val

    safe_add("text_mkrw88sj", "city")
    safe_add("text_mkrwfpm2", "state")
    safe_add("text_mkrwbndm", "zip")
    safe_add("text_mkrw5hsj", "best_time")
    safe_add("text_mkrwey0s", "text_opt_in")

    dob_raw = sanitize(participant_data.get("dob", ""))
    try:
        dob_obj = datetime.strptime(dob_raw, "%B %d, %Y")
        column_values["text_mkrwk3tk"] = dob_obj.strftime("%Y-%m-%d")
    except Exception:
        if dob_raw:
            column_values["text_mkrwk3tk"] = dob_raw

    safe_add("text_mkrwc5h6", "gender")
    safe_add("text_mkrwfv06", "ethnicity")
    safe_add("text_mkrw6ebk", "veteran")
    safe_add("text_mkrwfp9q", "indigenous")
    safe_add("text_mkrw6jhn", "employment")
    safe_add("text_mkrwp4az", "income")
    safe_add("text_mkrw2622", "insurance")
    safe_add("text_mkrw4sz3", "current_mental_care")
    safe_add("text_mkrw1n9t", "diagnosis_history")
    safe_add("text_mkrw293d", "ssri_use")
    safe_add("text_mkrwgytp", "bipolar")
    safe_add("text_mkrwrdv6", "blood_pressure")
    safe_add("text_mkrwcpt", "ketamine_use")
    safe_add("text_mkrwts3h", "pregnant")
    safe_add("text_mkrw3e9t", "remote_ok")
    safe_add("text_mkrwnrrd", "screening_calls_ok")
    safe_add("text_mkrwb4wx", "preferred_format")
    safe_add("text_mkrw26r3", "non_english_home")
    safe_add("text_mkrw250s", "preferred_language")
    safe_add("text_mkrw27j4", "future_studies_opt_in")
    safe_add("text_mkrw4nbt", "notes")

    if participant_data.get("rivers_match", False):
        column_values["text_mkrxbqdc"] = "Yes"

    item_name = sanitize(participant_data.get("name", "Hey Hope Lead"))

    query = '''
    mutation ($board_id: ID!, $group_id: String!, $item_name: String!, $column_values: JSON!) {
        create_item (
          board_id: $board_id,
          group_id: $group_id,
          item_name: $item_name,
          column_values: $column_values
        ) {
          id
        }
    }
    '''

    variables = {
        "board_id": str(BOARD_ID),
        "group_id": GROUP_ID,
        "item_name": item_name,
        "column_values": column_values
    }

    print("📤 Monday Payload:", json.dumps(variables, indent=2))
    try:
        response = requests.post(url, headers=headers, json={"query": query, "variables": variables})
        data = response.json()
        if "errors" in data:
            print("❌ Error pushing to Monday.com:", json.dumps(data, indent=2))
        else:
            print("✅ Successfully pushed to Monday.com:", json.dumps(data, indent=2))
        return data
    except Exception as e:
        print("❌ Exception during Monday.com request:", str(e))
        return {"errors": [{"message": str(e)}]}
