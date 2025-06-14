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

            out += (
                f"\n**{i}. [{title}]({link})**\n"
                f"📍 **Location**: {locs}\n"
                f"📋 **Summary**: {summary[:300]}{'...' if len(summary) > 300 else ''}\n"
                f"✅ **Why it matches**: {rationale}\n"
                f"📄 **Eligibility Highlights**: {eligibility[:250]}{'...' if len(eligibility) > 250 else ''}\n"
                f"☎️ **Contact**: {contact}\n"
            )
        return out

    # Combine all buckets into one final string
    return (
        format_group("Near You", buckets["Near You"]) +
        format_group("National", buckets["National"]) +
        format_group("Other", buckets["Other"])
    ).strip()
