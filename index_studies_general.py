import os
import json
import xml.etree.ElementTree as ET
import re
import sys

INPUT_DIR = "ctg-public-xml"  # Folder where XML files are extracted
OUTPUT_FILE = "indexed_studies.json"
INCLUDE_ONLY_US = True

US_ALIASES = {"united states", "usa", "us", "u.s.", "u.s.a.", "UN"}

def extract_age_range(text):
    matches = re.findall(r'(\d{1,2})\s*(?:to|-|–|and)\s*(\d{1,2})\s*(?:years|yrs)?', text, re.I)
    if matches:
        try:
            return int(matches[0][0]), int(matches[0][1])
        except:
            return None, None
    return None, None

def extract_contact_info(xml_root):
    name = email = phone = None

    # 1. Overall official contact
    official = xml_root.find("overall_official")
    if official is not None:
        name = official.findtext("last_name")
        email = official.findtext("email")
        phone = official.findtext("phone")

    # 2. Contact listed under locations
    if not email or not phone:
        contacts = xml_root.findall("location")
        for loc in contacts:
            if not email:
                email = loc.findtext("contact/email") or loc.findtext("contact_backup/email")
            if not phone:
                phone = loc.findtext("contact/phone") or loc.findtext("contact_backup/phone")
            if not name:
                name = loc.findtext("contact/last_name") or loc.findtext("contact_backup/last_name")
            if email or phone:
                break

    # 3. Country for filtering
    countries = xml_root.find("location_countries")
    country = countries.findtext("country") if countries is not None else None

    return name, email, phone, country

def extract_location(xml_root):
    facilities = xml_root.findall("location")
    if facilities:
        city = facilities[0].findtext("facility/address/city")
        state = facilities[0].findtext("facility/address/state")
        if city and state:
            return f"{city}, {state}"
        elif city:
            return city
    return None

def extract_summary(xml_root):
    brief = xml_root.findtext("brief_summary/textblock")
    if not brief:
        brief = xml_root.findtext("detailed_description/textblock")
    return re.sub(r'\s+', ' ', brief).strip() if brief else ""

def matches_keywords(text, keywords):
    return True if not keywords else any(k.lower() in text.lower() for k in keywords)

def index_studies(keywords=None, xml_dir=INPUT_DIR, output_path=OUTPUT_FILE):
    studies = []

    for root_dir, _, files in os.walk(xml_dir):
        for file in files:
            if not file.endswith(".xml"):
                continue

            try:
                tree = ET.parse(os.path.join(root_dir, file))
                root = tree.getroot()

                nct_id = root.findtext("id_info/nct_id")
                title = root.findtext("brief_title") or ""
                status = root.findtext("overall_status") or ""
                summary = extract_summary(root)
                eligibility = root.findtext("eligibility/criteria/textblock") or ""
                contact_name, contact_email, contact_phone, country = extract_contact_info(root)
                location = extract_location(root)
                study_link = f"https://clinicaltrials.gov/study/{nct_id}"
                full_text = " ".join([title, summary, eligibility])

                if not matches_keywords(full_text, keywords):
                    continue

                if INCLUDE_ONLY_US and (not country or country.strip().lower() not in US_ALIASES):
                    continue

                min_age, max_age = extract_age_range(eligibility)

                study = {
                    "nct_id": nct_id,
                    "study_title": title,
                    "recruitment_status": status,
                    "summary": summary,
                    "study_link": study_link,
                    "location": location,
                    "contact_name": contact_name,
                    "contact_email": contact_email,
                    "contact_phone": contact_phone,
                    "eligibility_text": eligibility,
                    "min_age_years": min_age,
                    "max_age_years": max_age
                }

                studies.append(study)

            except Exception as e:
                print(f"❌ Failed to process {file}: {e}")

    with open(output_path, "w") as f:
        json.dump(studies, f, indent=2)

    print(f"✅ Indexed {len(studies)} studies to {output_path}")


if __name__ == "__main__":
    keywords = sys.argv[1:]
    print(f"🔍 Filtering for keywords: {keywords or 'None (all US studies)'}")
    index_studies(keywords=keywords)
