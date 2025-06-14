import json
import time
from tqdm import tqdm
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderUnavailable

def safe_geocode(geolocator, location, retries=3, delay=5):
    """
    Attempt to geocode a location with retries and backoff.
    """
    for attempt in range(retries):
        try:
            return geolocator.geocode(location, timeout=10)
        except (GeocoderTimedOut, GeocoderUnavailable) as e:
            print(f"⏳ Retry {attempt + 1} for '{location}' due to {e}")
            time.sleep(delay * (attempt + 1))  # Exponential backoff
    print(f"❌ Failed to geocode: {location}")
    return None

def main():
    input_path = "indexed_studies.json"
    output_path = "indexed_studies_with_coords.json"

    print(f"📂 Loading: {input_path}")
    with open(input_path, "r", encoding="utf-8") as f:
        studies = json.load(f)

    geolocator = Nominatim(user_agent="heyhope-geocoder")
    updated_studies = []

    for study in tqdm(studies, desc="Geocoding locations"):
        if "coordinates" not in study or not study["coordinates"]:
            loc_str = study.get("location", "").strip()
            if loc_str:
                loc = safe_geocode(geolocator, loc_str)
                if loc:
                    study["coordinates"] = [loc.latitude, loc.longitude]
                    print(f"📍 {loc_str} → ({loc.latitude}, {loc.longitude})")
                else:
                    study["coordinates"] = None
            else:
                study["coordinates"] = None
        updated_studies.append(study)
        time.sleep(1)  # Respectful delay to avoid rate limits

    print(f"💾 Saving to: {output_path}")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(updated_studies, f, indent=2)

    print("✅ Geocoding complete.")

if __name__ == "__main__":
    main()
