"""EvaluatorAgent — quality gate.

Reads beat intent vs prose output and returns pass/retry with structured feedback.
Stateless per invocation. See AGENT_DESIGN.md §1.4.
"""

from __future__ import annotations

from strands import Agent
from strands.agent.conversation_manager.null_conversation_manager import NullConversationManager

from my_code.models.provider import get_model, system_prompt_suffix
from my_code.tools.eval_tools import (
    check_beat_coverage,
    check_coherence,
    check_style_compliance,
    emit_eval_result,
)

EVALUATOR_SYSTEM_PROMPT = """\
You are the Evaluator — a quality gate for a story engine.

You receive a beat instruction (what should happen) and the prose output
(what was written). Your job is to run three checks and emit a final verdict.

## Process

1. **Beat Coverage** — Did the prose cover the core narrative event described
   in the beat instruction? Call check_beat_coverage with covered=True only if
   the core event clearly happened; pass covered=False and a reason if it did not.

2. **Style Compliance** — Does the prose match the writing style directives?
   Check for POV consistency, tense, show-don't-tell, dialogue formatting,
   sentence variety. Call check_style_compliance with compliant=True if no clear
   violations exist, or compliant=False with a JSON array of specific issues.

3. **Coherence** — Is the prose consistent with what happened in prior beats?
   Read the prior beat summaries carefully. Check for contradictions: characters
   in the wrong place, events that didn't happen yet, facts that were established
   differently. Call check_coherence with your verdict — pass coherent=True only
   if you find no meaningful contradictions. If prior_summary is empty (first beat),
   the tool will auto-pass regardless of what you pass.

4. **Final Verdict** — Call emit_eval_result with the three boolean results
   and a list of specific issues found.

## Important

- Be strict on beat coverage — the event MUST happen in the prose.
- Be moderate on style — flag clear violations, not minor stylistic choices.
- Be strict on coherence when prior summaries exist — flag real contradictions, not stylistic choices.
- Be lenient on coherence for early beats with little prior context.
- When calling check tools, pass the actual prose and instructions as arguments.
  Then based on your analysis, call emit_eval_result with your boolean assessments.
- Return ONLY the output of emit_eval_result. Do not add commentary.
"""


def create_evaluator() -> Agent:
    """Create a fresh EvaluatorAgent instance."""
    return Agent(
        name="Evaluator",
        system_prompt=system_prompt_suffix(EVALUATOR_SYSTEM_PROMPT),
        tools=[check_beat_coverage, check_style_compliance, check_coherence, emit_eval_result],
        model=get_model("evaluator"),
        conversation_manager=NullConversationManager(),
    )
