import re
from geopy.distance import geodesic

KEY_CONDITIONS = ["depression", "anxiety", "ptsd"]
CONDITION_EXCLUSIONS = [
    "cancer", "menopause", "breast", "bone", "liver", "skeletal", "postpartum",
    "premenstrual", "oncology", "metastases", "carcinoma"
]

GENDER_TERMS = {
    "male": ["male", "man", "men", "masculine"],
    "female": ["female", "woman", "women", "feminine", "pregnant", "breastfeeding"]
}

PROFESSION_KEYWORDS = {
    "healthcare": ["nurse", "doctor", "clinician", "paramedic", "first responder"],
    "veteran": ["veteran", "military", "service member"]
}

def normalize(text):
    return text.lower().strip() if isinstance(text, str) else ""

def condition_match(participant_conditions, study_title, study_conditions, eligibility_text):
    conditions = [normalize(c) for c in participant_conditions]
    joined = f"{study_title} {' '.join(study_conditions)} {eligibility_text}".lower()

    # Must match a declared study condition directly
    if not any(c in joined for c in conditions):
        return False

    # Disqualify if study is mainly about an unrelated condition
    if any(excl in joined for excl in CONDITION_EXCLUSIONS):
        return False

    return True

def gender_allowed(participant_gender, eligibility_text):
    if not participant_gender:
        return True
    g = normalize(participant_gender)
    for required_gender, terms in GENDER_TERMS.items():
        if required_gender != g and any(term in eligibility_text for term in terms):
            return False
    return True

def veteran_allowed(is_veteran, eligibility_text):
    text = eligibility_text.lower()
    if "veteran" in text or "military" in text:
        return is_veteran is True or "not a veteran" not in text
    return True

def extract_distance_miles(coords1, coords2):
    try:
        return round(geodesic(coords1, coords2).miles, 1)
    except:
        return None

def score_match(participant, study):
    score = 0
    rationale = []

    study_title = normalize(study.get("brief_title", ""))
    study_conditions = [normalize(c) for c in study.get("conditions", [])]
    eligibility = normalize(study.get("eligibility", ""))
    gender = normalize(participant.get("gender", ""))
    veteran = normalize(participant.get("veteran", "no")) == "yes"
    age = participant.get("age")

    # Condition Match
    participant_conditions = participant.get("diagnosis_history", "").split(",")
    participant_conditions = [c.strip().lower() for c in participant_conditions]
    if not condition_match(participant_conditions, study_title, study_conditions, eligibility):
        return None  # hard filter

    score += 2
    rationale.append("Relevant condition match")

    # Gender Match
    if not gender_allowed(gender, eligibility):
        return None  # hard filter

    score += 1
    rationale.append("Gender allowed")

    # Veteran
    if not veteran_allowed(veteran, eligibility):
        return None  # hard filter if veteran required and not matched

    # Age
    if age is not None:
        min_age = study.get("min_age")
        max_age = study.get("max_age")
        if (min_age and age < min_age) or (max_age and age > max_age):
            return None  # hard filter
        score += 1
        rationale.append("Matches your age range")

    # Location
    participant_coords = participant.get("coordinates")
    study_coords = study.get("location_coords")
    if participant_coords and study_coords:
        miles = extract_distance_miles(participant_coords, study_coords)
        if miles is not None:
            if miles <= 50:
                score += 2
                rationale.append(f"Located near you (~{miles} km)")
            elif miles <= 100:
                score += 1
                rationale.append(f"Study is within ~{miles} km")

    # Remote
    if participant.get("remote_ok", "").lower() == "yes" and study.get("is_remote"):
        score += 1
        rationale.append("Remote option available")

    # Race / Ethnicity
    race = normalize(participant.get("Race / Ethnicity", ""))
    if race and race in eligibility:
        score += 1
        rationale.append("Relevant race/ethnicity focus")

    # Medications
    meds = normalize(participant.get("medications", ""))
    if meds and meds in eligibility:
        score += 1
        rationale.append("Medication match")

    # Profession
    prof = normalize(participant.get("profession", ""))
    for label, keywords in PROFESSION_KEYWORDS.items():
        if label in prof or any(k in prof for k in keywords):
            if any(k in eligibility for k in keywords):
                score += 1
                rationale.append(f"Matches your profession: {label}")
            break

    return {
        "study": study,
        "score": score,
        "rationale": rationale
    }

def match_studies(participant, all_studies, exclude_river=False):
    matches = []
    for study in all_studies:
        if exclude_river and "river" in study.get("brief_title", "").lower():
            continue
        match = score_match(participant, study)
        if match and match["score"] >= 3:  # only return confident matches
            matches.append(match)

    # Sort by descending score
    matches.sort(key=lambda x: x["score"], reverse=True)
    return matches
