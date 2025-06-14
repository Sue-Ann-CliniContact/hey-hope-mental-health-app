
def format_matches_for_gpt(matches):
    if not matches:
        return "😔 No eligible studies were found based on your info."

    formatted = []
    for i, study in enumerate(matches[:5], 1):
        title = study.get("study_title", "Untitled Study")
        location = study.get("location_summary") or "Location not specified"
        summary = study.get("summary", "No summary available.")
        eligibility = study.get("eligibility", "Eligibility details not provided.")
        link = study.get("nct_link") or study.get("url", "")
        contact_email = study.get("contact_email") or "Not listed"
        distance = study.get("match_distance_miles")
        match_reason = []

        if distance is not None:
            if distance <= 50:
                match_reason.append("near you")
            else:
                match_reason.append("national match")
        if study.get("min_age_num") or study.get("max_age_num"):
            match_reason.append("age-eligible")
        if "gender" in study and study["gender"].lower() != "all":
            match_reason.append(f"{study['gender'].lower()} participants")

        rationale = ", ".join(match_reason) if match_reason else "general eligibility"

        formatted.append(
            f"### {i}. {title}
"
            f"📍 **Location:** {location}
"
            f"📎 **Summary:** {summary}
"
            f"📄 **Eligibility:** {eligibility}
"
            f"🧭 **Match Rationale:** {rationale}
"
            f"✉️ **Contact:** {contact_email}
"
            f"🔗 **Study Link:** {link}
"
        )

    return "\n\n".join(formatted)
