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
        buckets.setdefault(tag, []).append(match)

    def format_group(label, studies):
        if not studies:
            return ""
        out = f"\n\n### 🏷️ {label} Studies\n"
        for i, match in enumerate(studies[:5], 1):
            title = match.get("study_title", "Untitled")
            link = match.get("link", "")
            locs = match.get("locations", "")
            summary = match.get("summary", "")
            rationale = match.get("match_rationale", "")
            eligibility = match.get("eligibility", "")
            contact = match.get("contacts", "")

            out += (
                f"\n**{i}. [{title}]({link})**\n"
                f"📍 **Location**: {locs or 'Not specified'}\n"
                f"📋 **Summary**: {summary[:300]}{'...' if len(summary) > 300 else ''}\n"
                f"✅ **Why it matches**: {rationale}\n"
                f"📄 **Eligibility Highlights**: {eligibility[:250]}{'...' if len(eligibility) > 250 else ''}\n"
                f"☎️ **Contact**: {contact or 'Not provided'}\n"
            )
        return out

    return (
        format_group("Near You", buckets["Near You"]) +
        format_group("National", buckets["National"]) +
        format_group("Other", buckets["Other"])
    ).strip()
