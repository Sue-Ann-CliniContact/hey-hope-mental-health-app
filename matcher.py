import math
import re
from geopy.distance import geodesic
from utils import normalize_gender

from geopy.distance import geodesic

def passes_basic_filters(study, participant_tags, age, gender, coords, participant_state=""):
    tags = [tag.lower().strip() for tag in study.get("tags", [])]

    if study.get("min_age_years") is not None and age is not None:
        if age < study["min_age_years"]:
            return False

    if study.get("max_age_years") is not None and age is not None:
        if age > study["max_age_years"]:
            return False

    if "exclude_female" in tags and gender == "female":
        return False

    if "exclude_male" in tags and gender == "male":
        return False

    # River Program state match
    title = study.get("study_title", "").lower().strip()
    if title == "river nonprofit ketamine trial":
        if participant_state.upper() not in ["CA", "MT"]:
            return False

    # State-specific matching
    allowed_states = [s.upper() for s in study.get("states", []) if isinstance(s, str)]
    if allowed_states and participant_state.upper() not in allowed_states:
        return False

    # Location fallback using coordinates
    study_coords = study.get("coordinates")
    if isinstance(study_coords, dict) and coords:
        lat = study_coords.get("lat")
        lng = study_coords.get("lng")
        if lat and lng:
            try:
                if geodesic(coords, (lat, lng)).miles > 100:
                    if "include_telehealth" not in tags:
                        return False
            except:
                return False

    return True

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

def is_site_nearby(site, participant_coords, radius_miles=100):
    if not site or not participant_coords:
        return False
    lat = site.get("latitude")
    lon = site.get("longitude")
    if lat is None or lon is None:
        return False
    try:
        return geodesic(participant_coords, (lat, lon)).miles <= radius_miles
    except:
        return False

# Synonym map for stronger matching
SYNONYMS = {
    "depression": ["depression", "major depressive disorder", "mdd"],
    "anxiety": ["anxiety", "gad", "generalized anxiety disorder"],
    "ptsd": ["ptsd", "post traumatic stress disorder", "post-traumatic stress"]
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

def match_studies(participant, all_studies, exclude_river=False):
    coords = participant.get("coordinates")
    age = participant.get("age")
    gender = normalize_gender(participant.get("gender"))
    state = participant.get("state", "").upper()

    conds = participant.get("diagnosis_history", "").split(",")
    participant_tags = set(normalize_gender(gender).lower().strip() if gender else "")
    participant_tags.update([c.strip().lower() for c in conds if c.strip()])

    matched = []

    for study in all_studies:
        title = study.get("study_title", "")
        tags = [t.lower().strip() for t in study.get("tags", [])]

        if exclude_river and "custom_river_program" in tags:
            continue

        # Handle sites
        sites = study.get("site_locations_and_contacts", [])
        matching_sites = [s for s in sites if is_site_nearby(s, coords)]

        has_near_site = bool(matching_sites)
        is_telehealth = "include_telehealth" in tags

        if not has_near_site and not is_telehealth:
            study_coords = study.get("coordinates")
            if study_coords:
                try:
                    loc_tuple = (study_coords.get("lat"), study_coords.get("lng"))
                    if geodesic(coords, loc_tuple).miles <= 100:
                        has_near_site = True
                except Exception:
                    pass

        if not has_near_site and not is_telehealth:
            study_states = [s.upper() for s in study.get("states", [])]
            if state in study_states:
                has_near_site = True

        if not has_near_site and not is_telehealth:
            continue
        
        if not passes_basic_filters(study, participant_tags, age, gender, coords, state):
            continue

        score = 5
        reasons = []
        matched_includes = []
        missing_required = []
        excluded_flags = []

        for tag in tags:
            base = tag.split("_")[-1]
            if tag.startswith("include_") and base in participant_tags:
                score += 1
                matched_includes.append(base)
                reasons.append(f"✅ Matches include: {base}")
            elif tag.startswith("exclude_") and base in participant_tags:
                score -= 2
                excluded_flags.append(base)
                reasons.append(f"❌ Excluded due to: {base}")
            elif tag.startswith("require_") and base not in participant_tags:
                score -= 2
                missing_required.append(base)
                reasons.append(f"⚠️ Missing required: {base}")
 

        if "custom_river_program" in tags:
            score += 3
            reasons.append("🌊 Prioritized River Program")

        match_record = {
            "study": study,
            "match_score": max(1, min(score, 10)),
            "match_reason": reasons,
        }
        
        # 🚫 Gender-based exclusion logic
        participant_gender = (participant.get("gender") or "").lower()
        eligibility_text = (study.get("eligibility_text") or "").lower()
        if participant_gender == "male":
            if any(term in eligibility_text for term in [
                "pregnant women", "pregnancy", "currently pregnant", "women aged",
                "female only", "females only", "breastfeeding women", "mothers"
            ]):
                if "river" not in title:
                    continue  # skip non-River studies not relevant for males

        # 🚫 Skip irrelevant studies that do not mention required condition terms
        summary_text = (study.get("summary") or "") + " " + (study.get("study_title") or "")
        summary_text = normalize(summary_text)
        if not any(term in summary_text for term in expanded_terms):
            if "river" not in title:
                continue

        score = 0
        reasons = []

        # ✅ Age-based matching (null-safe)
        age_min = study.get("min_age_years")
        age_max = study.get("max_age_years")
        if age is not None and (age_min is not None or age_max is not None):
            if (age_min is not None and age < age_min) or (age_max is not None and age > age_max):
                if "river" not in title:
                    continue  # disqualify non-River matches
            else:
                score += 1
                reasons.append("Matches your age range")

        # ✅ Diagnosis match (already confirmed above, reward it)
        if any(term in summary_text for term in expanded_terms):
            score += 2
            reasons.append("Relevant condition match")

        # ✅ Location matching
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

        # 📞 Contact info
        contact_parts = []
        for key in ["contact_name", "contact_email", "contact_phone"]:
            val = study.get(key)
            if val:
                contact_parts.append(val)
        contact_info = " | ".join(contact_parts) if contact_parts else "Not provided"

        matches.append({
            "study_title": study.get("study_title"),
            "summary": study.get("summary", ""),
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

    # Sort by score and River priority
    return sorted(matched, key=lambda m: (-m["match_score"], "river" not in m["study"]["study_title"].lower()))
