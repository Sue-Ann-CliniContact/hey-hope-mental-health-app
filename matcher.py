import math

def haversine_distance(coord1, coord2):
    # Calculate distance in kilometers between two coordinate tuples
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

def match_studies(participant, studies, exclude_river=False):
    matches = []
    age = participant.get("age")
    location = participant.get("coordinates")
    diagnosis = (participant.get("diagnosis_history") or "").lower()

    for study in studies:
        if exclude_river and "river" in study.get("study_title", "").lower():
            continue

        score = 0
        reasons = []

        # Age-based matching
        age_min = study.get("eligibility_min_age")
        age_max = study.get("eligibility_max_age")
        if age is not None and (age_min is not None or age_max is not None):
            if (age_min is not None and age < age_min) or (age_max is not None and age > age_max):
                continue  # disqualify
            else:
                score += 1
                reasons.append("Matches your age range")

        # Condition/diagnosis relevance
        conditions = (study.get("conditions") or "").lower()
        if any(term in conditions for term in diagnosis.split(", ")):
            score += 2
            reasons.append("Relevant condition match")

        # Location score
        loc_score = "Unknown"
        if location and study.get("location_coords"):
            dist = haversine_distance(location, study["location_coords"])
            study["distance_km"] = round(dist, 1)
            if dist <= 160:
                loc_score = "Near You"
                score += 2
                reasons.append(f"Located near you (~{int(dist)} km)")
            elif study.get("recruiting_nationwide"):
                loc_score = "National"
                score += 1
                reasons.append("Open to nationwide participants")
            else:
                loc_score = "Other"
        elif study.get("recruiting_nationwide"):
            loc_score = "National"
            score += 1
            reasons.append("Open to nationwide participants")
        else:
            loc_score = "Other"

        matches.append({
            "study_title": study.get("study_title"),
            "summary": study.get("brief_summary"),
            "conditions": study.get("conditions"),
            "locations": study.get("locations"),
            "contacts": study.get("contacts"),
            "link": study.get("nct_link"),
            "distance_km": study.get("distance_km", None),
            "match_confidence": score,
            "match_rationale": "; ".join(reasons),
            "location_tag": loc_score,
            "eligibility": study.get("eligibility_criteria", ""),
        })

    matches.sort(key=lambda m: m["match_confidence"], reverse=True)
    return matches
