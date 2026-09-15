"""Decide whether a character keeps talking without the human typing again.

Pure decision logic, no I/O — see PLAN_CONTINUATIONS.md. Delivery (calling
Engine.turn again) is the caller's job, kept in src/__main__.py so Tier 2/3
input layers can reuse this unchanged.
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass

from src.cast import Character, Scenario
from src.config import Config
from src.engine import TurnResult

# Ratios against cfg.continuation_chance, not standalone constants, so the
# single CHAT_CONTINUATION_CHANCE knob scales both. At the default of 0.25
# these land near the ~15%/~20% the design settled on.
_JOINDER_RATIO = 0.6
_SPONTANEOUS_RATIO = 0.8


@dataclass(frozen=True)
class Continuation:
    speaker: str | None  # None = let the selector pick
    reason: str  # addressed | joinder | spontaneous
    directive: str  # extra_directive passed to Engine.turn


def _addressed(scenario: Scenario, text: str, exclude: str) -> Character | None:
    lowered = text.lower()
    for c in scenario.characters:
        if c.name == exclude:
            continue
        if re.search(rf"\b{re.escape(c.name.lower())}\b", lowered):
            return c
    return None


def decide(
    scenario: Scenario,
    result: TurnResult,
    depth: int,
    cfg: Config,
    rng: random.Random,
) -> Continuation | None:
    text = result.text.strip()
    speaker = result.speaker
    other = _addressed(scenario, text, exclude=speaker.name)

    # The human must stay a participant: a question aimed at them ends the chain.
    if text.endswith("?") and other is None:
        return None

    if depth >= cfg.continuation_max:
        return None

    if other is not None:
        return Continuation(
            speaker=other.name,
            reason="addressed",
            directive=f"Reply to what {speaker.name} just said.",
        )

    if rng.random() < cfg.continuation_chance * _JOINDER_RATIO:
        return Continuation(
            speaker=speaker.name,
            reason="joinder",
            directive="Add one short follow-up to what you just said.",
        )

    if rng.random() < cfg.continuation_chance * _SPONTANEOUS_RATIO:
        return Continuation(
            speaker=None,
            reason="spontaneous",
            directive="Jump in naturally, reacting to what was just said.",
        )

    return None
