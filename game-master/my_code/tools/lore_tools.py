"""Lore tools — trigger scanning, character card lookup, lore block building.

Pure Python (no LLM). Mirrors KoboldCPP's World Info keyword injection.
Copied verbatim from story-engine/my_code/tools/lore_tools.py.
"""

from __future__ import annotations

import json
import re


def scan_for_triggers(beat_text: str, characters_json: str) -> str:
    """Scan player input for character trigger keywords.

    Args:
        beat_text: The current player action or story text.
        characters_json: JSON array of character cards.

    Returns:
        JSON array of matched character names.
    """
    characters = json.loads(characters_json)
    matched: list[str] = []

    for char in characters:
        for trigger in char["triggers"]:
            pattern = r"\b" + re.escape(trigger) + r"\b"
            if re.search(pattern, beat_text, re.IGNORECASE):
                matched.append(char["name"])
                break

    return json.dumps(matched)


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


def build_lore_block(matched_cards_json: str) -> str:
    """Assemble a compact lore injection block from matched character cards.

    Args:
        matched_cards_json: JSON array of pre-formatted character card strings.

    Returns:
        Character-focused lore context string ready for injection.
    """
    matched_cards = json.loads(matched_cards_json)

    if not matched_cards:
        return ""

    parts = ["## Characters in Scene\n"]
    for card in matched_cards:
        parts.append(f"\n{card}\n")

    return "".join(parts)
