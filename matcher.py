import re
from geopy.distance import geodesic

def get_location_coords(zip_code):
    # Placeholder - replace with actual geocoding
    return (33.9697897, -118.2468148) if zip_code == "90001" else None

def normalize(text):
    return text.lower().strip() if isinstance(text, str) else text

def extract_condition_tags(participant):
    conds = participant.get("Conditions", [])
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

    # Age
    if study.get("min_age_years") and age is not None:
        if age < study["min_age_years"]:
            return False
    if study.get("max_age_years") and age is not None:
        if age > study["max_age_years"]:
            return False

    # Gender
    if "exclude_female" in tags and gender == "female":
        return False
    if "exclude_male" in tags and gender == "male":
        return False

    # Location
    if coords and study.get("coordinates"):
        distance = geodesic(coords, study["coordinates"]).miles
        if distance > 100:  # Optional: filter or deprioritize later
            return False

    # Main condition tag must match at least one
    if not any(pt in tags for pt in participant_tags):
        return False

    return True

def match_studies(participant_data, all_studies, exclude_river=False):
    pd = participant_data
    location = pd.get("ZIP code") or pd.get("ZIP Code") or pd.get("zip")
    coords = get_location_coords(location)
    age = age_from_dob(pd.get("Date of birth"))
    gender = normalize(pd.get("Gender identity"))
    main_conditions = extract_condition_tags(pd.get("Mental Health & Diagnosis", {}))
    participant_tags = set(main_conditions)

    # Add key flags to help matching
    if gender:
        participant_tags.add(gender)
    if pd.get("Pregnant or Breastfeeding") is True or pd.get("Pregnant or breastfeeding (Follow-Up)") is True:
        participant_tags.add("pregnant")

    eligible_studies = []
    for study in all_studies:
        if exclude_river and "require_depression" in study.get("tags", []) and "River" in study.get("study_title", ""):
            continue

        if passes_basic_filters(study, participant_tags, age, gender, coords):
            score = 5  # default
            reasons = []

            tags = study.get("tags", [])

            # Handle inclusion/exclusion logic
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

    # River priority
    for e in eligible_studies:
        if "River" in e["study"].get("study_title", ""):
            e["match_score"] += 2
            e["match_reason"].append("🌊 Prioritized River Program")
    return sorted(eligible_studies, key=lambda x: x["match_score"], reverse=True)[:20]
