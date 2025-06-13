def format_matches_for_gpt(matches):
    if not matches:
        return "Sorry, we couldn’t find any matching studies based on the information provided."

    lines = ["Here are some clinical studies that may be a fit:\n"]

    for match in matches:
        lines.append(f"**{match.get('study_title', 'Untitled Study')}**")
        lines.append(f"**Location:** {match.get('location', 'N/A')}")
        lines.append(f"**Study Link:** [{match.get('study_link', 'View Study')}]({match.get('study_link', '')})")

        summary = match.get("summary", "")
        if summary:
            sentences = summary.strip().split(". ")
            brief_summary = ". ".join(sentences[:2]).strip()
            if not brief_summary.endswith("."):
                brief_summary += "."
            lines.append(f"**Summary:** {brief_summary}")

        eligibility_text = match.get("eligibility", "").strip()
        if eligibility_text:
            bullets = []
            for line in eligibility_text.splitlines():
                stripped = line.strip("•*-– ")
                if len(stripped) > 3:
                    bullets.append(f"- {stripped}")
            if bullets:
                lines.append("**Eligibility:**")
                lines.extend(bullets[:5])

        contact = match.get("contact", "")
        if contact and contact.lower() != "none":
            lines.append(f"**Contact:** {contact}")

        confidence = match.get("match_confidence")
        rationale = match.get("match_rationale", "")
        lines.append(f"**Match Confidence:** {confidence}/10" if confidence else "")
        lines.append(f"**Match Rationale:** {rationale}")

        lines.append("\n")

    return "\n".join(lines).strip()
