def normalize_participant_data(raw):
    key_map = {k.lower(): k for k in raw}

    def get_any(*keys):
        for key in keys:
            match = next((raw[v] for k, v in key_map.items() if key.lower() in k), None)
            if match:
                return match
        return ""

    # 🎯 Normalize core fields
    raw["dob"] = raw.get("dob") or get_any("date of birth")
    raw["phone"] = normalize_phone(raw.get("phone") or get_any("phone number"))
    raw["zip"] = raw.get("zip") or get_any("zip", "zip code")
    raw_gender = raw.get("gender") or get_any("gender", "gender identity")
    raw["gender"] = normalize_gender(raw_gender)
    raw["city"] = raw.get("city") or get_any("city")
    raw["state"] = normalize_state(raw.get("state") or get_any("state"))

    # 🗺️ ZIP → City/State fallback
    if (not raw["city"] or not raw["state"]) and raw.get("zip"):
        try:
            loc = geolocator.geocode(f"{raw['zip']}, USA")
            if loc:
                print("📦 Raw geocoder output:", loc)
                parts = loc.address.split(", ")
                print("📍 Parsed from string:", parts)
                raw["city"] = raw["city"] or parts[0] if len(parts) >= 2 else ""
                raw["state"] = raw["state"] or normalize_state(parts[1]) if len(parts) >= 2 else ""
                print(f"✅ ZIP enrichment resolved to {raw['city']}, {raw['state']}")
        except Exception as e:
            print("⚠️ ZIP enrichment error:", e)

    raw["city"] = raw.get("city") or "Unknown"
    raw["state"] = raw.get("state") or "Unknown"
    raw["location"] = f"{raw['city']}, {raw['state']}"

    # 🧠 Mental health summary
    conds = raw.get("diagnosis_history") or get_any("diagnosed with", "mental health conditions", "conditions")
    raw["diagnosis_history"] = ", ".join(conds) if isinstance(conds, list) else conds

    # 🎂 Age
    raw["age"] = calculate_age(raw["dob"])

    # 🧭 Coordinates for proximity matching
    raw["coordinates"] = get_coordinates(raw["city"], raw["state"], raw["zip"])
    print("📌 Final participant coordinates set to:", raw["coordinates"])

    # 🩺 River-related screening fields
    raw["bipolar"] = raw.get("bipolar") or get_any("bipolar disorder")
    raw["blood_pressure"] = raw.get("blood_pressure") or get_any("high blood pressure")
    raw["ketamine_use"] = raw.get("ketamine_use") or get_any("ketamine therapy", "ketamine use")

    # 👶 Pregnancy logic (male default = No)
    if raw["gender"] == "male":
        raw["pregnant"] = "No"

    return raw
