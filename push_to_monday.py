import os
import requests
import json

MONDAY_API_KEY = os.getenv("MONDAY_API_KEY")
BOARD_ID = 1987448172  # GPT - Autism board
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
        "email_mkrjhbqe": {
            "email": participant_data.get("email", ""),
            "text": participant_data.get("email", "")
        },
        "phone_mkrj1e0m": {
            "phone": phone_value
        },
        "text_mkrk7xqa": participant_data.get("dob", ""),
        "text_mkrjg9tz": participant_data.get("location", ""),
        "text_mkrkgtyt": participant_data.get("relation", ""),
        "text_mkrknr35": participant_data.get("text_opt_in", ""),
        "text_mkrkh8qw": participant_data.get("diagnosis", ""),
        "text_mkrkz666": participant_data.get("diagnosis_age", ""),
        "text_mkrkm84b": participant_data.get("verbal", ""),
        "text_mkrke8tm": participant_data.get("medications", ""),
        "text_mkrkzpxn": participant_data.get("medication_names", ""),
        "text_mkrkrxv3": participant_data.get("co_conditions", ""),
        "text_mkrk547b": participant_data.get("mobility", ""),
        "text_mkrkgdjj": participant_data.get("school_program", ""),
        "text_mkrkb1gp": participant_data.get("visit_type", ""),
        "text_mkrk5kgn": participant_data.get("study_age_focus", ""),
        "text_mkrjjyek": participant_data.get("study_goals", "")
    }

    column_values_str = json.dumps(column_values).replace('\\', '\\\\').replace('"', '\\"')

    query = f'''
    mutation {{
      create_item (
        board_id: {BOARD_ID},
        group_id: "{GROUP_ID}",
        item_name: "{participant_data.get("name", "GPT Lead")}",
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
