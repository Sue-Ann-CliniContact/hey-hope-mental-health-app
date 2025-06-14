import os
import requests
import json

MONDAY_API_KEY = os.getenv("MONDAY_API_KEY")
BOARD_ID = 2003358867  # Hey Hope board
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

    phone_value = participant_data.get("phone", "")
    if not phone_value.startswith("+"):
        phone_value = "+" + phone_value.lstrip("+")

    column_values = {
        "email_mkrwp3sg": {
            "email": sanitize(participant_data.get("email", "")),
            "text": sanitize(participant_data.get("email", ""))
        },
        "phone_mkrwnw09": {
            "phone": phone_value
        },
        "text_mkrw88sj": sanitize(participant_data.get("city", "")),
        "text_mkrwfpm2": sanitize(participant_data.get("state", "")),
        "text_mkrwbndm": sanitize(participant_data.get("zip", "")),
        "text_mkrw5hsj": sanitize(participant_data.get("best_time", "")),
        "text_mkrwey0s": sanitize(participant_data.get("text_opt_in", "")),
        "text_mkrwk3tk": sanitize(participant_data.get("dob", "")),
        "text_mkrwc5h6": sanitize(participant_data.get("gender", "")),
        "text_mkrwfv06": sanitize(participant_data.get("ethnicity", "")),
        "text_mkrw6ebk": sanitize(participant_data.get("veteran", "")),
        "text_mkrwfp9q": sanitize(participant_data.get("indigenous", "")),
        "text_mkrw6jhn": sanitize(participant_data.get("employment", "")),
        "text_mkrwp4az": sanitize(participant_data.get("income", "")),
        "text_mkrw2622": sanitize(participant_data.get("insurance", "")),
        "text_mkrw4sz3": sanitize(participant_data.get("current_mental_care", "")),
        "text_mkrw1n9t": sanitize(participant_data.get("diagnosis_history", "")),
        "text_mkrw293d": sanitize(participant_data.get("ssri_use", "")),
        "text_mkrwgytp": sanitize(participant_data.get("bipolar", "")),
        "text_mkrwrdv6": sanitize(participant_data.get("blood_pressure", "")),
        "text_mkrwcpt": sanitize(participant_data.get("ketamine_use", "")),
        "text_mkrwts3h": sanitize(participant_data.get("pregnant", "")),
        "text_mkrw3e9t": sanitize(participant_data.get("remote_ok", "")),
        "text_mkrwnrrd": sanitize(participant_data.get("screening_calls_ok", "")),
        "text_mkrwb4wx": sanitize(participant_data.get("preferred_format", "")),
        "text_mkrw26r3": sanitize(participant_data.get("non_english_home", "")),
        "text_mkrw250s": sanitize(participant_data.get("preferred_language", "")),
        "text_mkrw27j4": sanitize(participant_data.get("future_studies_opt_in", "")),
        "text_mkrw4nbt": sanitize(participant_data.get("notes", ""))
    }

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

    print("📤 Monday Payload:", json.dumps(variables, indent=2))  # Debug payload before sending

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
