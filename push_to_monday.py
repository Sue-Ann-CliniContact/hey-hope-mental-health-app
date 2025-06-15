import os
import requests
import json

MONDAY_API_KEY = os.getenv("MONDAY_API_KEY")
BOARD_ID = 2003358867  # Hey Hope board
GROUP_ID = "topics"

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
            "email": participant_data.get("email", ""),
            "text": participant_data.get("email", "")
        },
        "phone_mkrwnw09": {
            "phone": phone_value
        },
        "text_mkrw88sj": participant_data.get("city", ""),
        "text_mkrwfpm2": participant_data.get("state", ""),
        "text_mkrwbndm": participant_data.get("zip", ""),
        "text_mkrwk3tk": participant_data.get("dob", ""),
        "text_mkrwc5h6": participant_data.get("gender", ""),
        "text_mkrwfv06": participant_data.get("ethnicity", ""),
        "text_mkryn17b": participant_data.get("veteran", ""),
        "text_mkry9wwz": participant_data.get("indigenous", ""),
        "text_mkryazky": participant_data.get("profession", ""),
        "text_mkry6v3z": participant_data.get("diagnosis_history", ""),
        "text_mkrye22a": participant_data.get("diagnosed_by_provider", ""),
        "text_mkry8f89": participant_data.get("receiving_treatment", ""),
        "text_mkrybfqx": participant_data.get("medications", ""),
        "text_mkry7f99": participant_data.get("ketamine_use", ""),
        "text_mkryj41": participant_data.get("duration_symptoms", ""),
        "text_mkryn6g7": participant_data.get("pregnant", ""),
        "text_mkryvdap": participant_data.get("preferred_format", ""),
        "text_mkry33zt": participant_data.get("remote_ok", ""),
        "text_mkry5bdd": participant_data.get("screening_calls_ok", ""),
        "text_mkrydevh": participant_data.get("non_english_home", ""),
        "text_mkrys3pj": participant_data.get("preferred_language", ""),
        "text_mkry6nr7": participant_data.get("future_studies_opt_in", ""),
        "text_mkrykwbd": participant_data.get("notes", ""),
        "text_mkryv0aa": participant_data.get("text_opt_in", ""),
        "text_mkryjhq6": participant_data.get("best_time", ""),
        "text_mkrynnh7": str(participant_data.get("coordinates", "")),
        "text_mkrypzht": participant_data.get("bipolar", ""),
        "text_mkrygfm7": participant_data.get("blood_pressure", "")
    }

    if participant_data.get("rivers_match", False):
        column_values["text_mkrxbqdc"] = "Yes"

    column_values_str = json.dumps(column_values).replace('\\', '\\\\').replace('"', '\\"')

    query = f'''
    mutation {{
      create_item (
        board_id: {BOARD_ID},
        group_id: "{GROUP_ID}",
        item_name: "{participant_data.get("name", "Hey Hope Lead")}",
        column_values: "{column_values_str}"
      ) {{
        id
      }}
    }}
    '''

    response = requests.post(url, headers=headers, json={"query": query})
    data = response.json()

    if "errors" in data:
        print("❌ Error pushing to Monday.com:", json.dumps(data, indent=2))
    else:
        print("✅ Successfully pushed to Monday.com:", json.dumps(data, indent=2))

    return data
