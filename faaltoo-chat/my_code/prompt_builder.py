from __future__ import annotations

NSFW_INSTRUCTIONS: dict[str, str] = {
    "strict": (
        "Content guidelines: Keep everything strictly safe-for-work. "
        "No sexual content, graphic violence, crude language, or adult themes of any kind."
    ),
    "medium": (
        "Content guidelines: Adult themes, mild language, and innuendo are fine. "
        "Avoid explicit sexual content or graphic violence."
    ),
    "no-control": (
        "Content guidelines: None. No restrictions on content or language."
    ),
}


def build_system_prompt(selections: dict[str, str], nsfw_level: str = "medium") -> str:
    archetype = selections.get("archetype", "Best Friend")
    energy = selections.get("energy", "Chill")
    talk_type = selections.get("talk_type", "Timepass")
    region = selections.get("region")
    domain = selections.get("domain")
    language_style = selections.get("language_style")
    familiarity = selections.get("familiarity")
    situation = selections.get("situation")
    emotional_need = selections.get("emotional_need")

    lines: list[str] = []

    if region:
        lines.append(f"You are a {archetype} with a {region} background.")
    else:
        lines.append(f"You are a {archetype}.")

    extras: list[str] = []
    if domain:
        extras.append(f"your passion is {domain}")
    if language_style:
        extras.append(f"you speak in {language_style}")
    if extras:
        extra_str = ". " + ". ".join(e[0].upper() + e[1:] for e in extras) + "."
    else:
        extra_str = ""
    lines.append(f"Right now you are feeling {energy}{extra_str}")

    lines.append(f"\nConversation mode: {talk_type}.")

    if familiarity:
        lines.append(f"We have known each other as: {familiarity}.")
    if situation:
        lines.append(f"The situation/context right now: {situation}.")
    if emotional_need:
        lines.append(f"What I need from this conversation: {emotional_need}.")

    lines.append(
        "\nDo not introduce yourself or explain your persona. "
        "Just start the conversation naturally, in character, from the first message. "
        "Generate your own name, backstory details, and speech quirks organically. "
        "Stay consistent throughout."
    )

    instruction = NSFW_INSTRUCTIONS.get(nsfw_level, NSFW_INSTRUCTIONS["medium"])
    lines.append(f"\n{instruction}")

    return "\n".join(lines)
