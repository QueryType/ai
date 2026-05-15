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
   in the beat instruction? Call check_beat_coverage(covered=..., reason=...)
   with covered=True only if the core event clearly happened.

2. **Style Compliance** — Does the prose match the writing style directives?
   Check for POV consistency, tense, show-don't-tell, dialogue formatting,
   sentence variety. Call check_style_compliance(compliant=..., issues_json=...)
   with compliant=True if no clear violations exist, or compliant=False with a
   JSON array of specific issues (e.g. '["passive voice overused", "POV slip"]').

3. **Coherence** — Is the prose consistent with what happened in prior beats?
   Read the prior beat summaries carefully. Check for contradictions: characters
   in the wrong place, events that didn't happen yet, facts established differently.
   Call check_coherence(coherent=..., reason=...) — coherent=True only if you find
   no meaningful contradictions. First beat auto-passes.

4. **Final Verdict** — Call emit_eval_result(beat_coverage=..., style_compliant=...,
   coherent=..., issues_json=...) with the three boolean results and a JSON array
   of all specific issues found.

## Important

- Do NOT include prose text or beat instructions in tool call arguments — only
  pass booleans, reason strings, and issues arrays. The content is already in context.
- Be strict on beat coverage — the event MUST happen in the prose.
- Be moderate on style — flag clear violations, not minor stylistic choices.
- Be strict on coherence when prior summaries exist — flag real contradictions only.
- Be lenient on coherence for early beats with little prior context.
- Return ONLY the output of emit_eval_result. Do not add commentary.
"""


EVALUATOR_SINGLE_PASS_SYSTEM_PROMPT = """\
You are the Evaluator — a quality gate for a story engine.

You receive a beat instruction, prose output, writing style directives, and prior
beat summaries. Evaluate using the same rubric:

1. Beat coverage (strict): the core event in the beat instruction must happen.
2. Style compliance (moderate): flag clear directive violations only.
3. Coherence (strict with prior context): flag real contradictions only.

Return ONLY valid JSON (no markdown, no extra text) with this exact schema:
{
   "result": "pass" | "retry",
   "score": number,
   "reason": string,
   "beat_coverage": boolean,
   "style_compliant": boolean,
   "coherent": boolean,
   "issues": string[]
}

Rules:
- score must be in [0.0, 1.0] and should reflect the three booleans.
- result must be "pass" only if all three booleans are true; otherwise "retry".
- issues should contain specific, concise problems. Use [] when all checks pass.
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


def create_evaluator_single_pass() -> Agent:
   """Create evaluator variant that returns final JSON directly without tools.

   Used as a fallback when tool-calling loops inflate context and trigger
   provider-side prompt-length errors.
   """
   return Agent(
      name="EvaluatorSinglePass",
      system_prompt=system_prompt_suffix(EVALUATOR_SINGLE_PASS_SYSTEM_PROMPT),
      tools=[],
      model=get_model("evaluator"),
      conversation_manager=NullConversationManager(),
   )
