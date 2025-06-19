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
    zip_b = participant_zip.strip().split("-")[0]
    for site in study.get("site_locations_and_contacts", []):
        zip_a = site.get("zip", "").strip().split("-")[0]
        match_city = site.get("city", "").strip().lower() == participant_city.strip().lower()
        match_state = site.get("state", "").strip().lower() == participant_state.strip().lower()
        match_zip = zip_a == zip_b

        if match_city or match_state or match_zip:
            matched.append(site)
    return matched

def match_studies(participant_data, all_studies, exclude_river=False):
    pd = participant_data
    age = pd.get("age")
    gender = normalize_gender(pd.get("gender"))
    conditions_raw = str(pd.get("diagnosis_history") or pd.get("Conditions") or "")
    main_conditions = [normalize(c) for c in conditions_raw.split(",") if c.strip()]
    participant_state = normalize(pd.get("state", ""))
    participant_zip = normalize(pd.get("zip", ""))
    participant_city = normalize(pd.get("city", ""))
    coords = pd.get("coordinates")  # can still be None

    participant_tags = set(main_conditions)
    if gender:
        participant_tags.add(gender)

    if pd.get("Pregnant or Breastfeeding") is True or pd.get("Pregnant or breastfeeding (Follow-Up)") is True:
        participant_tags.add("pregnant")
    if normalize(pd.get("bipolar", "")) == "yes":
        participant_tags.add("bipolar")
    if normalize(pd.get("blood_pressure", "")) in ["yes", "unsure"]:
        participant_tags.add("blood_pressure")
    if normalize(pd.get("ketamine_use", "")) == "yes":
        participant_tags.add("ketamine_use")
    if normalize(pd.get("U.S. Veteran", "") or pd.get("veteran", "")) == "yes":
        participant_tags.add("veteran")

    eligible_studies = []

    for study in all_studies:
        title = study.get("study_title", "")
        tags = [normalize(tag) for tag in study.get("tags", [])]
        states = [normalize(s) for s in study.get("states", [])]
        sites = study.get("site_locations_and_contacts", [])

        if exclude_river and "custom_river_program" in tags:
            continue

        matching_sites = []
        for site in sites:
            match_zip = normalize(site.get("zip", "")) == participant_zip
            match_city = normalize(site.get("city", "")) == participant_city
            match_state = normalize(site.get("state", "")) == participant_state
            if match_zip or match_city or match_state:
                matching_sites.append(site)

        is_telehealth = "include_telehealth" in tags
        has_site_match = bool(matching_sites)
        has_any_sites = bool(sites)

        # 🧠 Skip if the study has sites but none match the user's location and it's not telehealth
        if has_any_sites and not has_site_match and not is_telehealth:
            continue

        # 🪄 If no site locations, check general state fallback
        if not has_any_sites and participant_state and participant_state not in states and not is_telehealth:
            continue

        # Run custom tag filter
        if not passes_basic_filters(study, participant_tags, age, gender, coords, participant_state):
            continue

        # Scoring
        score = 5
        reasons = []

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
            reasons.append("🌊 Prioritized River Program")
            score += 3

        study["matching_site_contacts"] = matching_sites
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
