from geopy.distance import geodesic

# === Confidence thresholds ===
HIGH_MATCH_THRESHOLD = 8
GOOD_MATCH_THRESHOLD = 5


# ✅ Gender normalization shared across files
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
    primary = study.get("contact_name", "")
    email = study.get("contact_email", "")
    phone = study.get("contact_phone", "")
    if primary or email or phone:
        return f"{primary} | {email} | {phone}".strip(" |")
    return "Not provided"

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

    def classify_location(coords):
        # Default center: LA coordinates
        center = (33.9697897, -118.2468148)
        try:
            if coords:
                distance = geodesic(coords, center).miles
                if distance <= 100:
                    return "Near You"
                elif distance <= 1500:
                    return "National"
        except:
            pass
        return "Other"

    # Grouping logic
    grouped = {
        "Near You": [],
        "National": [],
        "Other": []
    }

    for match in matches:
        study = match.get("study", {})
        score = match.get("match_score", 0)
        reasons = match.get("match_reason", [])
        tag = classify_location(study.get("coordinates"))

        matched_includes = [r for r in reasons if "Matches include" in r]
        missing_required = [r for r in reasons if "Missing required" in r]
        excluded_flags = [r for r in reasons if "Excluded due to" in r]

        formatted = {
            "study_title": study.get("study_title", "Untitled"),
            "link": study.get("study_link", ""),
            "locations": study.get("location", "Not specified"),
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

    def format_group(label, studies):
        if not studies:
            return f"\n\n### 🏷️ {label} Studies\nNo studies available in this category."

        out = f"\n\n### 🏷️ {label} Studies\n"
        studies = sorted(studies, key=lambda x: x["match_confidence"], reverse=True)

        for i, s in enumerate(studies[:10], 1):
            confidence = get_confidence_label(s["match_confidence"])
            summary = (s["summary"] or "Not provided")[:300] + ("..." if s["summary"] and len(s["summary"]) > 300 else "")
            eligibility = (s["eligibility"] or "Not specified")[:250] + ("..." if s["eligibility"] and len(s["eligibility"]) > 250 else "")

            highlights = ""
            if s["matched_includes"]:
                highlights += "\n✨ Included: " + ", ".join(s["matched_includes"])
            if s["missing_required"]:
                highlights += "\n⚠️ Missing: " + ", ".join(s["missing_required"])
            if s["excluded_flags"]:
                highlights += "\n🚫 Excluded: " + ", ".join(s["excluded_flags"])

            is_river = "river" in s['study_title'].lower()
            river_label = " 🌊 **[River Program]**" if is_river else ""

            safe_link = s['link'] or "#"
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

    return (
        format_group("Near You", grouped["Near You"]) +
        format_group("National", grouped["National"]) +
        format_group("Other", grouped["Other"])
    ).strip()
