"""Lore tools — trigger scanning, character card lookup, lore block building.

Owned by LoreInjectorAgent. See AGENT_DESIGN.md §2.2.
"""

from __future__ import annotations

import json
import re

from strands import tool


@tool
def scan_for_triggers(beat_text: str, characters_json: str) -> str:
    """Scan beat text for character trigger keywords.

    Args:
        beat_text: The current beat instruction text.
        characters_json: JSON array of character cards.

    Returns:
        JSON array of matched character names.
    """
    characters = json.loads(characters_json)
    matched: list[str] = []

    for char in characters:
        for trigger in char["triggers"]:
            # Case-insensitive whole-word match
            pattern = r"\b" + re.escape(trigger) + r"\b"
            if re.search(pattern, beat_text, re.IGNORECASE):
                matched.append(char["name"])
                break

    return json.dumps(matched)


@tool
def get_character_card(character_name: str, characters_json: str) -> str:
    """Retrieve a formatted character card by name.

    Args:
        character_name: Name of the character to look up.
        characters_json: JSON array of character cards.

    Returns:
        Formatted card string, or error message if not found.
    """
    characters = json.loads(characters_json)

    for char in characters:
        if char["name"] == character_name:
            lines = [
                f"**{char['name']}** ({char['role']})",
                f"Description: {char['description']}",
                f"Personality: {char['personality']}",
            ]
            if char.get("backstory"):
                lines.append(f"Backstory: {char['backstory']}")
            if char.get("speech_style"):
                lines.append(f"Speech style: {char['speech_style']}")
            return "\n".join(lines)

    return f"Character not found: {character_name}"


@tool
def build_lore_block(world_info: str, matched_cards_json: str) -> str:
    """Assemble a lore injection block from world info and matched character cards.

    Args:
        world_info: The global world-info content.
        matched_cards_json: JSON array of pre-formatted character card strings.

    Returns:
        Complete lore context string ready for narrator prompt injection.
    """
    matched_cards = json.loads(matched_cards_json)

    parts = ["## World\n", world_info]

    if matched_cards:
        parts.append("\n\n## Characters in Scene\n")
        for card in matched_cards:
            parts.append(f"\n{card}\n")

    return "".join(parts)
