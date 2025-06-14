
import re
from datetime import datetime
from math import radians, cos, sin, asin, sqrt

def haversine(lat1, lon1, lat2, lon2):
    if None in [lat1, lon1, lat2, lon2]:
        return None
    R = 3956  # Miles
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    return round(R * c, 1)

def match_studies(participant, all_studies, exclude_river=False):
    user_age = participant.get("age")
    gender = participant.get("gender", "").lower()
    user_lat, user_lon = (participant.get("coordinates") or (None, None))

    matches = []
    for study in all_studies:
        if exclude_river and "river" in study.get("study_title", "").lower():
            continue

        min_age = study.get("min_age_num")
        max_age = study.get("max_age_num")
        study_gender = study.get("gender", "").lower()

        # Age and gender filters
        if user_age is not None:
            if min_age is not None and user_age < min_age:
                continue
            if max_age is not None and user_age > max_age:
                continue
        if study_gender and study_gender != "all" and gender and study_gender != gender:
            continue

        # Distance filter
        study_lat = study.get("lat")
        study_lon = study.get("lon")
        distance = haversine(user_lat, user_lon, study_lat, study_lon)
        study["match_distance_miles"] = distance

        matches.append(study)

    # Sort by distance (prioritize closer ones)
    matches.sort(key=lambda s: s.get("match_distance_miles") or 9999)

    return matches
