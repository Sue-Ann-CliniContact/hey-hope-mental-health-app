import re
from geopy.distance import geodesic

def extract_age_from_text(text):
    matches = re.findall(r'(\d+)\s*(?:to|-|–|and)?\s*(\d+)?\s*(?:years|yrs)?', text.lower())
    if matches:
        try:
            min_age = int(matches[0][0])
            max_age = int(matches[0][1]) if matches[0][1] else 120
            return min_age, max_age
        except:
            return None, None
    return None, None

def is_mental_health_related(text: str) -> bool:
    keywords = ["depression", "anxiety", "ptsd", "bipolar", "mental health", "schizophrenia", "mood disorder"]
    tl = text.lower()
    return any(k in tl for k in keywords)

def compute_score_and_group(study, user_loc):
    score = 0
    group = "Other"
    full_text = " ".join([
        study.get("study_title", ""),
        study.get("summary", ""),
        study.get("eligibility_text", "")
    ])

    if is_mental_health_related(full_text):
        score += 5

    coords = study.get("coordinates")
    if user_loc and coords:
        lat2, lon2 = coords if isinstance(coords, (list, tuple)) else (coords["lat"], coords["lon"])
        dist = geodesic(user_loc, (lat2, lon2)).miles
        if dist <= 50:
            score += 3
            group = "Near You"
        elif dist <= 300:
            score += 2
            group = "National"
    else:
        score += 1

    return score, group

def match_studies(participant, studies, exclude_river=False):
    user_age = participant.get("age")
    user_loc = participant.get("location")
    if user_age is None:
        return []

    results = []
    river_candidate = None

    for s in studies:
        if s.get("recruitment_status", "").lower() != "recruiting":
            continue

        is_river = "river" in (s.get("study_title", "").lower() + " ".join(s.get("tags", [])))
        if exclude_river and is_river:
            continue

        min_a = s.get("min_age_years")
        max_a = s.get("max_age_years")
        if min_a is None or max_a is None:
            min_a_fallback, max_a_fallback = extract_age_from_text(s.get("eligibility_text", ""))
            min_a = min_a if min_a is not None else min_a_fallback or 0
            max_a = max_a if max_a is not None else max_a_fallback or 120

        if not (min_a <= user_age <= max_a):
            continue

        # Check gender eligibility
        eligibility_text = (s.get("eligibility_text") or "").lower()
        user_gender = (participant.get("gender", "") or "").lower()
        if "women only" in eligibility_text or "females only" in eligibility_text:
            if "female" not in user_gender:
                continue
        if "men only" in eligibility_text or "males only" in eligibility_text:
            if "male" not in user_gender:
                continue

        # Handle River match logic
        if is_river:
            state = participant.get("state", "").strip().upper()
            diagnosis = participant.get("diagnosis_history", "").lower()
            if (
                state in ["CA", "MT"] and
                any(dx in diagnosis for dx in ["depression", "ptsd", "anxiety"]) and
                participant.get("bipolar", "").lower() != "yes" and
                participant.get("blood_pressure", "").lower() != "yes" and
                participant.get("ketamine_use", "").lower() != "yes"
            ):
                river_candidate = s
                # Do not skip: include in results
                score = 10
                group = "National"
                rationale = ["Matched River Program eligibility"]
                contact_parts = list(filter(None, [s.get("contact_name"), s.get("contact_email"), s.get("contact_phone")]))
                results.append({
                    "study_title": s.get("study_title", "River Study"),
                    "location": s.get("location", "Unknown"),
                    "study_link": s.get("study_link"),
                    "summary": s.get("summary", "No summary."),
                    "eligibility": s.get("eligibility_text", "Not provided"),
                    "contact": " | ".join(contact_parts) if contact_parts else "Not available",
                    "match_confidence": score,
                    "match_rationale": "; ".join(rationale),
                    "group": group
                })
                continue  # Avoid double-adding this match

        # Score and group normal studies
        score, group = compute_score_and_group(s, user_loc)
        if score <= 0:
            continue

        rationale = []
        if is_mental_health_related(" ".join([s.get("study_title", ""), s.get("eligibility_text", "")])):
            rationale.append("Mental health relevance")
        rationale.append(f"Age range {min_a}-{max_a}")
        rationale.append(f"Proximity score {score}")

        contact_parts = []
        if s.get("contact_name"):
            contact_parts.append(s["contact_name"])
        if s.get("contact_email"):
            contact_parts.append(s["contact_email"])
        if s.get("contact_phone"):
            contact_parts.append(s["contact_phone"])
        contact = " | ".join(contact_parts) if contact_parts else "Not available"

        results.append({
            "study_title": s.get("study_title") or "No Title",
            "location": s.get("location") or "Unknown",
            "study_link": s.get("study_link") or f"https://clinicaltrials.gov/ct2/show/{s.get('nct_id','')}",
            "summary": s.get("summary") or "No summary.",
            "eligibility": s.get("eligibility_text") or "Not provided",
            "contact": contact,
            "match_confidence": score,
            "match_rationale": "; ".join(rationale),
            "group": group
        })

    results.sort(key=lambda x: x["match_confidence"], reverse=True)
    return results[:10]
