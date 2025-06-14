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
    a = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

SYNONYMS = {
    "depression": ["depression", "major depressive disorder", "mdd"],
    "anxiety": ["anxiety", "gad", "generalized anxiety disorder"],
    "ptsd": ["ptsd", "post traumatic stress disorder", "post-traumatic stress"],
    "bipolar": ["bipolar", "bipolar disorder", "manic depression"],
    "adhd": ["adhd", "attention deficit hyperactivity disorder"],
    "autism": ["autism", "asd", "autism spectrum disorder"]
}

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
    ketamine_use = (participant.get("ketamine_use") or "").strip().lower()
    is_veteran = (participant.get("Are you a U.S. Veteran?") or "").strip().lower() == "yes"

    for study in studies:
        if exclude_river and "river" in (study.get("study_title") or "").lower():
            continue

        participant_gender = (participant.get("gender") or "").lower()
        eligibility_text = (study.get("eligibility_text") or "").lower()

        # Gender exclusion
        if participant_gender == "male":
            if any(term in eligibility_text for term in [
                "pregnant women", "pregnancy", "currently pregnant", "women aged",
                "female only", "females only", "breastfeeding women"
            ]):
                continue

        # ❌ Exclude if ketamine use is YES and study bans it
        if ketamine_use == "yes":
            if any(term in eligibility_text for term in [
                "no ketamine", "not used ketamine", "exclude if used ketamine",
                "must not have used ketamine", "no history of ketamine use"
            ]):
                continue

        score = 0
        reasons = []

        # Age-based matching
        age_min = study.get("min_age_years")
        age_max = study.get("max_age_years")
        if age is not None and (age_min is not None or age_max is not None):
            if (age_min is not None and age < age_min) or (age_max is not None and age > age_max):
                continue
            else:
                score += 1
                reasons.append("Matches your age range")

        # Mental health condition relevance
        combined_text = (
            (study.get("study_title") or "") + " " +
            (study.get("summary") or "") + " " +
            (study.get("eligibility_text") or "")
        )
        combined_text = normalize(combined_text)

        if not any(term in combined_text for term in expanded_terms):
            continue

        score += 2
        reasons.append("Relevant condition match")

        # Location matching
        loc_score = "Unknown"
        if location and study.get("coordinates"):
            dist = haversine_distance(location, study["coordinates"])
            study["distance_km"] = round(dist, 1)
            if dist <= 160:
                loc_score = "Near You"
                score += 2
                reasons.append(f"Located near you (~{int(dist)} km)")
            else:
                loc_score = "Other"
        else:
            loc_score = "Other"

        # ✅ Veteran boost
        if is_veteran and any(vet_term in combined_text for vet_term in [
            "veteran", "veterans", "military", "former military", "army", "navy", "air force", "marine corps"
        ]):
            score += 2
            reasons.append("Specifically targets veterans")

        contact_parts = []
        for key in ["contact_name", "contact_email", "contact_phone"]:
            val = study.get(key)
            if val:
                contact_parts.append(val)
        contact_info = " | ".join(contact_parts) if contact_parts else "Not provided"

        matches.append({
            "study_title": study.get("study_title"),
            "summary": study.get("summary", ""),
            "conditions": combined_text,
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
