# === UPDATED matcher.py (only adjusted filtering logic) ===
import os
from geopy.geocoders import GoogleV3
from geopy.distance import geodesic

geolocator = GoogleV3(api_key=os.getenv("GOOGLE_MAPS_API_KEY"))

def get_location_coords(zip_code):
    try:
        loc = geolocator.geocode(zip_code)
        if loc:
            return (loc.latitude, loc.longitude)
    except Exception as e:
        print("⚠️ Geocode failed for ZIP:", zip_code, "→", str(e))
    return None

def normalize(text):
    return text.lower().strip() if isinstance(text, str) else text

def extract_condition_tags(mental_section):
    if isinstance(mental_section, dict):
        conds = mental_section.get("Conditions", [])
    else:
        conds = []
    if isinstance(conds, list):
        return [normalize(c) for c in conds]
    elif isinstance(conds, str):
        return [normalize(c) for c in conds.split(",")]
    return []

def age_from_dob(dob_str):
    from datetime import datetime
    try:
        dob = datetime.strptime(dob_str, "%B %d, %Y")
        today = datetime.today()
        return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    except:
        return None

def passes_basic_filters(study, participant_tags, age, gender, coords):
    tags = study.get("tags", [])

    if study.get("min_age_years") and age is not None:
        if age < study["min_age_years"]:
            return False
    if study.get("max_age_years") and age is not None:
        if age > study["max_age_years"]:
            return False

    if "exclude_female" in tags and gender == "female":
        return False
    if "exclude_male" in tags and gender == "male":
        return False

    if coords and study.get("coordinates"):
        distance = geodesic(coords, study["coordinates"]).miles
        if distance > 100:
            return False

    return True

def match_studies(participant_data, all_studies, exclude_river=False):
    pd = participant_data
    location = pd.get("ZIP code") or pd.get("ZIP Code") or pd.get("zip")
    coords = pd.get("coordinates") or get_location_coords(location)
    dob = pd.get("Date of birth") or pd.get("dob")
    age = age_from_dob(dob)
    gender = normalize(pd.get("Gender identity") or pd.get("gender"))
    mental = pd.get("Mental Health & Diagnosis", {})

    main_conditions = extract_condition_tags(mental)
    participant_tags = set(main_conditions)

    if gender:
        participant_tags.add(gender)
    if pd.get("Pregnant or Breastfeeding") is True or pd.get("Pregnant or breastfeeding (Follow-Up)") is True:
        participant_tags.add("pregnant")
    if pd.get("bipolar", "").strip().lower() == "yes":
        participant_tags.add("bipolar")
    if pd.get("blood_pressure", "").strip().lower() in ["yes", "unsure"]:
        participant_tags.add("blood_pressure")
    if pd.get("ketamine_use", "").strip().lower() == "yes":
        participant_tags.add("ketamine_use")
    if pd.get("U.S. Veteran", "").strip().lower() == "yes":
        participant_tags.add("veteran")

    eligible_studies = []
    for study in all_studies:
        tags = study.get("tags", [])
        if exclude_river and "require_depression" in tags and "River" in study.get("study_title", ""):
            continue

        if passes_basic_filters(study, participant_tags, age, gender, coords):
            score = 5
            reasons = []

            if not any(pt in tags for pt in participant_tags):
                score -= 3
                reasons.append("⚠️ Main condition may not match")

            for tag in tags:
                if tag.startswith("exclude_") and tag[8:] in participant_tags:
                    reasons.append(f"❌ Excluded due to: {tag[8:]}")
                    score -= 2
                if tag.startswith("require_") and tag[8:] not in participant_tags:
                    reasons.append(f"⚠️ Missing required: {tag[8:]}")
                    score -= 2
                if tag.startswith("include_") and tag[8:] in participant_tags:
                    reasons.append(f"✅ Matches include: {tag[8:]}")
                    score += 1

            eligible_studies.append({
                "study": study,
                "match_score": max(1, min(score, 10)),
                "match_reason": reasons
            })

    for e in eligible_studies:
        if "River" in e["study"].get("study_title", ""):
            e["match_score"] += 2
            e["match_reason"].append("🌊 Prioritized River Program")

    sorted_matches = sorted(
        eligible_studies,
        key=lambda x: (
            -x["match_score"],  # high score first
            "River" not in x["study"].get("study_title", "")  # River = True gets priority
        )
    )[:20]

    matched_tags = set()
    matched_titles = []
    for match in sorted_matches:
        matched_tags.update(match["study"].get("tags", []))
        matched_titles.append(match["study"].get("study_title", "Untitled Study"))

    participant_data["matched_tags"] = sorted(matched_tags)
    participant_data["matched_studies"] = matched_titles

    return sorted_matches
