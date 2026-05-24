"""Entry point: python -m my_code [--ui terminal|web] [--preset NAME] [--port 7860]"""
from __future__ import annotations

import argparse
import asyncio


def main() -> None:
    parser = argparse.ArgumentParser(description="faaltoo-chat — quick local LLM chat")
    parser.add_argument(
        "--ui", choices=["terminal", "web"], default="web",
        help="Interface mode (default: web)",
    )
    parser.add_argument(
        "--preset", default=None,
        help="Preset name to load, e.g. 'Chai Break' (terminal only)",
    )
    parser.add_argument("--port", type=int, default=7860, help="Web UI port (default: 7860)")
    parser.add_argument("--host", default="0.0.0.0", help="Web UI host (default: 0.0.0.0)")
    args = parser.parse_args()

    if args.ui == "web":
        import uvicorn
        from my_code.ui.web import create_app
        uvicorn.run(create_app(), host=args.host, port=args.port)
    else:
        from my_code.chat_loop import run_chat_terminal
        asyncio.run(run_chat_terminal(preset_name=args.preset))


if __name__ == "__main__":
    main()
