"""Unattended driver loops — BACKLOG.md's "Autonomous mode" (no human at
all) and "Self-Auto mode" (a human is still in the scene, but their lines
are generated too). Both reuse driver.play()/continue_chain() exactly as the
interactive terminal loop does — no engine, prompt, or history changes;
this is pure orchestration, same as continuation.py itself. Each stops on a
turn cap or a time cap (CHAT_AUTOPILOT_MAX_TURNS/_SECONDS), or Ctrl+C.
"""
from __future__ import annotations

import random
import time
from pathlib import Path

from src.continuation import decide_autonomous
from src.driver import continue_chain, play
from src.engine import Engine
from src.human_agent import generate_human_line
from src.session import Session
from src.ui.terminal import Terminal

_rng = random.Random()


async def run_autonomous(
    ui: Terminal,
    engine: Engine,
    session: Session,
    save_path: Path,
    max_turns: int,
    max_seconds: float,
) -> None:
    """No human turn ever happens. Bootstraps with the same empty-input
    call /next already uses, then keeps forcing the next speaker via
    decide_autonomous() (unbounded, no hand-back-to-human) instead of the
    interactive, capped decide()."""
    start = time.monotonic()
    result = await play(ui, engine, session, save_path, "")
    while engine.turn_count < max_turns and (time.monotonic() - start) < max_seconds:
        cont = decide_autonomous(engine.scenario, result, engine.cfg, _rng)
        result = await play(
            ui, engine, session, save_path, "",
            speaker=cont.speaker, directive=cont.directive, is_continuation=True,
        )


async def run_self_auto(
    ui: Terminal,
    engine: Engine,
    session: Session,
    save_path: Path,
    max_turns: int,
    max_seconds: float,
) -> None:
    """You're still a participant, but your line is generated instead of
    typed. continuation.py's interactive hand-back-to-human invariant is
    untouched — it's simply satisfied by generate_human_line() instead of
    stdin, so the normal capped decide() and continue_chain() still apply."""
    start = time.monotonic()
    while engine.turn_count < max_turns and (time.monotonic() - start) < max_seconds:
        line = await generate_human_line(engine)
        if not line:
            break
        ui.show_human(line)
        result = await play(ui, engine, session, save_path, line)
        await continue_chain(ui, engine, session, save_path, result)
