from geopy.distance import geodesic
from dateutil import parser
from datetime import datetime

# === Confidence thresholds ===
HIGH_MATCH_THRESHOLD = 8
GOOD_MATCH_THRESHOLD = 5

def normalize_participant_data(raw):
    data = {}

    # Map fields like "Date of birth" → "dob"
    for k, v in raw.items():
        key = k.lower().strip()
        if "birth" in key or "dob" in key:
            data["dob"] = v
        elif key in ["zip code", "zip"]:
            data["zip"] = str(v).strip()
        elif key in ["gender", "gender identity"]:
            data["gender"] = v
        else:
            data[key] = v

    # 🎂 Calculate age from dob
    if "dob" in data and data["dob"]:
        try:
            dob = parser.parse(data["dob"])
            today = datetime.today()
            age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
            data["age"] = age
            print("🎂 Parsed age from DOB:", data["dob"], "→", age)
        except Exception as e:
            print("⚠️ Failed to parse DOB:", data["dob"], "→", str(e))
            data["age"] = None
    else:
        data["age"] = None

    return data

# ✅ Required for main.py JSON parsing
def flatten_dict(d, parent_key='', sep=' - '):
    items = {}
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.update(flatten_dict(v, new_key, sep=sep))
        else:
            items[new_key] = v
    return items

# ✅ Shared gender normalization
def normalize_gender(g):
    if not g:
        return ""
    g = g.lower().strip()
    if g in ["male", "m"]:
        return "male"
    elif g in ["female", "f"]:
        return "female"
    return g

def format_contact(study):
    matching_sites = study.get("matching_site_contacts", [])
    if matching_sites:
        formatted = []
        for site in matching_sites:
            parts = [
                site.get("contact_name", ""),
                site.get("contact_email", ""),
                site.get("contact_phone", "")
            ]
            formatted.append(" | ".join(p for p in parts if p))
        return "\n".join(formatted)
    # Fallback to study-level
    contact = study.get("study_contact", {})
    parts = [
        contact.get("name", ""),
        contact.get("email", ""),
        contact.get("phone", "")
    ]
    return " | ".join(p for p in parts if p) or "Not provided"

def format_matches_for_gpt(matches):
    if not matches:
        return "❌ Sorry, we couldn't find any matching studies at the moment."

    def get_confidence_label(score):
        if score >= HIGH_MATCH_THRESHOLD:
            return "✅ High Match"
        elif score >= GOOD_MATCH_THRESHOLD:
            return "👍 Good Match"
        else:
            return "📌 Possible Match"

    grouped = {"Near You": [], "National": [], "Other": []}
    for match in matches:
        study = match.get("study", {})
        score = match.get("match_score", 0)
        reasons = match.get("match_reason", [])
        participant_state = study.get("participant_state")
        participant_coords = study.get("participant_coords")  # already injected in match_studies

        # Fix: Ensure 'sites' field exists and is populated
        if "sites" not in study:
            study["sites"] = study.get("site_locations_and_contacts", [])

        tag = classify_location(participant_coords, study=study, participant_state=participant_state)

        matched_includes = [r for r in reasons if "Matches include" in r]
        missing_required = [r for r in reasons if "Missing required" in r]
        excluded_flags = [r for r in reasons if "Excluded due to" in r]

        formatted = {
            "study_title": study.get("study_title", "Untitled"),
            "link": study.get("study_link", ""),
            "locations": ", ".join(
                ", ".join(filter(None, [s.get("city", ""), s.get("state", "")]))
                for s in study.get("matching_site_contacts", [])
            ) or study.get("location", "Not specified"),
            "summary": study.get("summary", ""),
            "eligibility": study.get("eligibility_text", ""),
            "contacts": format_contact(study),
            "match_confidence": score,
            "match_rationale": " / ".join(reasons),
            "matched_includes": matched_includes,
            "missing_required": missing_required,
            "excluded_flags": excluded_flags
        }

        grouped[tag].append(formatted)

    def format_group(label, studies, global_index):
        if not studies:
            return f"\n\n### 🏷️ {label} Studies\nNo studies available in this category."

        out = f"\n\n### 🏷️ {label} Studies\n"
        studies = sorted(studies, key=lambda x: x["match_confidence"], reverse=True)

        for s in studies[:10]:
            i = global_index[0]
            global_index[0] += 1
            confidence = get_confidence_label(s["match_confidence"])

            summary = (s["summary"] or "Not provided")[:300]
            if s["summary"] and len(s["summary"]) > 300:
                summary += "..."

            eligibility = (s["eligibility"] or "Not specified")[:250]
            if s["eligibility"] and len(s["eligibility"]) > 250:
                eligibility += "..."

            highlights = ""
            if s["matched_includes"]:
                highlights += "\n✨ Included: " + ", ".join(s["matched_includes"])
            if s["missing_required"]:
                highlights += "\n⚠️ Missing: " + ", ".join(s["missing_required"])
            if s["excluded_flags"]:
                highlights += "\n🚫 Excluded: " + ", ".join(s["excluded_flags"])

            is_river = s["study_title"].strip().lower() == "river nonprofit ketamine trial"
            river_label = " 🌊 **[River Program]**" if is_river else ""
            safe_link = s["link"] or "#"

            out += (
                f"\n**{i}. [{s['study_title']}]({safe_link}){river_label}**\n"
                f"📍 **Location**: {s['locations']}\n"
                f"🏅 **Match Score**: {s['match_confidence']}/10  |  {confidence}\n"
                f"📜 **Summary**: {summary}\n"
                f"✅ **Why it matches**: {s['match_rationale']}\n"
                f"📄 **Eligibility Highlights**: {eligibility}{highlights}\n"
                f"☎️ **Contact**: {s['contacts']}\n"
            )
        return out

    global_index = [1]
    return (
        format_group("Near You", grouped["Near You"], global_index) +
        format_group("National", grouped["National"], global_index) +
        format_group("Other", grouped["Other"], global_index)
    ).strip()

def classify_location(participant_coords, study=None, participant_state=None):
    try:
        if not study:
            return "Other"

        title = study.get("study_title", "").strip().lower()
        tags = [t.lower().strip() for t in study.get("tags", [])]
        study_coords = study.get("coordinates")
        site_coords_list = [
            tuple((s.get("latitude"), s.get("longitude")))
            for s in study.get("sites", [])
            if s.get("latitude") is not None and s.get("longitude") is not None
        ]

        # ✅ Special case for River
        if title == "river nonprofit ketamine trial":
            if participant_state and participant_state.upper() in [s.upper() for s in study.get("states", [])]:
                return "Near You"
            return "Other"

        for sc in site_coords_list:
            if participant_coords and geodesic(participant_coords, sc).miles <= 100:
                return "Near You"

        if participant_coords and study_coords and len(study_coords) == 2:
            if geodesic(participant_coords, tuple(study_coords)).miles <= 100:
                return "Near You"
            elif geodesic(participant_coords, tuple(study_coords)).miles <= 1500:
                return "National"

        if participant_state:
            states = [s.upper() for s in study.get("states", [])]
            if participant_state.upper() in states:
                return "Near You"

    except Exception as e:
        print("⚠️ Location classification error:", e)

    return "Other"