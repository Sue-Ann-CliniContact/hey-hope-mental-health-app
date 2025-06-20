import os
from geopy.geocoders import GoogleV3
from geopy.distance import geodesic
from datetime import datetime
from utils import normalize_gender

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

def passes_basic_filters(study, participant_tags, age, gender, coords, participant_state=""):
    tags = [normalize(tag) for tag in study.get("tags", [])]

    if study.get("min_age_years") is not None and age is not None:
        if age < study["min_age_years"]:
            print(f"❌ Too young: {age} < {study['min_age_years']}")
            return False
    if study.get("max_age_years") is not None and age is not None:
        if age > study["max_age_years"]:
            return False

    if "exclude_female" in tags and gender == "female":
        return False
    if "exclude_male" in tags and gender == "male":
        return False

    # ✅ Enforce location requirement for River
    title = study.get("study_title", "").strip().lower()
    if "river nonprofit ketamine trial" == title:
        if participant_state.upper() not in ["CA", "MT"]:
            return False
    
    # ✅ State-specific match logic
    if "states" in study and isinstance(study["states"], list) and study["states"]:
        if participant_state.upper() not in [s.upper() for s in study["states"]]:
            print(f"❌ State mismatch: {participant_state} not in {study['states']}")
            return False

    study_coords = study.get("coordinates")
    if coords and isinstance(study_coords, dict):
        try:
            study_tuple = (study_coords.get("lat"), study_coords.get("lng"))
            distance = geodesic(coords, study_tuple).miles
            if distance > 100:
                if "include_telehealth" in tags:
                    return True
                return False
        except:
            pass

    return True

def get_matching_sites(study, participant_city, participant_state, participant_zip):
    matched = []
    for site in study.get("sites", []):
        match_city = site.get("city", "").strip().lower() == participant_city.strip().lower()
        match_state = site.get("state", "").strip().lower() == participant_state.strip().lower()
        match_zip = site.get("zip", "").strip() == participant_zip.strip()
        if match_zip or match_city or match_state:
            matched.append(site)
    return matched

def is_study_location_near(participant_coords, study_coords, radius_miles=100):
    if not participant_coords or not study_coords:
        return False
    try:
        distance = geodesic(participant_coords, tuple(study_coords)).miles
        return distance <= radius_miles
    except Exception:
        return False

def is_site_nearby(site, participant_coords, radius_miles=100):
    site_coords = (site.get("latitude"), site.get("longitude"))
    if None in site_coords or not participant_coords:
        return False
    try:
        distance = geodesic(participant_coords, site_coords).miles
        return distance <= radius_miles
    except:
        return False

def match_studies(participant_data, all_studies, exclude_river=False):
    pd = participant_data
    coords = pd.get("coordinates")
    age = pd.get("age")
    gender = normalize_gender(pd.get("Gender identity") or pd.get("gender"))
    participant_state = (pd.get("state", "") or pd.get("State", "")).split()[0].upper()
    participant_state = participant_state.upper()
    zip_code = pd.get("zip", "")

    conditions_raw = str(pd.get("diagnosis_history") or pd.get("Conditions") or "")
    main_conditions = [normalize(c) for c in conditions_raw.split(",") if c.strip()]
    participant_tags = set(normalize(c) for c in main_conditions)

    if gender:
        participant_tags.add(gender)

    print("👤 Gender:", gender)
    print("📌 Participant Tags:", participant_tags)

    eligible_studies = []
    for study in all_studies:
        title = study.get("study_title", "")
        tags = [normalize(tag) for tag in study.get("tags", [])]
        
        for site in study.get("sites", []):
        # 👇 ADD THIS PATCH
            if "latitude" not in site or "longitude" not in site:
                site_coords = site.get("coordinates")
                if isinstance(site_coords, dict):
                    site["latitude"] = site_coords.get("lat")
                    site["longitude"] = site_coords.get("lng")

        if exclude_river and "custom_river_program" in tags:
            continue

        matching_sites = [
            s for s in study.get("sites", [])
            if is_site_nearby(s, coords)
        ]
        
        # Start of site logic
        has_matching_site = bool(matching_sites)
        is_telehealth = "include_telehealth" in tags

        # ➕ Fallback 1: study-level coordinates
        if not has_matching_site and not is_telehealth:
            study_coords = study.get("coordinates")
            if isinstance(study_coords, dict):
                study_coords = (study_coords.get("lat"), study_coords.get("lng"))
            if is_study_location_near(coords, study_coords):
                has_matching_site = True
                matching_sites = []
                print(f"📍 Using fallback study-level match for: {title}")

        # ➕ Fallback 2: state-level match
        if not has_matching_site and not is_telehealth:
            study_states = [s.upper() for s in study.get("states", [])]
            if participant_state and participant_state in study_states:
                has_matching_site = True
                matching_sites = []
                print(f"📍 State-level fallback used for: {title}")

        # ❗️ Now run the skip check AFTER fallbacks
        if not has_matching_site and not is_telehealth:
            print(f"⛔️ Skipping {title}: no nearby site or study location match")
            continue

        print("⏳ Checking basic filters for:", study.get("study_title", "Unknown"))
        if not passes_basic_filters(study, participant_tags, age, gender, coords, participant_state):
            print(f"❌ Filtered out by eligibility logic: {title}")
            continue

        score = 5
        reasons = []

        if not any(f"include_{pt}" in tags or pt in tags for pt in participant_tags):
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

        if "custom_river_program" in tags:
            score += 3
            reasons.append("🌊 Prioritized River Program")

        eligible_studies.append({
            "study": study,
            "match_score": max(1, min(score, 10)),
            "match_reason": reasons
        })

    sorted_matches = sorted(
        eligible_studies,
        key=lambda x: (-x["match_score"], "river" not in x["study"].get("study_title", "").lower())
    )[:20]

    matched_tags = set()
    matched_titles = []
    for match in sorted_matches:
        matched_tags.update(match["study"].get("tags", []))
        matched_titles.append(match["study"].get("study_title", "Untitled Study"))

    participant_data["matched_tags"] = sorted(matched_tags)
    participant_data["matched_studies"] = matched_titles

    return sorted_matches
