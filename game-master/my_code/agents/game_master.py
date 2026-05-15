"""Game Master agent — single stateful agent for the entire adventure session."""

from __future__ import annotations

import re

from strands import Agent
from strands.agent.conversation_manager import SummarizingConversationManager

from my_code.models.data_models import AdventureScene, CharacterCard, GameState, WorldInfoEntry
from my_code.models.provider import get_model, system_prompt_suffix
from my_code.tools.dice_tools import roll_dice
from my_code.tools.memory_tools import add_world_info_entry, update_authors_note, update_memory


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
    """Build the baked-in system prompt from an AdventureScene.

    visual_context: pre-generated prose descriptions of scene_image and character
    portraits (produced once at startup by the vision model). Injected as a
    ## Visual Reference section so the GM can draw on them throughout the session.
    """
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

    prompt = "\n\n".join(parts)
    return system_prompt_suffix(prompt)


# ---------------------------------------------------------------------------
# Lore injection (pure Python — no LLM call)
# ---------------------------------------------------------------------------

def _match_character_triggers(scan_text: str, characters: list[CharacterCard]) -> list[CharacterCard]:
    """Return characters whose trigger keywords appear in scan_text."""
    matched = []
    for char in characters:
        for trigger in char.triggers:
            pattern = r"\b" + re.escape(trigger) + r"\b"
            if re.search(pattern, scan_text, re.IGNORECASE):
                matched.append(char)
                break
    return matched


def _build_world_context(player_input: str, last_response: str, state: GameState) -> str:
    """Scan input + last response for character triggers and custom world info keywords.

    Returns a formatted context block, or empty string if nothing matched.
    """
    scan_text = f"{player_input} {last_response}"

    # Character card injection
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

    # Custom world info entries
    wi_parts: list[str] = []
    for entry in state.world_info_entries:
        pattern = r"\b" + re.escape(entry.keyword) + r"\b"
        if re.search(pattern, scan_text, re.IGNORECASE):
            wi_parts.append(f"[{entry.keyword}] {entry.content}")
    wi_block = "\n".join(wi_parts)

    combined_parts = [p for p in (char_block, wi_block) if p]
    if not combined_parts:
        return ""

    return "[WORLD CONTEXT]\n" + "\n\n".join(combined_parts)


# ---------------------------------------------------------------------------
# Per-turn message builder
# ---------------------------------------------------------------------------

def build_turn_message(
    player_input: str,
    last_response: str,
    state: GameState,
    image_context: str = "",
) -> str:
    """Assemble the full message sent to the GM agent each turn.

    image_context: prose description generated from a /img call this turn.
    Injected as [IMAGE CONTEXT] so the GM weaves it into narration. Cleared
    by the caller after this turn — never persists.
    """
    parts: list[str] = []

    # Memory — always injected
    if state.memory.strip():
        parts.append(f"[MEMORY]\n{state.memory.strip()}")

    # World context — conditional keyword injection
    world_ctx = _build_world_context(player_input, last_response, state)
    if world_ctx:
        parts.append(world_ctx)

    # One-turn image context from /img command
    if image_context.strip():
        parts.append(f"[IMAGE CONTEXT]\n{image_context.strip()}")

    # Author's note — injected every author_note_depth turns (0 = every turn)
    depth = state.scene.author_note_depth
    if state.author_note.strip() and (depth == 0 or state.turn_count % depth == 0):
        parts.append(f"[AUTHOR'S NOTE: {state.author_note.strip()}]")

    parts.append(f"---\n{player_input.strip()}")

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Agent factory
# ---------------------------------------------------------------------------

def create_game_master(scene: AdventureScene, visual_context: str = "") -> Agent:
    """Create and return the stateful GM Agent for a new session.

    visual_context: prose descriptions generated from scene/character images at
    startup. Passed through to build_system_prompt so the GM has visual grounding
    without images ever entering the turn-by-turn context.
    """
    system_prompt = build_system_prompt(scene, visual_context=visual_context)
    model = get_model("game_master")

    return Agent(
        model=model,
        tools=[roll_dice, update_memory, update_authors_note, add_world_info_entry],
        conversation_manager=SummarizingConversationManager(
            summary_ratio=0.3,
            preserve_recent_messages=6,
        ),
        system_prompt=system_prompt,
    )
