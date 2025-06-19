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
    if "states" in study and isinstance(study["states"], list):
        if participant_state.upper() not in [s.upper() for s in study["states"]]:
            return False

    if coords and study.get("coordinates") and not study.get("matching_site_contacts"):
        try:
            distance = geodesic(coords, study["coordinates"]).miles
            if distance > 100:
                if "include_telehealth" in tags:
                    return True
                return False
        except:
            pass

    return True

def get_matching_sites(study, participant_city, participant_state, participant_zip):
    matched = []
    for site in study.get("site_locations_and_contacts", []):
        match_city = site.get("city", "").strip().lower() == participant_city.strip().lower()
        match_state = site.get("state", "").strip().lower() == participant_state.strip().lower()
        match_zip = site.get("zip", "").strip() == participant_zip.strip()
        if match_zip or match_city or match_state:
            matched.append(site)
    return matched

def get_matching_sites_by_coords(study, participant_coords, fallback_state=None, radius_miles=100):
    if not participant_coords:
        return []

    matched_sites = []
    for site in study.get("site_locations_and_contacts", []):
        site_coords = site.get("coordinates")
        if site_coords and isinstance(site_coords, list) and len(site_coords) == 2:
            try:
                distance = geodesic(participant_coords, tuple(site_coords)).miles
                if distance <= radius_miles:
                    matched_sites.append(site)
            except Exception:
                continue
        elif fallback_state and site.get("state", "").strip().lower() == fallback_state.strip().lower():
            matched_sites.append(site)
    return matched_sites

def is_study_location_near(participant_coords, study_coords, radius_miles=100):
    if not participant_coords or not study_coords:
        return False
    try:
        distance = geodesic(participant_coords, tuple(study_coords)).miles
        return distance <= radius_miles
    except Exception:
        return False

def match_studies(participant_data, all_studies, exclude_river=False):
    pd = participant_data
    coords = pd.get("coordinates")
    age = pd.get("age")
    gender = normalize_gender(pd.get("Gender identity") or pd.get("gender"))
    conditions_raw = str(pd.get("diagnosis_history") or pd.get("Conditions") or "")
    main_conditions = [normalize(c) for c in conditions_raw.split(",") if c.strip()]
    participant_state = pd.get("state", "").lower()

    participant_tags = set(normalize(c) for c in main_conditions)
    if gender:
        participant_tags.add(gender)

    if normalize(pd.get("bipolar", "")) == "yes":
        participant_tags.add("bipolar")
    if normalize(pd.get("blood_pressure", "")) in ["yes", "unsure"]:
        participant_tags.add("blood_pressure")
    if normalize(pd.get("ketamine_use", "")) == "yes":
        participant_tags.add("ketamine_use")
    if pd.get("Pregnant or Breastfeeding") is True:
        participant_tags.add("pregnant")
    if normalize(pd.get("U.S. Veteran", "") or pd.get("veteran", "")) == "yes":
        participant_tags.add("veteran")

    eligible_studies = []
    for study in all_studies:
        title = study.get("study_title", "")
        tags = [normalize(tag) for tag in study.get("tags", [])]

        if exclude_river and "river program" in title.lower():
            continue

        matching_sites = get_matching_sites_by_coords(study, coords, fallback_state=participant_state)
        site_coords_exist = any(site.get("coordinates") for site in study.get("site_locations_and_contacts", []))
        study_coords = study.get("coordinates")
        study_states = [s.lower() for s in study.get("states", [])]
        is_telehealth = "include_telehealth" in tags

        # 🌍 Location rules
        location_ok = False
        if matching_sites:
            location_ok = True  # Nearby site
        elif study_coords and is_study_location_near(coords, study_coords):
            location_ok = True  # Main study location is near
        elif participant_state in study_states:
            location_ok = True  # Fallback to same-state match
        elif is_telehealth:
            location_ok = True  # Remote

        if not location_ok:
            continue

        study["matching_site_contacts"] = matching_sites

        if passes_basic_filters(study, participant_tags, age, gender, coords, participant_state):
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

            if "highlight_river_priority" in tags:
                score += 3
                reasons.append("🌊 Prioritized River Program")

            eligible_studies.append({
                "study": study,
                "match_score": max(1, min(score, 10)),
                "match_reason": reasons
            })

    return eligible_studies

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
