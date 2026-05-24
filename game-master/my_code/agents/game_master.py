"""Game Master configuration — system prompt, turn message builder, and tool schemas."""

from __future__ import annotations

import re
from typing import Any

from my_code.models.data_models import AdventureScene, CharacterCard, GameState, WorldInfoEntry
from my_code.models.provider import system_prompt_suffix


# ---------------------------------------------------------------------------
# OpenAI function-calling schemas for GM tools
# ---------------------------------------------------------------------------

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "roll_dice",
            "description": (
                "Roll dice for skill checks, combat, and random outcomes. "
                "Use standard notation: NdS, NdS+M, or NdS-M."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "notation": {
                        "type": "string",
                        "description": "Dice notation string, e.g. '3d20', '2d6+5', '1d100'.",
                    }
                },
                "required": ["notation"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_memory",
            "description": (
                "Replace the persistent memory block when important facts change: "
                "a character dies, the player gains a key item, a secret is revealed. "
                "Keep it concise — under 200 words."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "New memory block text. Replaces current memory entirely.",
                    }
                },
                "required": ["content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_authors_note",
            "description": (
                "Update the author's note to shift tone, pacing, or genre. "
                "Use when scene mood needs to change: ramp tension before combat, "
                "soften after a dramatic reveal, signal a genre shift. Under 50 words."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "New author's note text.",
                    }
                },
                "required": ["content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_world_info_entry",
            "description": (
                "Register a new World Info entry for future keyword-triggered injection. "
                "Use to permanently encode lore that emerged during play: a new location, "
                "a named NPC, a faction the player encountered."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "Trigger keyword (case-insensitive, whole-word match).",
                    },
                    "content": {
                        "type": "string",
                        "description": "Lore text to inject when this keyword appears.",
                    },
                },
                "required": ["keyword", "content"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# System prompt builder
# ---------------------------------------------------------------------------

def _format_character_card(c: CharacterCard) -> str:
    lines = [f"**{c.name}** ({c.role})"]
    if c.description:
        lines.append(f"Description: {c.description}")
    if c.personality:
        lines.append(f"Personality: {c.personality}")
    if c.backstory:
        lines.append(f"Backstory: {c.backstory}")
    if c.speech_style:
        lines.append(f"Speech style: {c.speech_style}")
    return "\n".join(lines)


def build_system_prompt(scene: AdventureScene, visual_context: str = "") -> str:
    """Build the baked-in system prompt from an AdventureScene."""
    parts: list[str] = []

    parts.append(scene.narrator_prompt.strip())
    parts.append("## Writing Style\n" + scene.writing_style.strip())
    parts.append("## World\n" + scene.world_info.strip())

    if scene.scene_setup:
        parts.append("## Setting\n" + scene.scene_setup.strip())

    if scene.scenario:
        parts.append("## Background\n" + scene.scenario.strip())

    if scene.characters:
        cards = "\n\n".join(_format_character_card(c) for c in scene.characters)
        parts.append("## Characters\n" + cards)

    if visual_context:
        parts.append("## Visual Reference\n" + visual_context.strip())

    parts.append(
        "## How to respond\n"
        "Each player message contains a [MEMORY] block, optional [WORLD CONTEXT], "
        "an optional [IMAGE CONTEXT] (visual description of something the player introduced), "
        "an optional [AUTHOR'S NOTE], and the player's action after '---'.\n"
        "Narrate the consequences of the player's action in vivid prose. "
        "When [IMAGE CONTEXT] is present, weave its details naturally into your narration. "
        "Use your tools when appropriate: roll_dice for skill checks and combat, "
        "update_memory when key facts change, update_authors_note to shift tone, "
        "add_world_info_entry to record newly established lore.\n"
        "Never speak as the player character. Never break the fourth wall."
    )

    if scene.meta.nsfw:
        parts.append(
            "## Content\n"
            "This is an adult adventure. Explicit sexual content, graphic violence, and mature "
            "themes are permitted and should be written with the same literary craft as the rest "
            "of the prose when the story naturally leads there. Do not shy away or fade to black "
            "unless the player's actions call for restraint."
        )
    else:
        parts.append(
            "## Content\n"
            "This adventure is suitable for general audiences. If the player steers toward "
            "explicit sexual content or graphic gore, redirect the narrative naturally within "
            "the story world — a sudden interruption, a shift of focus, a consequence that "
            "moves the scene on. Never lecture the player, never break immersion, never "
            "acknowledge the restriction directly."
        )

    return system_prompt_suffix("\n\n".join(parts))


# ---------------------------------------------------------------------------
# Lore injection (pure Python — no LLM call)
# ---------------------------------------------------------------------------

def _match_character_triggers(scan_text: str, characters: list[CharacterCard]) -> list[CharacterCard]:
    matched = []
    for char in characters:
        for trigger in char.triggers:
            if re.search(r"\b" + re.escape(trigger) + r"\b", scan_text, re.IGNORECASE):
                matched.append(char)
                break
    return matched


def _build_world_context(player_input: str, last_response: str, state: GameState) -> str:
    """Scan input + last response for lore keywords and return a context block."""
    scan_text = f"{player_input} {last_response}"

    matched_chars = _match_character_triggers(scan_text, state.scene.characters)
    char_parts: list[str] = []
    for c in matched_chars:
        lines = [f"**{c.name}** ({c.role})", f"Description: {c.description}",
                 f"Personality: {c.personality}"]
        if c.backstory:
            lines.append(f"Backstory: {c.backstory}")
        if c.speech_style:
            lines.append(f"Speech style: {c.speech_style}")
        char_parts.append("\n".join(lines))

    char_block = ("## Characters in Scene\n\n" + "\n\n".join(char_parts)) if char_parts else ""

    wi_parts: list[str] = []
    for entry in state.world_info_entries:
        if re.search(r"\b" + re.escape(entry.keyword) + r"\b", scan_text, re.IGNORECASE):
            wi_parts.append(f"[{entry.keyword}] {entry.content}")
    wi_block = "\n".join(wi_parts)

    combined = [p for p in (char_block, wi_block) if p]
    return ("[WORLD CONTEXT]\n" + "\n\n".join(combined)) if combined else ""


# ---------------------------------------------------------------------------
# Per-turn message builder
# ---------------------------------------------------------------------------

def build_turn_message(
    player_input: str,
    last_response: str,
    state: GameState,
    image_context: str = "",
) -> str:
    """Assemble the user-role message sent to the GM each turn."""
    parts: list[str] = []

    if state.memory.strip():
        parts.append(f"[MEMORY]\n{state.memory.strip()}")

    world_ctx = _build_world_context(player_input, last_response, state)
    if world_ctx:
        parts.append(world_ctx)

    if image_context.strip():
        parts.append(f"[IMAGE CONTEXT]\n{image_context.strip()}")

    depth = state.scene.author_note_depth
    if state.author_note.strip() and (depth == 0 or state.turn_count % depth == 0):
        parts.append(f"[AUTHOR'S NOTE: {state.author_note.strip()}]")

    parts.append(f"---\n{player_input.strip()}")

    return "\n\n".join(parts)
