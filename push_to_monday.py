import os
import requests
import json

MONDAY_API_KEY = os.getenv("MONDAY_API_KEY")
BOARD_ID = 2004529213  # Updated Hey Hope board ID
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

    tags = participant_data.get("matched_tags", [])
    matched_studies = participant_data.get("matched_studies", [])

    column_values = {
        "email_mkrzc5px": {
            "email": participant_data.get("email", ""),
            "text": participant_data.get("email", "")
        },
        "phone_mkrzeeh7": {
            "phone": phone_value
        },
        "numeric_mkrzfy78": participant_data.get("zip", ""),
        "text_mkrz55pk": participant_data.get("location", ""),
        "text_mkrz2151": participant_data.get("dob", ""),
        "text_mkrz2hx1": participant_data.get("gender", ""),
        "text_mkrze78q": participant_data.get("main_conditions", ""),
        "text_mkrzmr4a": participant_data.get("diagnosis_history", ""),
        "text_mkrzygkg": participant_data.get("receiving_treatment", ""),
        "text_mkrzw93e": participant_data.get("medications", ""),
        "text_mkrzsdxr": participant_data.get("preferred_format", ""),
        "text_mkrzqy0p": participant_data.get("remote_ok", ""),
        "text_mkrzptfz": participant_data.get("preferred_language", ""),
        "text_mkrz5rgj": participant_data.get("future_studies_opt_in", ""),
        "text_mkrzagbg": "Yes" if participant_data.get("rivers_match") else "No",
        "long_text_mkrzgyf7": ", ".join(tags),
        "long_text_mkrza8m6": "\n".join(matched_studies)
    }

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
