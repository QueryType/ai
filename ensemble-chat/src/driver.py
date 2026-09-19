"""Shared turn-orchestration helpers: streaming/saving/warnings around a
turn, and the decide()-driven continuation chain. Used by the terminal's
interactive loop and by autopilot.py's unattended loops, so both go through
the exact same path — kept out of Engine per PLAN_CONTINUATIONS.md ("this is
orchestration, not turn generation").
"""
from __future__ import annotations

import random
from collections.abc import Awaitable, Callable
from pathlib import Path

from src.bootstrap import save_session
from src.cast import Character
from src.continuation import decide
from src.engine import Engine, TurnResult
from src.session import Session
from src.ui.terminal import Terminal

_continuation_rng = random.Random()

Run = Callable[
    [Callable[[str], None], Callable[[Character], None] | None], Awaitable[TurnResult]
]


async def run_turn(ui: Terminal, engine: Engine, session: Session, save_path: Path, run: Run) -> TurnResult:
    """Shared by `play` and `regenerate_turn` — both just differ in which
    Engine call `run` wraps (turn() vs. regenerate()); the streaming/
    saving/warning treatment is identical either way."""
    if engine.scenario.mode == "f2f":
        printer = ui.begin_stream()
        result = await run(printer.on_chunk, printer.on_speaker)
        printer.finish()
        # Saved here, not just on clean exit — a killed terminal, a double
        # Ctrl-C, a crash, all previously lost the whole session, not just the
        # in-flight turn. See BACKLOG.md.
        save_session(engine, session, save_path)
        ui.show_warnings(result)
        ui.console.print()
    else:
        with ui.console.status("", spinner="dots"):
            result = await run(lambda _: None, None)
        save_session(engine, session, save_path)
        await ui.show(result)
    if engine.state_error:
        ui.console.print(f"[dim red]state update failed: {engine.state_error}[/dim red]\n")
    return result


async def play(
    ui: Terminal,
    engine: Engine,
    session: Session,
    save_path: Path,
    text: str,
    speaker: str | None = None,
    directive: str = "",
    is_continuation: bool = False,
    image: bytes | None = None,
) -> TurnResult:
    if is_continuation:
        await ui.pause_for_continuation()
    return await run_turn(
        ui,
        engine,
        session,
        save_path,
        lambda on_chunk, on_speaker: engine.turn(
            text,
            on_chunk,
            force_speaker=speaker,
            extra_directive=directive,
            image=image,
            on_speaker=on_speaker,
        ),
    )


async def regenerate_turn(
    ui: Terminal, engine: Engine, session: Session, save_path: Path, guidance: str
) -> TurnResult:
    """Redo the last reply, same speaker — only valid while it's still the
    most recent thing that happened. The terminal can't un-print what's
    already on screen, so the new reply just appears below the old one
    rather than replacing it (the web UI can and does replace it)."""
    return await run_turn(
        ui,
        engine,
        session,
        save_path,
        lambda on_chunk, on_speaker: engine.regenerate(on_chunk, guidance=guidance, on_speaker=on_speaker),
    )


async def continue_chain(
    ui: Terminal, engine: Engine, session: Session, save_path: Path, result: TurnResult
) -> TurnResult:
    """Let characters answer each other after a turn, capped and biased to stop.

    Kept out of Engine — this is orchestration, not turn generation. See
    PLAN_CONTINUATIONS.md. Returns the final result so callers (including the
    idle-timer check) can track what the conversation currently stands on.
    """
    depth = 0
    while True:
        cont = decide(engine.scenario, result, depth, engine.cfg, _continuation_rng)
        if cont is None:
            return result
        result = await play(
            ui, engine, session, save_path, "",
            speaker=cont.speaker, directive=cont.directive, is_continuation=True,
        )
        depth += 1


async def raise_due_promises(
    ui: Terminal, engine: Engine, session: Session, save_path: Path
) -> TurnResult | None:
    result = None
    for promise in engine.state.due_promises():
        promise.fulfilled = True
        result = await play(
            ui,
            engine,
            session,
            save_path,
            "",
            speaker=promise.speaker or None,
            directive=(
                f'You said you would do this: "{promise.text}". '
                "Bring it up now, in your own words, as if it just occurred to you."
            ),
        )
    return result
