"""Evaluator tools — beat coverage, style compliance, coherence, result emission.

Owned by EvaluatorAgent. See AGENT_DESIGN.md §2.4.
"""

from __future__ import annotations

import json

from strands import tool


@tool
def check_beat_coverage(beat_instruction: str, prose_output: str, covered: bool, reason: str) -> str:
    """Check whether the prose covers the narrative event in the beat instruction.

    The evaluator agent uses its LLM reasoning to determine coverage,
    then calls this tool to record the structured result.

    Args:
        beat_instruction: The original beat text from [scene-beats].
        prose_output: The prose written by the narrator.
        covered: True if the prose covers the beat event, False otherwise.
        reason: Explanation of the coverage verdict.

    Returns:
        JSON with 'covered' (bool) and 'reason' (str).
    """
    return json.dumps({"covered": covered, "reason": reason})


@tool
def check_style_compliance(prose_output: str, writing_style: str, compliant: bool, issues_json: str) -> str:
    """Check whether the prose matches the declared writing style.

    The evaluator agent reasons about style compliance, then calls this
    tool to record the structured result.

    Args:
        prose_output: The prose written by the narrator.
        writing_style: The [writing-style] section content.
        compliant: True if the prose matches the style directives, False otherwise.
        issues_json: JSON array of specific style issues found (empty array if compliant).

    Returns:
        JSON with 'compliant' (bool) and 'issues' (list of strings).
    """
    issues = json.loads(issues_json) if issues_json else []
    return json.dumps({"compliant": compliant, "issues": issues})


@tool
def check_coherence(prose_output: str, prior_summary: str, coherent: bool, reason: str) -> str:
    """Record the evaluator's coherence assessment for this beat.

    The evaluator agent reasons about whether the prose is consistent with
    prior beat summaries, then calls this tool with its verdict.
    Auto-passes if prior_summary is empty (first beat).

    Args:
        prose_output: The prose written by the narrator.
        prior_summary: Accumulated bullet-point summaries of prior beats.
        coherent: True if the prose is consistent with prior beats, False if contradictions found.
        reason: Explanation of the coherence verdict, or specific contradictions found.

    Returns:
        JSON with 'coherent' (bool) and 'reason' (str).
    """
    if not prior_summary.strip():
        return json.dumps({"coherent": True, "reason": "First beat — no prior context."})
    return json.dumps({"coherent": coherent, "reason": reason})


@tool
def emit_eval_result(beat_coverage: bool, style_compliant: bool, coherent: bool, issues_json: str) -> str:
    """Aggregate check results into a final EvalResult.

    Args:
        beat_coverage: Whether the beat instruction was covered.
        style_compliant: Whether style directives were followed.
        coherent: Whether prose is consistent with prior beats.
        issues_json: JSON array of specific issue strings.

    Returns:
        JSON EvalResult with result, score, reason, and per-check booleans.
    """
    issues = json.loads(issues_json) if issues_json else []
    all_pass = beat_coverage and style_compliant and coherent
    score = sum([beat_coverage, style_compliant, coherent]) / 3.0

    result = {
        "result": "pass" if all_pass else "retry",
        "score": round(score, 2),
        "reason": "All checks passed." if all_pass else "; ".join(issues) if issues else "One or more checks failed.",
        "beat_coverage": beat_coverage,
        "style_compliant": style_compliant,
        "coherent": coherent,
        "issues": issues,
    }
    return json.dumps(result)
