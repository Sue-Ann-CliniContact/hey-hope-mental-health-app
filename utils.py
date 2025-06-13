def format_matches_for_gpt(matches):
    if not matches:
        return "Sorry, we couldn’t find any matching studies based on the information provided."

    lines = ["Here are some clinical studies that may be a fit:\n"]

    for match in matches:
        title = match.get('study_title') or "Untitled Study"
        location = match.get('location') or "N/A"
        link = match.get('study_link') or "#"
        contact = match.get("contact", "")
        summary = match.get("summary", "")
        eligibility_text = match.get("eligibility", "").strip()
        confidence = match.get("match_confidence")
        rationale = match.get("match_rationale", "")

        lines.append(f"**{title}**")
        lines.append(f"**Location:** {location}")
        lines.append(f"**Study Link:** [{link}]({link})")

        if summary:
            sentences = summary.strip().split(". ")
            brief_summary = ". ".join(sentences[:2]).strip()
            if not brief_summary.endswith("."):
                brief_summary += "."
            lines.append(f"**Summary:** {brief_summary}")

        if eligibility_text:
            bullets = []
            for line in eligibility_text.splitlines():
                stripped = line.strip("•*-– ")
                if len(stripped) > 3:
                    bullets.append(f"- {stripped}")
            if bullets:
                lines.append("**Eligibility:**")
                lines.extend(bullets[:5])

        if contact and contact.lower() != "none":
            lines.append(f"**Contact:** {contact}")

        if confidence is not None:
            lines.append(f"**Match Confidence:** {confidence}/10")
        if rationale:
            lines.append(f"**Match Rationale:** {rationale}")

        lines.append("\n")

    return "\n".join(lines).strip()
