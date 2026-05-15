"""Memory tools — GM-callable tools for mutating persistent game state.

These tools modify the GameState held in game_loop.py via a shared mutable
container. The GM calls them mid-turn when facts change (character dies,
new lore discovered, tone shift needed, etc.).
"""

from __future__ import annotations

from strands import tool

# Shared mutable state injected by game_loop before each agent call.
# This avoids passing GameState through tool signatures (would inflate tokens).
_state_holder: dict = {}


def bind_state(state_holder: dict) -> None:
    """Bind the shared state dict before each GM turn. Called by game_loop."""
    _state_holder.clear()
    _state_holder.update(state_holder)


@tool
def update_memory(content: str) -> str:
    """Replace the persistent memory block with new content.

    Call this when important facts change: a character dies, the player
    gains a key item, a secret is revealed. Keep it concise (< 200 words).

    Args:
        content: New memory block text. Replaces the current memory entirely.

    Returns:
        Confirmation string.
    """
    _state_holder["memory"] = content.strip()
    return f"Memory updated ({len(content.split())} words)."


@tool
def update_authors_note(content: str) -> str:
    """Update the author's note to shift tone, pacing, or genre.

    Use this when the scene mood needs to change: ramp up tension before
    combat, soften after a dramatic reveal, signal a genre shift.

    Args:
        content: New author's note text (keep under 50 words for best effect).

    Returns:
        Confirmation string.
    """
    _state_holder["author_note"] = content.strip()
    return f"Author's note updated."


@tool
def add_world_info_entry(keyword: str, content: str) -> str:
    """Register a new World Info entry for future keyword-triggered injection.

    Use this to permanently encode lore that emerged during play: a new
    location, a named NPC, a faction the player encountered.

    Args:
        keyword: The trigger keyword (case-insensitive, whole-word match).
        content: The lore text to inject when this keyword appears.

    Returns:
        Confirmation string.
    """
    entries: list = _state_holder.setdefault("world_info_entries", [])
    # Replace if keyword already exists
    for entry in entries:
        if entry["keyword"].lower() == keyword.lower():
            entry["content"] = content.strip()
            return f"World info entry updated for keyword: {keyword!r}."
    entries.append({"keyword": keyword.strip(), "content": content.strip()})
    return f"World info entry added for keyword: {keyword!r}."
