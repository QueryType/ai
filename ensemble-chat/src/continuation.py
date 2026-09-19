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

# F2F: addressing-by-name is common in ordinary dialogue ("Dev, you should..."),
# so it can't be a guaranteed continuation the way it first shipped — that
# turned into every human line cascading through the whole cast, since each
# hop just handed a fresh, near-certain excuse to keep going. Boosted over the
# base spontaneous chance (still favoring a genuine address) but decayed per
# depth, so the first hop is likely, a five-deep chain is rare, not routine.
# Retuned 2026-09-16 after reading real transcripts — see PLAN_F2F.md.
_F2F_ADDRESSED_RATIO = 2.5
_F2F_DEPTH_DECAY = 0.5


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
    # Holds in every mode — this is the one invariant F2F's looser tuning
    # below does not relax. See PLAN_F2F.md.
    if text.endswith("?") and other is None:
        return None

    if scenario.mode == "f2f":
        return _decide_f2f(scenario, other, speaker, depth, cfg, rng)

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


def _decide_f2f(
    scenario: Scenario,
    other: Character | None,
    speaker: Character,
    depth: int,
    cfg: Config,
    rng: random.Random,
) -> Continuation | None:
    """Real in-person talk overlaps constantly and rarely uses names, so
    addressing is a bonus signal here, not a guarantee — both branches decay
    with depth so a chain tapers off rather than running to the cap by
    default. See PLAN_F2F.md."""
    if depth >= cfg.f2f_continuation_max:
        return None

    decay = _F2F_DEPTH_DECAY**depth

    if other is not None:
        chance = min(1.0, cfg.f2f_continuation_chance * _F2F_ADDRESSED_RATIO) * decay
        if rng.random() < chance:
            return Continuation(
                speaker=other.name,
                reason="addressed",
                directive=f"Reply to what {speaker.name} just said.",
            )
        return None

    if rng.random() < cfg.f2f_continuation_chance * decay:
        return Continuation(
            speaker=None,
            reason="spontaneous",
            directive="Jump in naturally, reacting to what was just said.",
        )

    return None


def decide_autonomous(
    scenario: Scenario,
    result: TurnResult,
    cfg: Config,
    rng: random.Random,
) -> Continuation:
    """The cast keeps talking with no human to hand back to and no per-turn
    cap — the autopilot driver's own turn/time budget is the only stop
    condition (see src/autopilot.py). Deliberately separate from decide()
    rather than a flag on it, so the interactive hand-back-to-human
    invariant and the per-turn continuation cap stay exactly as tested for
    every existing caller. Reuses the same addressed/joinder/spontaneous
    shape so autonomous chatter still feels selector-weighted, not uniform
    random, and always returns a Continuation (never None)."""
    text = result.text.strip()
    speaker = result.speaker
    other = _addressed(scenario, text, exclude=speaker.name)

    if scenario.mode == "f2f":
        if other is not None:
            chance = min(1.0, cfg.f2f_continuation_chance * _F2F_ADDRESSED_RATIO)
            if rng.random() < chance:
                return Continuation(
                    speaker=other.name,
                    reason="addressed",
                    directive=f"Reply to what {speaker.name} just said.",
                )
        if rng.random() < min(1.0, cfg.f2f_continuation_chance * _SPONTANEOUS_RATIO * 2):
            return Continuation(
                speaker=None,
                reason="spontaneous",
                directive="Jump in naturally, reacting to what was just said, or start a new beat.",
            )
        return Continuation(
            speaker=speaker.name,
            reason="joinder",
            directive="Add one short follow-up to what you just said.",
        )

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
    return Continuation(
        speaker=None,
        reason="spontaneous",
        directive="Start a new thought, or reply to what was just said, in character.",
    )
