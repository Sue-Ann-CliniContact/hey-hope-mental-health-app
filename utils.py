
def format_matches_for_gpt(matches):
    if not matches:
        return "❌ No suitable matches were found at this time."

    sections = {
        "near_you": [],
        "national": [],
        "other": []
    }

    for m in matches:
        block = format_single_match(m)
        category = m.get("proximity") or "other"
        if category in sections:
            sections[category].append(block)
        else:
            sections["other"].append(block)

    response_parts = []
    if sections["near_you"]:
        response_parts.append("📍 **Studies Near You:**\n" + "\n\n".join(sections["near_you"]))
    if sections["national"]:
        response_parts.append("🌐 **National Studies:**\n" + "\n\n".join(sections["national"]))
    if sections["other"]:
        response_parts.append("📎 **Other Options:**\n" + "\n\n".join(sections["other"]))

    return "\n\n".join(response_parts)

def format_single_match(study, i=None):
    title = study.get("study_title", "Untitled")
    summary = study.get("brief_summary", "No summary available.")
    eligibility = study.get("eligibility_summary", "Eligibility not listed.")
    contact = study.get("contact", {})
    loc = study.get("location", "Location not available.")
    email = contact.get("email", "N/A")
    phone = contact.get("phone", "N/A")
    link = study.get("url", "")
    confidence = study.get("match_score", 5)

    match_reason = study.get("match_reason", "General match based on your profile.")

    header = f"### {i}. {title}" if i else f"### {title}"
    details = f"""{header}
📍 Location: {loc}
🔗 [View Study]({link})
📋 Summary: {summary}
🧪 Eligibility: {eligibility}
📞 Contact: {email} / {phone}
🤖 Match Confidence: {confidence}/10
💡 Why this match: {match_reason}"""
    return details.strip()
