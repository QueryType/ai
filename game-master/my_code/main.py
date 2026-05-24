"""Entry point for the game-master adventure engine."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from my_code.parser import ParseError, parse_scene_file
from my_code.game_loop import run_adventure
from my_code.ui.terminal import Terminal


def _resolve_scenario(path_arg: str | None) -> str:
    if path_arg:
        return path_arg
    default = Path(__file__).parent.parent / "scenarios" / "ashenveil.md"
    if default.exists():
        return str(default)
    sys.exit(
        "No scenario specified and default scenarios/ashenveil.md not found.\n"
        "Usage: python -m my_code [scenario.md]"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Game Master — AI-driven text adventure engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python -m my_code                          # run default scenario\n"
            "  python -m my_code scenarios/ashenveil.md  # explicit scenario\n"
        ),
    )
    parser.add_argument(
        "scenario",
        nargs="?",
        default=None,
        help="Path to a .md scenario file (default: scenarios/ashenveil.md)",
    )
    parser.add_argument(
        "--ui",
        choices=["terminal", "web"],
        default="terminal",
        help="UI mode: terminal (default) or web (browser, served on port 7860)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=7860,
        help="Port for web UI (default: 7860)",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host/IP to bind for web UI (default: 0.0.0.0)",
    )
    args = parser.parse_args()

    if args.ui == "web":
        import uvicorn
        from my_code.ui.web import create_app
        ui = Terminal()
        host, port = args.host, args.port
        ui.system(f"Game Master web UI → [bold]http://{host}:{port}[/bold]")
        if args.scenario:
            ui.system(f"Default scenario: [bold]{args.scenario}[/bold]")
        app = create_app(default_scenario=args.scenario)
        uvicorn.run(app, host=host, port=port)
        return

    scenario_path = _resolve_scenario(args.scenario)

    try:
        scene = parse_scene_file(scenario_path)
    except FileNotFoundError as e:
        sys.exit(str(e))
    except ParseError as e:
        sys.exit(f"Scenario parse error — {e}")

    ui = Terminal()
    ui.system(f"Loading scenario: [bold]{scenario_path}[/bold]")
    try:
        asyncio.run(run_adventure(scene, ui))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
