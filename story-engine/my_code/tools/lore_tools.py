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
def build_lore_block(matched_cards_json: str) -> str:
    """Assemble a compact lore injection block from matched character cards.

    Args:
        matched_cards_json: JSON array of pre-formatted character card strings.

    Returns:
        Character-focused lore context string ready for narrator prompt injection.
    """
    matched_cards = json.loads(matched_cards_json)

    if not matched_cards:
        return ""

    parts = ["## Characters in Scene\n"]

    for card in matched_cards:
        parts.append(f"\n{card}\n")

    return "".join(parts)


@tool
def build_facts_block(facts_by_entity_json: str) -> str:
    """Assemble a compact continuity-facts block from pre-queried story facts.

    Pure formatting, same as build_lore_block — the actual database lookup
    (match_entities/query_facts in fact_store.py) happens before this is
    called, so no LLM or I/O is involved here.

    Args:
        facts_by_entity_json: JSON object mapping entity name to a list of
            {relation, value} dicts, e.g.
            {"dagger": [{"relation": "found_by", "value": "Aldric"}]}

    Returns:
        Continuity-focused lore context string ready for narrator prompt
        injection, or "" if there are no facts.
    """
    facts_by_entity = json.loads(facts_by_entity_json)

    if not facts_by_entity:
        return ""

    parts = ["## Established So Far\n"]

    for entity, facts in facts_by_entity.items():
        if not facts:
            continue
        parts.append(f"\n**{entity}**")
        for fact in facts:
            parts.append(f"\n- {fact['relation']}: {fact['value']}")
        parts.append("\n")

    return "".join(parts)
