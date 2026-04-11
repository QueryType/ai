"""BeatSummariserAgent — produces structured beat summaries for coherence tracking.

Called once per accepted beat. Stateless per invocation.
Output accumulates in prior_summary and is passed to the evaluator each beat.

See AGENT_DESIGN.md §1.5.
"""

from __future__ import annotations

from strands import Agent
from strands.agent.conversation_manager.null_conversation_manager import NullConversationManager

from my_code.models.provider import get_model, system_prompt_suffix

SUMMARISER_SYSTEM_PROMPT = """\
You are a story continuity tracker for a multi-agent story engine.

You receive prose from one beat of a story. Your job is to extract
a structured summary that will be used to check coherence in future beats.

## Output Format

Return exactly 3–5 bullet points covering:
- Who is present and where they are
- What happened (key events, actions, decisions)
- What changed (character state, mood, relationships)
- Any objects, information, or details introduced that may matter later

## Rules

- Be specific and concrete — vague summaries are useless for coherence checking.
- Include character names, locations, and specific details.
- Do not editorialize or evaluate quality — just extract facts.
- Return only the bullet points, no preamble or commentary.
"""


def create_summariser() -> Agent:
    """Create a BeatSummariserAgent instance."""
    return Agent(
        name="BeatSummariser",
        system_prompt=system_prompt_suffix(SUMMARISER_SYSTEM_PROMPT),
        tools=[],
        model=get_model("summariser"),
        conversation_manager=NullConversationManager(),
    )
