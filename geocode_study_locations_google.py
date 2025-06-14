import json
import os
import time
from tqdm import tqdm
import requests
from dotenv import load_dotenv

load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
INPUT_FILE = "indexed_studies.json"
OUTPUT_FILE = "indexed_studies_with_coords.json"

def geocode_google(location):
    base_url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {
        "address": location,
        "key": GOOGLE_API_KEY
    }
    response = requests.get(base_url, params=params)
    if response.status_code == 200:
        data = response.json()
        if data["results"]:
            coords = data["results"][0]["geometry"]["location"]
            return coords["lat"], coords["lng"]
    return None, None

def main():
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        studies = json.load(f)

    location_cache = {}
    updated = 0

    for study in tqdm(studies, desc="Geocoding locations"):
        if "coordinates" in study and study["coordinates"]:
            continue  # Skip already geocoded

        location = study.get("location", "").strip()
        if not location:
            continue

        if location in location_cache:
            study["coordinates"] = location_cache[location]
        else:
            lat, lon = geocode_google(location)
            if lat and lon:
                coords = (lat, lon)
                location_cache[location] = coords
                study["coordinates"] = coords
                updated += 1
            else:
                study["coordinates"] = None
            time.sleep(0.05)  # ~20 req/sec to stay under limits

    print(f"✅ Geocoded {updated} unique new locations.")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(studies, f, indent=2)

if __name__ == "__main__":
    main()
