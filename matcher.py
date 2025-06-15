import math
import re

def haversine_distance(coord1, coord2):
    lat1, lon1 = coord1
    lat2, lon2 = coord2
    R = 6371
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(delta_lambda/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

SYNONYMS = {
    "depression": ["depression", "major depressive disorder", "mdd"],
    "anxiety": ["anxiety", "gad", "generalized anxiety disorder"],
    "ptsd": ["ptsd", "post traumatic stress disorder", "post-traumatic stress"]
}

PROFESSION_TERMS = [
    "healthcare", "nurse", "doctor", "clinician", "first responder", "veteran", "military",
    "teacher", "educator", "student", "parent", "caregiver"
]

MEDICATION_TERMS = [
    "ssri", "antidepressant", "fluoxetine", "prozac", "sertraline", "zoloft",
    "escitalopram", "lexapro", "bupropion", "wellbutrin", "ketamine"
]

def normalize(text):
    return re.sub(r"[^\w\s]", "", text.lower()).strip()

def expand_terms(diagnosis_text):
    terms = set()
    for diag in diagnosis_text.split(","):
        norm = normalize(diag)
        for key, values in SYNONYMS.items():
            if norm in values:
                terms.update(values)
                break
        else:
            terms.add(norm)
    return terms

def match_studies(participant, studies, exclude_river=False):
    matches = []
    age = participant.get("age")
    location = participant.get("coordinates")
    diagnosis = (participant.get("diagnosis_history") or "").lower()
    expanded_terms = expand_terms(diagnosis)
    participant_gender = (participant.get("gender") or "").lower()
    participant_profession = normalize(participant.get("profession", ""))
    medications = normalize(participant.get("medications", ""))
    duration = (participant.get("duration_symptoms") or "").lower()
    race = normalize(participant.get("ethnicity", ""))
    prefers_remote = "remote" in (participant.get("preferred_format", "") or "").lower()

    for study in studies:
        title = (study.get("study_title") or "").lower()
        summary = (study.get("summary") or "")
        eligibility_text = (study.get("eligibility_text") or "").lower()
        summary_text = normalize(summary + " " + title)

        if exclude_river and "river" in title:
            continue

        # 🚫 Exclude if gender incompatible (unless River)
        if participant_gender == "male":
            if any(term in eligibility_text for term in [
                "pregnant women", "pregnancy", "currently pregnant", "women aged",
                "female only", "females only", "breastfeeding women", "mothers"
            ]):
                if "river" not in title:
                    continue

        # 🚫 Require diagnosis match
        if not any(term in summary_text for term in expanded_terms):
            if "river" not in title:
                continue

        # 🚫 Require age eligibility
        age_min = study.get("min_age_years")
        age_max = study.get("max_age_years")
        if age is not None and (age_min is not None or age_max is not None):
            if (age_min is not None and age < age_min) or (age_max is not None and age > age_max):
                if "river" not in title:
                    continue

        score = 0
        reasons = []

        # ✅ Add age match bonus
        score += 1
        reasons.append("Matches your age range")

        # ✅ Condition match bonus
        score += 2
        reasons.append("Relevant condition match")

        # ✅ Location scoring
        loc_score = "Unknown"
        if location and study.get("coordinates"):
            dist = haversine_distance(location, study["coordinates"])
            study["distance_km"] = round(dist, 1)
            if dist <= 160:
                loc_score = "Near You"
                score += 3
                reasons.append(f"Located near you (~{int(dist)} km)")
            else:
                loc_score = "Other"
        else:
            loc_score = "Other"

        # ✅ Remote-friendly bonus
        if prefers_remote and any(term in summary_text for term in ["telehealth", "remote", "at-home"]):
            score += 1
            reasons.append("Study offers remote participation")

        # ✅ Medication keyword match
        if medications:
            if any(med in summary_text for med in MEDICATION_TERMS):
                score += 1
                reasons.append("Mentions relevant medications")

        # ✅ Profession keyword match
        if participant_profession:
            for keyword in PROFESSION_TERMS:
                if keyword in participant_profession and keyword in summary_text:
                    score += 1
                    reasons.append("Profession-relevant study")
                    break

        # ✅ Duration + chronic match
        if "year" in duration or "month" in duration:
            if any(term in summary_text for term in ["chronic", "long term", "persistent"]):
                score += 1
                reasons.append("Symptom duration aligns with study criteria")

        # ✅ Race relevance
        if race and race in eligibility_text:
            score += 1
            reasons.append("Study includes your race/ethnicity group")

        # 🚫 Filter out studies scoring below 3
        if score < 3:
            continue

        contact_parts = []
        for key in ["contact_name", "contact_email", "contact_phone"]:
            val = study.get(key)
            if val:
                contact_parts.append(val)
        contact_info = " | ".join(contact_parts) if contact_parts else "Not provided"

        matches.append({
            "study_title": study.get("study_title"),
            "summary": summary,
            "conditions": summary_text,
            "locations": study.get("location", "Not specified"),
            "contacts": contact_info,
            "link": study.get("study_link", ""),
            "distance_km": study.get("distance_km", None),
            "match_confidence": score,
            "match_rationale": "; ".join(reasons),
            "location_tag": loc_score,
            "eligibility": study.get("eligibility_text", ""),
        })

    matches.sort(key=lambda m: m["match_confidence"], reverse=True)
    return matches
