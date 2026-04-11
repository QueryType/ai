"""Evaluator tools — beat coverage, style compliance, coherence, result emission.

Owned by EvaluatorAgent. See AGENT_DESIGN.md §2.4.

Tool signatures deliberately do NOT include prose_output, beat_instruction, or
writing_style as parameters. The LLM already has those in its context window —
repeating them as tool call arguments would inflate each generated tool call by
~1200 tokens × 3 calls = ~3600 tokens, which blows past ctx=4096 every beat.
"""

from __future__ import annotations

import json

from strands import tool


@tool
def check_beat_coverage(covered: bool, reason: str) -> str:
    """Record whether the prose covers the narrative event in the beat instruction.

    Read the beat instruction and prose carefully, then call this tool with
    your verdict. covered=True only if the core event clearly happened.

    Args:
        covered: True if the prose covers the beat event, False otherwise.
        reason: Explanation of the coverage verdict.

    Returns:
        JSON with 'covered' (bool) and 'reason' (str).
    """
    return json.dumps({"covered": covered, "reason": reason})


@tool
def check_style_compliance(compliant: bool, issues_json: str) -> str:
    """Record whether the prose matches the declared writing style.

    Read the prose and writing style directives carefully, then call this tool
    with your verdict. Check for POV consistency, tense, show-don't-tell,
    dialogue formatting, sentence variety.

    Args:
        compliant: True if the prose matches the style directives, False otherwise.
        issues_json: JSON array of specific style issues found (empty array if compliant).

    Returns:
        JSON with 'compliant' (bool) and 'issues' (list of strings).
    """
    issues = json.loads(issues_json) if issues_json else []
    return json.dumps({"compliant": compliant, "issues": issues})


@tool
def check_coherence(coherent: bool, reason: str) -> str:
    """Record the coherence assessment for this beat vs prior beats.

    Read the prose and prior beat summaries carefully. Check for contradictions:
    characters in the wrong place, events that didn't happen yet, facts established
    differently. Auto-passes if prior_summary is empty (first beat).

    Args:
        coherent: True if the prose is consistent with prior beats, False if contradictions found.
        reason: Explanation of the coherence verdict, or specific contradictions found.

    Returns:
        JSON with 'coherent' (bool) and 'reason' (str).
    """
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
