"""Narrative tools — wrappers for calling sub-agents as tools.

These are thin wrappers used by the OrchestratorAgent to invoke
LoreInjector, Narrator, and Evaluator agents. See AGENT_DESIGN.md §2.1.

Note: The actual agent instances are injected at runtime by the orchestrator.
These tools use the @tool(context=True) pattern to access shared state.
"""

from __future__ import annotations

import json

from strands import tool


@tool(name="call_lore_injector")
def call_lore_injector(beat_text: str, beat_index: int, characters_json: str, world_info: str) -> str:
    """Build lore context for the current beat by scanning for character triggers.

    Args:
        beat_text: Full text of the current beat instruction.
        beat_index: 0-based index of the current beat.
        characters_json: Serialised character card list (JSON array).
        world_info: Global world-info content.

    Returns:
        Formatted lore block ready for narrator prompt injection.
    """
    # This is a placeholder — the actual implementation delegates to LoreInjectorAgent.
    # The orchestrator replaces this tool with one that calls the real agent.
    return ""


@tool(name="call_narrator")
def call_narrator(narrator_context_json: str) -> str:
    """Generate prose for one beat using the NarratorAgent.

    Args:
        narrator_context_json: Serialised NarratorContext (JSON).

    Returns:
        Written prose for this beat.
    """
    return ""


@tool(name="call_evaluator")
def call_evaluator(beat_instruction: str, prose_output: str, writing_style: str, prior_summary: str) -> str:
    """Evaluate beat prose quality using the EvaluatorAgent.

    Args:
        beat_instruction: Original beat text from [scene-beats].
        prose_output: Prose written by NarratorAgent.
        writing_style: [writing-style] section content.
        prior_summary: Rolling summary of prior beats (may be empty).

    Returns:
        Serialised EvalResult JSON.
    """
    return ""
