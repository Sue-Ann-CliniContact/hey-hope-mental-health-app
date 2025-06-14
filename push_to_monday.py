import os
import requests
import json
from datetime import datetime

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

    # Normalize keys to lowercase for consistent mapping
    participant_data = {k.strip().lower(): v for k, v in participant_data.items()}

    email = sanitize(participant_data.get("email address", ""))
    phone = sanitize(participant_data.get("phone number", ""))
    if phone and not phone.startswith("+"):
        phone = "+" + phone.lstrip("+")

    column_values = {}

    if email:
        column_values["email_mkrwp3sg"] = {"email": email, "text": email}
    if phone and len(phone) > 1:
        column_values["phone_mkrwnw09"] = {"phone": phone}

    def safe_add(key, field_name):
        val = sanitize(participant_data.get(field_name.lower(), ""))
        if val:
            column_values[key] = val

    safe_add("text_mkrw88sj", "city")
    safe_add("text_mkrwfpm2", "state")
    safe_add("text_mkrwbndm", "zip code")
    safe_add("text_mkrw5hsj", "best time to reach you")
    safe_add("text_mkrwey0s", "can we contact you via text message? (yes / no)")

    dob_raw = sanitize(participant_data.get("date of birth", ""))
    try:
        dob_obj = datetime.strptime(dob_raw, "%B %d, %Y")
        column_values["text_mkrwk3tk"] = dob_obj.strftime("%Y-%m-%d")
    except Exception:
        if dob_raw:
            column_values["text_mkrwk3tk"] = dob_raw

    safe_add("text_mkrwc5h6", "gender identity")
    safe_add("text_mkrwfv06", "race / ethnicity")
    safe_add("text_mkrw6ebk", "are you a u.s. veteran? (yes / no)")
    safe_add("text_mkrwfp9q", "are you native american or identify as indigenous? (yes / no)")
    safe_add("text_mkrw6jhn", "employment status (employed, unemployed, retired, student, other)")
    safe_add("text_mkrwp4az", "annual income range")
    safe_add("text_mkrw2622", "do you have health insurance? (yes / no / prefer not to say)")
    safe_add("text_mkrw4sz3", "are you currently receiving any form of mental health care? (yes / no)")
    safe_add("text_mkrw1n9t", "have you ever been diagnosed with any of the following?")
    safe_add("text_mkrw293d", "have you ever tried prescribed treatments such as ssris or antidepressants? (yes / no / unsure)")
    safe_add("text_mkrwgytp", "have you ever been diagnosed with bipolar disorder? (yes / no)")
    safe_add("text_mkrwrdv6", "do you currently have high blood pressure that is not medically managed? (yes / no / unsure)")
    safe_add("text_mkrwcpt", "have you used ketamine recreationally in the past? (yes / no / prefer not to say)")
    safe_add("text_mkrwts3h", "are you currently pregnant or breastfeeding? (yes / no / prefer not to say)")
    safe_add("text_mkrw3e9t", "are you open to remote or at-home participation options? (yes / no / maybe)")
    safe_add("text_mkrwnrrd", "are you willing to participate in brief screening calls with a study team? (yes / no / maybe)")
    safe_add("text_mkrwb4wx", "preferred participation format")
    safe_add("text_mkrw26r3", "do you speak a language other than english at home? (yes / no)")
    safe_add("text_mkrw250s", "if yes: what language(s) do you prefer to communicate in?")
    safe_add("text_mkrw27j4", "are you open to being contacted about future mental health studies?")
    safe_add("text_mkrw4nbt", "anything else you'd like us to know about your mental health journey or study preferences?")

    if participant_data.get("rivers_match", False):
        column_values["text_mkrxbqdc"] = "Yes"

    item_name = sanitize(participant_data.get("full name", "Hey Hope Lead"))

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
        "column_values": json.dumps(column_values)
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
