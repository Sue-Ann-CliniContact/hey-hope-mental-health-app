from dateutil import parser
from datetime import datetime
import re
import os
from geopy.geocoders import GoogleV3

geolocator = GoogleV3(api_key=os.getenv("GOOGLE_MAPS_API_KEY"))

def flatten_dict(d, parent_key='', sep=' - '):
    items = {}
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.update(flatten_dict(v, new_key, sep=sep))
        else:
            items[new_key] = v
    return items

def normalize_gender(g):
    if not g:
        return ""
    g = g.lower().strip()
    if g in ["male", "m"]:
        return "male"
    elif g in ["female", "f"]:
        return "female"
    return g

def normalize_state(state_input):
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

def get_coordinates(city, state, zip_code):
    try:
        if zip_code:
            loc = geolocator.geocode({"postalcode": zip_code, "country": "US"})
        elif city and state:
            loc = geolocator.geocode(f"{city}, {state}")
        elif state:
            loc = geolocator.geocode(state)
        else:
            return None
        if loc:
            return (loc.latitude, loc.longitude)
    except Exception as e:
        print("⚠️ Failed to geocode location:", city, state, zip_code, "→", str(e))
    return None

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
    raw["zip"] = raw.get("zip") or get_any("zip", "zip code")
    raw_gender = raw.get("gender") or get_any("gender", "gender identity")
    raw["gender"] = normalize_gender(raw_gender)
    raw["city"] = raw.get("city") or get_any("city")
    raw["state"] = normalize_state(raw.get("state") or get_any("state"))

    if (not raw["city"] or not raw["state"]) and raw.get("zip"):
        try:
            loc = geolocator.geocode(f"{raw['zip']}, USA")
            if loc:
                print("📦 Raw geocoder output:", loc)
                parts = loc.address.split(", ")
                print("📍 Parsed from string:", parts)
                raw["city"] = raw["city"] or parts[0] if len(parts) >= 2 else ""
                raw["state"] = raw["state"] or normalize_state(parts[1]) if len(parts) >= 2 else ""
        except Exception as e:
            print("⚠️ ZIP enrichment error:", e)

    raw["city"] = raw.get("city") or "Unknown"
    raw["state"] = raw.get("state") or "Unknown"
    raw["location"] = f"{raw['city']}, {raw['state']}"

    conds = raw.get("diagnosis_history") or get_any("diagnosed with", "mental health conditions", "conditions")
    raw["diagnosis_history"] = ", ".join(conds) if isinstance(conds, list) else conds

    raw["age"] = calculate_age(raw["dob"])
    raw["coordinates"] = get_coordinates(raw["city"], raw["state"], raw["zip"])
    print("📌 Final participant coordinates set to:", raw["coordinates"])

    raw["bipolar"] = raw.get("bipolar") or get_any("bipolar disorder")
    raw["blood_pressure"] = raw.get("blood_pressure") or get_any("high blood pressure")
    raw["ketamine_use"] = raw.get("ketamine_use") or get_any("ketamine therapy", "ketamine use")

    if raw["gender"] == "male":
        raw["pregnant"] = "No"

    return raw
