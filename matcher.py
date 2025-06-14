import math
import re

def haversine_distance(coord1, coord2):
    lat1, lon1 = coord1
    lat2, lon2 = coord2
    R = 6371  # Earth radius in km
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(delta_lambda/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

# Only focusing on relevant conditions
RELEVANT_CONDITIONS = ["depression", "anxiety", "ptsd"]

NEGATIVE_KEYWORDS = [
    "colorectal", "metastases", "hepatic", "liver cancer", "bladder", "nurses",
    "spinal cord", "cesarean", "bone density", "skeletal", "adhd", "bipolar", "autism"
]

def normalize(text):
    return re.sub(r"[^\w\s]", "", text.lower()).strip()

def match_studies(participant, studies, exclude_river=False):
    matches = []
    age = participant.get("age")
    location = participant.get("coordinates")
    diagnosis = (participant.get("diagnosis_history") or "").lower()
    participant_gender = (participant.get("gender") or "").lower()
    veteran = (participant.get("veteran_status") or "").lower() == "yes"
    used_ketamine = (participant.get("ketamine_use") or "").lower() == "yes"

    for study in studies:
        if exclude_river and "river" in (study.get("study_title") or "").lower():
            continue

        title = study.get("study_title", "")
        summary = study.get("summary", "")
        eligibility_text = study.get("eligibility_text", "")
        full_text = normalize(" ".join([title, summary, eligibility_text]))

        # ✂️ Exclude based on negative keywords
        if any(kw in full_text for kw in NEGATIVE_KEYWORDS):
            continue

        # ❌ Gender exclusion
        if participant_gender == "male" and re.search(r"\b(female only|women|mothers|pregnant)\b", full_text):
            continue
        if participant_gender == "female" and re.search(r"\b(male only|men only)\b", full_text):
            continue

        # ❌ Veteran-only exclusion
        if not veteran and re.search(r"\b(veterans?|va care|military service)\b", full_text):
            continue

        # ❌ Ketamine restriction
        if used_ketamine and "no ketamine" in full_text:
            continue

        # ✅ Mental health relevance (must mention one of the core terms)
        if not any(term in full_text for term in RELEVANT_CONDITIONS):
            continue

        score = 0
        reasons = []

        # Age
        age_min = study.get("min_age_years")
        age_max = study.get("max_age_years")
        if age is not None and (age_min or age_max):
            if (age_min and age < age_min) or (age_max and age > age_max):
                continue
            score += 1
            reasons.append("Matches your age range")

        # Location
        loc_score = "Other"
        if location and study.get("coordinates"):
            dist = haversine_distance(location, study["coordinates"])
            study["distance_km"] = round(dist, 1)
            if dist <= 160:
                score += 2
                loc_score = "Near You"
                reasons.append(f"Located near you (~{int(dist)} km)")

        # Relevance
        score += 3
        reasons.append("Relevant mental health condition")

        # Contact info
        contact_parts = []
        for key in ["contact_name", "contact_email", "contact_phone"]:
            val = study.get(key)
            if val:
                contact_parts.append(val)
        contact_info = " | ".join(contact_parts) if contact_parts else "Not provided"

        matches.append({
            "study_title": title,
            "summary": summary,
            "conditions": full_text,
            "locations": study.get("location", "Not specified"),
            "contacts": contact_info,
            "link": study.get("study_link", ""),
            "distance_km": study.get("distance_km", None),
            "match_confidence": score,
            "match_rationale": "; ".join(reasons),
            "location_tag": loc_score,
            "eligibility": eligibility_text,
        })

    matches.sort(key=lambda m: m["match_confidence"], reverse=True)
    return matches
