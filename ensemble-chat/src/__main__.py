from __future__ import annotations

import argparse
import asyncio
import time
from pathlib import Path

from src.autopilot import run_autonomous, run_self_auto
from src.bootstrap import build_engine, save_session
from src.config import load_config
from src.driver import continue_chain, play, raise_due_promises, regenerate_turn
from src.engine import Engine, TurnResult
from src.gpu_memory import ensure_gpu_memory_limit
from src.session import Session
from src.ui.terminal import Terminal


async def _run_autopilot(
    ui: Terminal, engine: Engine, session: Session, save_path: Path,
    autonomous: bool, turns: int, seconds: float,
) -> None:
    kind = "autonomous" if autonomous else "self-auto"
    ui.console.print(
        f"[dim]autopilot: {kind} · up to {turns} turns / {seconds:.0f}s · Ctrl+C to stop[/dim]\n"
    )
    try:
        if autonomous:
            await run_autonomous(ui, engine, session, save_path, turns, seconds)
        else:
            await run_self_auto(ui, engine, session, save_path, turns, seconds)
    finally:
        with ui.console.status("saving…", spinner="dots"):
            await engine.drain()
        save_session(engine, session, save_path)
        ui.console.print(f"[dim]saved {len(engine.history)} messages -> {save_path}[/dim]")


async def run(
    scenario_arg: str | None,
    fresh: bool,
    autonomous: bool = False,
    auto_human: bool = False,
    max_turns: int | None = None,
    max_seconds: float | None = None,
) -> None:
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
        last_result = await raise_due_promises(ui, engine, session, save_path)

    if autonomous or auto_human:
        turns = max_turns or engine.cfg.autopilot_max_turns
        seconds = max_seconds or engine.cfg.autopilot_max_seconds
        try:
            await _run_autopilot(ui, engine, session, save_path, autonomous, turns, seconds)
        except KeyboardInterrupt:
            pass
        return

    async def on_idle() -> None:
        nonlocal last_result
        if last_result is not None:
            last_result = await continue_chain(ui, engine, session, save_path, last_result)

    try:
        while True:
            try:
                idle_seconds = (
                    engine.cfg.idle_seconds_f2f
                    if engine.scenario.mode == "f2f"
                    else engine.cfg.idle_seconds
                )
                raw = (await ui.ask(on_idle=on_idle, idle_seconds=idle_seconds)).strip()
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
            if raw.startswith("/regenerate"):
                if not engine.can_regenerate():
                    ui.console.print("[dim red]nothing to regenerate[/dim red]\n")
                    continue
                parts = raw.split(None, 1)
                guidance = parts[1].strip() if len(parts) > 1 else ""
                result = await regenerate_turn(ui, engine, session, save_path, guidance)
                last_result = await continue_chain(ui, engine, session, save_path, result)
                continue
            if raw.startswith("/delete"):
                parts = raw.split(None, 1)
                arg = parts[1].strip() if len(parts) > 1 else ""
                if not arg.isdigit():
                    ui.console.print("[dim red]usage: /delete <n> — turn number, see /log[/dim red]\n")
                    continue
                idx = int(arg)
                answer = ui.console.input(
                    f"Delete turn #{idx} and everything after it? This cannot be undone. [y/N] "
                )
                if not answer.strip().lower().startswith("y"):
                    ui.console.print("[dim]cancelled[/dim]\n")
                    continue
                try:
                    engine.delete_from(idx)
                except ValueError as exc:
                    ui.console.print(f"[dim red]{exc}[/dim red]\n")
                    continue
                save_session(engine, session, save_path)
                last_result = None
                ui.console.print(f"[dim]deleted · history: {len(engine.history)} msgs[/dim]\n")
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
                result = await play(
                    ui, engine, session, save_path, caption, image=image_path.read_bytes()
                )
                last_result = await continue_chain(ui, engine, session, save_path, result)
                continue
            if raw.startswith("/next"):
                parts = raw.split(None, 1)
                name = parts[1].strip() if len(parts) > 1 else None
                if name and not scenario.by_name(name):
                    ui.console.print(f"[dim red]no character named {name!r}[/dim red]\n")
                    continue
                result = await play(ui, engine, session, save_path, "", speaker=name)
                last_result = await continue_chain(ui, engine, session, save_path, result)
                continue

            result = await play(ui, engine, session, save_path, raw)
            last_result = await continue_chain(ui, engine, session, save_path, result)
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
    parser.add_argument(
        "--autonomous", action="store_true",
        help="no human at all — the cast just keeps talking (terminal only)",
    )
    parser.add_argument(
        "--auto-human", action="store_true",
        help="you stay in the scene, but your lines are generated too (terminal only)",
    )
    parser.add_argument(
        "--max-turns", type=int, help="autopilot stop condition (default: CHAT_AUTOPILOT_MAX_TURNS)"
    )
    parser.add_argument(
        "--max-seconds", type=float, help="autopilot stop condition (default: CHAT_AUTOPILOT_MAX_SECONDS)"
    )
    args = parser.parse_args()
    if args.autonomous and args.auto_human:
        raise SystemExit("--autonomous and --auto-human are mutually exclusive")
    if (args.autonomous or args.auto_human) and args.ui == "web":
        raise SystemExit("--autonomous/--auto-human are terminal-only for now")
    ensure_gpu_memory_limit(load_config().gpu_memory_headroom_gb)
    try:
        if args.ui == "web":
            run_web(args.scenario, args.fresh, args.host, args.port)
        else:
            asyncio.run(run(
                args.scenario, args.fresh,
                autonomous=args.autonomous, auto_human=args.auto_human,
                max_turns=args.max_turns, max_seconds=args.max_seconds,
            ))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
