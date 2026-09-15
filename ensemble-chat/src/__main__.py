from __future__ import annotations

import argparse
import asyncio
import random
import time
from pathlib import Path

from src.bootstrap import build_engine, save_session
from src.continuation import decide
from src.engine import Engine, TurnResult
from src.session import Session
from src.ui.terminal import Terminal

_continuation_rng = random.Random()


async def _play(
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
    with ui.console.status("", spinner="dots"):
        result = await engine.turn(
            text, lambda _: None, force_speaker=speaker, extra_directive=directive, image=image
        )
    # Saved here, not just on clean exit — a killed terminal, a double
    # Ctrl-C, a crash, all previously lost the whole session, not just the
    # in-flight turn. See BACKLOG.md.
    save_session(engine, session, save_path)
    await ui.show(result)
    if engine.state_error:
        ui.console.print(f"[dim red]state update failed: {engine.state_error}[/dim red]\n")
    return result


async def _continue(
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
        result = await _play(
            ui, engine, session, save_path, "",
            speaker=cont.speaker, directive=cont.directive, is_continuation=True,
        )
        depth += 1


async def _raise_due_promises(
    ui: Terminal, engine: Engine, session: Session, save_path: Path
) -> TurnResult | None:
    result = None
    for promise in engine.state.due_promises():
        promise.fulfilled = True
        result = await _play(
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


async def run(scenario_arg: str | None, fresh: bool) -> None:
    engine, session, save_path = build_engine(scenario_arg, fresh)
    scenario = engine.scenario

    ui = Terminal(engine)
    ui.banner()

    last_result: TurnResult | None = None

    if session.history:
        ago = time.time() - session.updated_at if session.updated_at else 0
        ui.console.print(
            f"[dim]resumed {len(session.history)} messages"
            + (f", {ago / 3600:.0f}h ago" if ago > 3600 else "")
            + "[/dim]\n"
        )
        last_result = await _raise_due_promises(ui, engine, session, save_path)

    async def on_idle() -> None:
        nonlocal last_result
        if last_result is not None:
            last_result = await _continue(ui, engine, session, save_path, last_result)

    try:
        while True:
            try:
                raw = (
                    await ui.ask(on_idle=on_idle, idle_seconds=engine.cfg.idle_seconds)
                ).strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not raw:
                continue

            if raw in ("/quit", "/exit"):
                break
            if raw == "/who":
                debt = ", ".join(f"{k} {v:.1f}" for k, v in engine.selector.debt.items())
                ui.console.print(f"[dim]debt: {debt} · history: {len(engine.history)} msgs[/dim]\n")
                continue
            if raw == "/state":
                ui.show_state()
                continue
            if raw == "/log":
                ui.show_log()
                continue
            if raw.startswith("/image"):
                if not engine.policy.vision_capable:
                    ui.console.print("[dim red]this model doesn't accept image input[/dim red]\n")
                    continue
                parts = raw.split(None, 2)
                if len(parts) < 2:
                    ui.console.print("[dim red]usage: /image <path> [caption][/dim red]\n")
                    continue
                image_path = Path(parts[1]).expanduser()
                caption = parts[2] if len(parts) > 2 else ""
                if not image_path.is_file():
                    ui.console.print(f"[dim red]no file at {image_path}[/dim red]\n")
                    continue
                result = await _play(
                    ui, engine, session, save_path, caption, image=image_path.read_bytes()
                )
                last_result = await _continue(ui, engine, session, save_path, result)
                continue
            if raw.startswith("/next"):
                parts = raw.split(None, 1)
                name = parts[1].strip() if len(parts) > 1 else None
                if name and not scenario.by_name(name):
                    ui.console.print(f"[dim red]no character named {name!r}[/dim red]\n")
                    continue
                result = await _play(ui, engine, session, save_path, "", speaker=name)
                last_result = await _continue(ui, engine, session, save_path, result)
                continue

            result = await _play(ui, engine, session, save_path, raw)
            last_result = await _continue(ui, engine, session, save_path, result)
    finally:
        with ui.console.status("saving…", spinner="dots"):
            await engine.drain()
        save_session(engine, session, save_path)
        ui.console.print(f"[dim]saved {len(engine.history)} messages -> {save_path}[/dim]")


def run_web(scenario_arg: str | None, fresh: bool, host: str | None, port: int | None) -> None:
    import uvicorn

    from src.ui.web import create_app

    engine, session, save_path = build_engine(scenario_arg, fresh)
    app = create_app(engine, session, save_path)
    uvicorn.run(app, host=host or engine.cfg.web_host, port=port or engine.cfg.web_port)


def main() -> None:
    parser = argparse.ArgumentParser(prog="ensemble-chat")
    parser.add_argument(
        "scenario",
        nargs="?",
        help="scenario name under SCENARIO_LOC, or an explicit path",
    )
    parser.add_argument("--fresh", action="store_true", help="ignore any saved session")
    parser.add_argument(
        "--ui", choices=["terminal", "web"], default="terminal", help="front end (default: terminal)"
    )
    parser.add_argument("--host", help="web UI bind address (default: CHAT_WEB_HOST, 127.0.0.1)")
    parser.add_argument("--port", type=int, help="web UI port (default: CHAT_WEB_PORT, 8000)")
    args = parser.parse_args()
    try:
        if args.ui == "web":
            run_web(args.scenario, args.fresh, args.host, args.port)
        else:
            asyncio.run(run(args.scenario, args.fresh))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
