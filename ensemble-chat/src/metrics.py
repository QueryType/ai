"""Deterministic quality metrics over a generated transcript.

These measure mechanical texture — repetition, length, assistant-voice leakage,
turn distribution. They do NOT measure whether the writing is good or whether a
character is well portrayed. A high score means the output does not read like an
LLM; judging whether it reads like *these people* still needs your eyes.

Everything here is computed without a model, so scores are cheap, reproducible
and can't flatter themselves.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from src.cast import Character
from src.register import ASSISTANT_TICS
from src.state import State

_WORD = re.compile(r"[a-z']+")
_NARRATION = re.compile(r"\*[^*\n]+\*|^\s*\([^)]+\)\s*$", re.MULTILINE)

_BREVITY_GOOD = 350
_BREVITY_BAD = 700
_QUESTION_OK = 0.5
_TTR_TARGET = 0.45


@dataclass
class Turn:
    speaker: str
    text: str
    elapsed: float


@dataclass
class Metric:
    name: str
    score: float
    detail: str
    weight: float = 1.0
    applicable: bool = True


def _opener(text: str, words: int = 3) -> str:
    return " ".join(_WORD.findall(text.lower())[:words])


def tic_free(turns: list[Turn]) -> Metric:
    hits = [t for t in turns if any(tic in t.text.lower() for tic in ASSISTANT_TICS)]
    score = 1.0 - len(hits) / len(turns) if turns else 0.0
    detail = f"{len(hits)}/{len(turns)} replies carry assistant-voice"
    if hits:
        detail += f' — e.g. "{hits[0].text[:60]}…"'
    return Metric("tic_free", score, detail, weight=2.0)


def brevity(turns: list[Turn]) -> Metric:
    def one(text: str) -> float:
        n = len(text)
        if n <= _BREVITY_GOOD:
            return 1.0
        if n >= _BREVITY_BAD:
            return 0.0
        return 1.0 - (n - _BREVITY_GOOD) / (_BREVITY_BAD - _BREVITY_GOOD)

    if not turns:
        return Metric("brevity", 0.0, "no replies", 1.5)
    scores = [one(t.text) for t in turns]
    lengths = [len(t.text) for t in turns]
    mean = sum(lengths) / len(lengths)
    return Metric(
        "brevity",
        sum(scores) / len(scores),
        f"mean {mean:.0f} chars, longest {max(lengths)}",
        weight=1.5,
    )


def opener_variety(turns: list[Turn]) -> Metric:
    """The rut metric — a character reusing one sentence shape every turn."""
    by_speaker: dict[str, list[str]] = {}
    for t in turns:
        by_speaker.setdefault(t.speaker, []).append(_opener(t.text))

    ratios, details = [], []
    for name, openers in sorted(by_speaker.items()):
        if len(openers) < 3:
            continue
        unique = len(set(openers))
        ratios.append(unique / len(openers))
        details.append(f"{name} {unique}/{len(openers)}")

    if not ratios:
        # Excluded rather than passed — too little data is not evidence of variety.
        return Metric("opener_variety", 0.0, "too few replies per character to judge",
                      2.0, applicable=False)
    return Metric("opener_variety", sum(ratios) / len(ratios), ", ".join(details), weight=2.0)


def question_balance(turns: list[Turn]) -> Metric:
    """Catches the interrogation failure: nearly every reply ending in '?'."""
    if not turns:
        return Metric("question_balance", 0.0, "no replies", 1.5)
    rate = sum(1 for t in turns if t.text.rstrip().endswith("?")) / len(turns)
    score = 1.0 if rate <= _QUESTION_OK else max(0.0, 1.0 - (rate - _QUESTION_OK) / _QUESTION_OK)
    return Metric("question_balance", score, f"{rate:.0%} of replies end in a question", 1.5)


def no_narration(turns: list[Turn]) -> Metric:
    hits = [t for t in turns if _NARRATION.search(t.text)]
    score = 1.0 - len(hits) / len(turns) if turns else 0.0
    return Metric("no_narration", score, f"{len(hits)}/{len(turns)} contain stage directions", 1.0)


def voice_integrity(turns: list[Turn], names: list[str]) -> Metric:
    """Speaking as someone else, or narrating your own name like a script."""
    hits = []
    for t in turns:
        others = [n for n in names if n != t.speaker]
        wrote_other = any(re.search(rf"\b{re.escape(n)}\s*:", t.text) for n in others)
        labelled_self = re.search(
            rf"^\s*{re.escape(t.speaker)}\s*:", t.text, re.MULTILINE
        ) is not None
        if wrote_other or labelled_self:
            hits.append(t)
    score = 1.0 - len(hits) / len(turns) if turns else 0.0
    return Metric("voice_integrity", score, f"{len(hits)}/{len(turns)} break character boundaries", 1.5)


def lexical_diversity(turns: list[Turn]) -> Metric:
    words = [w for t in turns for w in _WORD.findall(t.text.lower())]
    if not words:
        return Metric("lexical_diversity", 0.0, "no words", 1.0)
    ttr = len(set(words)) / len(words)
    return Metric(
        "lexical_diversity",
        min(1.0, ttr / _TTR_TARGET),
        f"type-token {ttr:.2f} over {len(words)} words (falls naturally as a chat gets longer)",
        weight=1.0,
    )


def turn_distribution(turns: list[Turn], characters: list[Character]) -> Metric:
    """How closely speaking shares track the weights in the scenario."""
    if not turns:
        return Metric("turn_distribution", 0.0, "no replies", 1.0)
    total_weight = sum(c.weight for c in characters) or 1.0
    expected = {c.name: c.weight / total_weight for c in characters}
    actual: dict[str, int] = {}
    for t in turns:
        actual[t.speaker] = actual.get(t.speaker, 0) + 1

    deviation = sum(abs(actual.get(n, 0) / len(turns) - share) for n, share in expected.items()) / 2
    shares = ", ".join(f"{n} {actual.get(n, 0)}" for n in expected)
    return Metric("turn_distribution", 1.0 - deviation, f"{shares} (of {len(turns)})", weight=1.0)


def state_health(state: State, expect: dict[str, int]) -> Metric:
    """Did memory capture what this script deliberately put in front of it.

    The script is fixed, so we know what should have been picked up — an
    explicit request for a reminder should produce a promise, and repeated talk
    about not eating or sleeping should produce a trait.
    """
    counts = {
        "traits": len(state.traits),
        "threads": len(state.threads),
        "promises": len(state.promises),
    }
    checks = [min(1.0, counts[k] / want) for k, want in expect.items() if want]
    score = (sum(checks) / len(checks)) if checks else (1.0 if state.updated else 0.0)

    detail = ", ".join(
        f"{counts[k]} {k}" + (f" (expected {expect[k]})" if expect.get(k) else "")
        for k in counts
    )
    return Metric("state_health", score, detail, weight=2.0)


def evaluate(
    turns: list[Turn],
    characters: list[Character],
    state: State,
    expect: dict[str, int] | None,
    mode: str = "text",
) -> tuple[list[Metric], float]:
    names = [c.name for c in characters]
    metrics = [
        tic_free(turns),
        opener_variety(turns),
        question_balance(turns),
        voice_integrity(turns, names),
        lexical_diversity(turns),
        turn_distribution(turns, characters),
    ]
    # brevity and no_narration encode texting-mode expectations (short lines,
    # no asterisk actions) that F2F's register deliberately violates on
    # purpose — see PLAN_F2F.md.
    if mode != "f2f":
        metrics.append(brevity(turns))
        metrics.append(no_narration(turns))
    if expect is not None:
        metrics.append(state_health(state, expect))

    scored = [m for m in metrics if m.applicable]
    total_weight = sum(m.weight for m in scored) or 1.0
    composite = sum(m.score * m.weight for m in scored) / total_weight * 100
    return metrics, composite
