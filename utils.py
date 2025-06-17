from geopy.distance import geodesic

# ✅ Extracted earlier to avoid forward reference

def format_contact(study):
    primary = study.get("contact_name") or ""
    email = study.get("contact_email") or ""
    phone = study.get("contact_phone") or ""
    if primary or email or phone:
        return f"{primary} | {email} | {phone}".strip(" |")
    return "Not provided"

def format_matches_for_gpt(matches):
    if not matches:
        return "❌ Sorry, we couldn't find any matching studies at the moment."

    def get_confidence_label(score):
        if score >= 8:
            return "✅ High Match"
        elif score >= 5:
            return "👍 Good Match"
        else:
            return "📌 Possible Match"

    def classify_location(coords):
        if not coords:
            return "Other"
        try:
            distance = geodesic(coords, (33.9697897, -118.2468148)).miles
            return "Near You" if distance <= 100 else "National"
        except:
            return "Other"

    # Grouping logic
    grouped = {
        "Near You": [],
        "National": [],
        "Other": []
    }

    for match in matches:
        study = match["study"]
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
            return ""
        out = f"\n\n### 🏷️ {label} Studies\n"
        studies = sorted(studies, key=lambda x: x["match_confidence"], reverse=True)
        for i, s in enumerate(studies[:5], 1):
            confidence = get_confidence_label(s["match_confidence"])
            summary = s["summary"][:300] + ("..." if len(s["summary"]) > 300 else "")
            eligibility = s["eligibility"][:250] + ("..." if len(s["eligibility"]) > 250 else "")

            highlights = ""
            if s["matched_includes"]:
                highlights += "\n✨ Included: " + ", ".join(s["matched_includes"])
            if s["missing_required"]:
                highlights += "\n⚠️ Missing: " + ", ".join(s["missing_required"])
            if s["excluded_flags"]:
                highlights += "\n🚫 Excluded: " + ", ".join(s["excluded_flags"])

            out += (
                f"\n**{i}. [{s['study_title']}]({s['link']})**\n"
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
