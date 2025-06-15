def format_matches_for_gpt(matches):
    if not matches:
        return "❌ Sorry, we couldn't find any matching studies at the moment."

    buckets = {
        "Near You": [],
        "National": [],
        "Other": []
    }

    for match in matches:
        tag = match.get("location_tag", "Other")
        if tag not in buckets:
            tag = "Other"
        buckets[tag].append(match)

    def get_confidence_label(score):
        if score >= 7:
            return "✅ High Match"
        elif score >= 4:
            return "👍 Good Match"
        else:
            return "📌 General Match"

    def format_group(label, studies):
        if not studies:
            return ""
        out = f"\n\n### 🏷️ {label} Studies\n"
        for i, match in enumerate(studies[:5], 1):
            title = match.get("study_title") or "Untitled"
            link = match.get("link") or ""
            locs = match.get("locations") or "Not specified"
            summary = match.get("summary") or ""
            rationale = match.get("match_rationale") or ""
            eligibility = match.get("eligibility") or ""
            contact = match.get("contacts") or "Not provided"
            score = match.get("match_confidence", 0)
            confidence = get_confidence_label(score)

            out += (
                f"\n**{i}. [{title}]({link})**\n"
                f"📍 **Location**: {locs}\n"
                f"🏅 **Match Score**: {score}/10  |  {confidence}\n"
                f"📋 **Summary**: {summary[:300]}{'...' if len(summary) > 300 else ''}\n"
                f"✅ **Why it matches**: {rationale}\n"
                f"📄 **Eligibility Highlights**: {eligibility[:250]}{'...' if len(eligibility) > 250 else ''}\n"
                f"☎️ **Contact**: {contact}\n"
            )
        return out

    return (
        format_group("Near You", buckets["Near You"]) +
        format_group("National", buckets["National"]) +
        format_group("Other", buckets["Other"])
    ).strip()
