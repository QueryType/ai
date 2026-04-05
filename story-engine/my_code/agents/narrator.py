"""NarratorAgent — the writer.

Produces prose for one beat at a time. Maintains voice continuity via
conversation history using SummarizingConversationManager.

Constructed once per scene run, not per beat. See AGENT_DESIGN.md §1.3.
"""

from __future__ import annotations

from strands import Agent
from strands.agent.conversation_manager.summarizing_conversation_manager import SummarizingConversationManager

from my_code.models.data_models import ParsedScene
from my_code.models.provider import get_model, system_prompt_suffix


def _build_narrator_system_prompt(scene: ParsedScene) -> str:
    """Assemble the narrator's system prompt from parsed scene data.

    The static context (narrator identity, writing style, world info, scenario,
    scene setup, writing instructions) is baked into the system prompt at
    construction time — it does not travel with every beat.
    """
    parts = [scene.narrator_prompt]

    parts.append(f"\n\n## Writing Style\n{scene.writing_style}")

    parts.append(f"\n\n## World\n{scene.world_info}")

    setup = scene.scene_setup
    if setup.location or setup.time or setup.atmosphere:
        parts.append("\n\n## Scene Setup")
        if setup.location:
            parts.append(f"\nLocation: {setup.location}")
        if setup.time:
            parts.append(f"\nTime: {setup.time}")
        if setup.atmosphere:
            parts.append(f"\nAtmosphere: {setup.atmosphere}")

    parts.append(f"\n\n## Scenario\n{scene.scenario}")

    if scene.writing_instructions:
        parts.append(f"\n\n## Writing Instructions\n{scene.writing_instructions}")

    pov = scene.meta.pov
    parts.append(f"\n\n## POV\nWrite in {pov}.")

    if scene.meta.nsfw:
        parts.append("\n\nNSFW content is permitted where narratively appropriate.")
    else:
        parts.append("\n\nKeep content appropriate — no explicit/NSFW material.")

    target = scene.meta.target_length
    beat_count = len(scene.beats)
    words_per_beat = target // beat_count if beat_count else target
    parts.append(
        f"\n\n## Length Target\n"
        f"Target ~{words_per_beat} words per beat ({target} total for {beat_count} beats)."
    )

    # Player character rule
    pc_names = [c.name for c in scene.characters if c.role == "player-character"]
    if pc_names:
        names = ", ".join(pc_names)
        parts.append(
            f"\n\n## Player Character Rule\n"
            f"You may describe {names}'s perceptions, reactions, and emotions, "
            f"but NEVER make decisions or take actions on their behalf."
        )

    return "\n".join(parts)


def create_narrator(scene: ParsedScene) -> Agent:
    """Create a NarratorAgent with scene context baked into its system prompt.

    The narrator is created once per scene run. Its conversation history
    persists across beats via SummarizingConversationManager.
    """
    return Agent(
        name="Narrator",
        system_prompt=system_prompt_suffix(_build_narrator_system_prompt(scene)),
        tools=[],  # pure generation — no tools
        model=get_model("narrator"),
        conversation_manager=SummarizingConversationManager(
            summary_ratio=0.3,
            preserve_recent_messages=10,
        ),
    )
