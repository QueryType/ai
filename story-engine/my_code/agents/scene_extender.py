"""SceneExtenderAgent — generates planning sections for a sequel scene file.

Single-shot, no tools, stateless. Uses the summariser model from env config.
Input: previous scene file text + user brief.
Output: JSON with title, prior_context, scene_setup, scenario, scene_beats,
        writing_instructions.
"""

from __future__ import annotations

from strands import Agent
from strands.agent.conversation_manager.null_conversation_manager import NullConversationManager

from my_code.models.provider import get_model, system_prompt_suffix

SCENE_EXTENDER_SYSTEM_PROMPT = """\
You are a story continuation planner for a multi-agent story engine.

You receive a complete scene input file (the previous part of a story) and a brief
description of what the next part should cover. Your job is to generate the planning
sections for the next scene file.

## Output Format

Return ONLY a valid JSON object with these exact keys:

{
  "title": "Short evocative title for this part (5-8 words)",
  "prior_context": "3-5 bullet points (one per line, each starting with -) summarising what happened in the previous scene: concrete events, character states, unresolved threads. Use real character names and specific details. No vague phrases like 'tension was established'.",
  "scene_setup": {
    "location": "Where this scene takes place — be specific about the physical space",
    "time": "Time of day and how much time has passed since the previous scene ended",
    "atmosphere": "Dominant mood and sensory environment — what the place feels, smells, sounds like"
  },
  "scenario": "2-4 sentences describing the exact situation at the start of this scene, picking up directly from where the previous scene ended. Include character positions and immediate emotional state.",
  "scene_beats": [
    {"text": "Concrete beat description — what happens, what changes, what decision or revelation drives it", "pause": false},
    {"text": "...", "pause": true}
  ],
  "writing_instructions": "Specific craft and tone notes for this installment: what to open on, what to avoid, what texture to aim for"
}

## Rules

- scene_beats: exactly 4-5 beats. Each beat must be a concrete story event, not a vague direction.
- Mark pause: true on exactly 1-2 beats where a natural human review point falls (after a key confrontation, revelation, or decision).
- prior_context: bullet points only, concrete and specific.
- scenario: must start exactly where the previous scene's last beat ended. No unexplained time skips.
- Return ONLY the JSON object. No preamble, no commentary, no markdown fences.
"""


def create_scene_extender() -> Agent:
    return Agent(
        name="SceneExtender",
        system_prompt=system_prompt_suffix(SCENE_EXTENDER_SYSTEM_PROMPT),
        tools=[],
        model=get_model("summariser"),
        conversation_manager=NullConversationManager(),
    )
