import os
import requests
import json

MONDAY_API_KEY = os.getenv("MONDAY_API_KEY")
BOARD_ID = 1987448172  # Hey Hope board
GROUP_ID = "topics"

def push_to_monday(participant_data):
    url = "https://api.monday.com/v2"
    headers = {
        "Authorization": MONDAY_API_KEY,
        "Content-Type": "application/json"
    }

    # Fix phone number: must be in + format or remove countryShortName if unsure
    phone_value = participant_data.get("phone", "")
    if not phone_value.startswith("+"):
        phone_value = "+" + phone_value.lstrip("+")

    column_values = {
        "name": participant_data.get("name", ""),
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
        "text_mkrw5hsj": participant_data.get("best_time", ""),
        "text_mkrwey0s": participant_data.get("text_opt_in", ""),
        "text_mkrwk3tk": participant_data.get("dob", ""),
        "text_mkrwc5h6": participant_data.get("gender", ""),
        "text_mkrwfv06": participant_data.get("ethnicity", ""),
        "text_mkrw6ebk": participant_data.get("veteran", ""),
        "text_mkrwfp9q": participant_data.get("indigenous", ""),
        "text_mkrw6jhn": participant_data.get("employment", ""),
        "text_mkrwp4az": participant_data.get("income", ""),
        "text_mkrw2622": participant_data.get("insurance", ""),
        "text_mkrw4sz3": participant_data.get("current_mental_care", ""),
        "text_mkrw1n9t": participant_data.get("diagnosis_history", ""),
        "text_mkrw293d": participant_data.get("ssri_use", ""),
        "text_mkrwgytp": participant_data.get("bipolar", ""),
        "text_mkrwrdv6": participant_data.get("blood_pressure", ""),
        "text_mkrwcpt": participant_data.get("ketamine_use", ""),
        "text_mkrwts3h": participant_data.get("pregnant", ""),
        "text_mkrw3e9t": participant_data.get("remote_ok", ""),
        "text_mkrwnrrd": participant_data.get("screening_calls_ok", ""),
        "text_mkrwb4wx": participant_data.get("preferred_format", ""),
        "text_mkrw26r3": participant_data.get("non_english_home", ""),
        "text_mkrw250s": participant_data.get("preferred_language", ""),
        "text_mkrw27j4": participant_data.get("future_studies_opt_in", ""),
        "text_mkrw4nbt": participant_data.get("notes", "")
    }

    # Conditionally populate Rivers match column
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
        print("Error pushing to Monday:", data)
    return data
