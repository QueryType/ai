"""Core streaming bot call and terminal chat loop."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

from my_code.models.data_models import ChatSession
from my_code.models.provider import get_client, get_vision_client_args
from my_code.prompt_builder import build_system_prompt

_EXPORTS_DIR = Path(__file__).parent.parent / "exports"
_EXPORTS_DIR.mkdir(exist_ok=True)

_KICK_OFF = (
    "[Start the conversation naturally, in character. "
    "Say the first thing that comes to mind for this persona and situation. "
    "Do not introduce yourself or explain your role.]"
)

Messages = list[dict[str, Any]]


# ---------------------------------------------------------------------------
# Core streaming call (no tools)
# ---------------------------------------------------------------------------

async def _stream_bot(
    client: AsyncOpenAI,
    model: str,
    system: str,
    messages: Messages,
    ui: Any,
) -> str:
    text_parts: list[str] = []
    try:
        stream = await client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system}] + messages,
            stream=True,
        )
        ui.bot_start()
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta.content:
                text_parts.append(delta.content)
                ui.bot_chunk(delta.content)
        ui.bot_end()
    except Exception as exc:
        ui.system(f"[red]Error: {exc}[/red]")

    full_text = "".join(text_parts)
    if full_text:
        messages.append({"role": "assistant", "content": full_text})
    return full_text


# ---------------------------------------------------------------------------
# Terminal commands
# ---------------------------------------------------------------------------

def _cmd_export(args: str, session: ChatSession) -> str:
    if not session.story_log:
        return "Nothing to export yet."
    name = args.strip() or f"chat_{session.turn_count}"
    path = _EXPORTS_DIR / f"{name}.txt"
    body = "\n\n".join(session.story_log)
    path.write_text(body, encoding="utf-8")
    return f"Exported to exports/{name}.txt ({len(session.story_log)} turns)."


def _cmd_help(vision_capable: bool = False) -> str:
    img_line = "  /img <path>    — attach image to your next message\n" if vision_capable else ""
    return (
        "  /regen         — regenerate the last bot response\n"
        "  /undo          — undo the last turn\n"
        "  /export [name] — export chat as plain text\n"
        + img_line
        + "  /help          — show this\n"
        "  /quit          — exit"
    )


# ---------------------------------------------------------------------------
# Terminal run loop
# ---------------------------------------------------------------------------

async def run_chat_terminal(preset_name: str | None = None) -> None:
    from my_code.ui.terminal import Terminal, dimension_picker
    from my_code.dimensions import PRESETS

    ui = Terminal()
    ui.banner("faaltoo chat")

    # ── Dimension selection ──
    preset = PRESETS.get(preset_name) if preset_name else None
    if preset_name and not preset:
        ui.system(f"Preset {preset_name!r} not found. Showing picker.")
    selections = dimension_picker(preset=preset, ui=ui)

    system = build_system_prompt(selections)
    session = ChatSession(selections=selections, system_prompt=system)

    # ── Vision setup ──
    vision_capable = False
    vision_client_args = get_vision_client_args()
    if vision_client_args:
        ui.system("Checking vision…")
        from my_code.vision import probe_vision
        vision_capable = await asyncio.to_thread(probe_vision, *vision_client_args)
        ui.system("Vision: enabled" if vision_capable else "Vision: not available")

    client, model = get_client()
    messages: Messages = []
    last_response = ""
    _turn_snapshot: dict | None = None
    _initial_msg_count = 0
    _pending_image_context = ""

    _initial_msg_count = 0

    # ── Chat loop ──
    while True:
        raw = await ui.prompt("[YOU]")

        if raw is None or raw.strip().lower() in ("/quit", "/exit", "quit", "exit"):
            break

        if raw.startswith("/"):
            parts = raw[1:].split(None, 1)
            cmd = parts[0].lower()
            args = parts[1] if len(parts) > 1 else ""

            if cmd == "regen":
                if _turn_snapshot is None:
                    ui.system("Nothing to regenerate yet.")
                else:
                    ui.system("Regenerating…")
                    messages[:] = _turn_snapshot["messages"]
                    last_response = _turn_snapshot["last_response"]
                    session.turn_count = _turn_snapshot["turn_count"]
                    session.story_log = list(_turn_snapshot["story_log"])
                    messages.append({"role": "user", "content": _turn_snapshot["turn_message"]})
                    session.turn_count += 1
                    last_response = await _stream_bot(client, model, system, messages, ui)
                    if last_response:
                        session.story_log.append(last_response)

            elif cmd == "undo":
                if len(messages) <= _initial_msg_count:
                    ui.system("Nothing to undo.")
                elif (messages[-1].get("role") == "assistant" and
                      messages[-2].get("role") == "user"):
                    del messages[-2:]
                    if session.story_log:
                        session.story_log.pop()
                    session.turn_count = max(0, session.turn_count - 1)
                    last_response = session.story_log[-1] if session.story_log else ""
                    _turn_snapshot = None
                    ui.system(f"Undone. Turn {session.turn_count}.")
                else:
                    ui.system("Cannot undo from here.")

            elif cmd == "export":
                ui.system(_cmd_export(args, session))

            elif cmd == "img":
                if not vision_capable:
                    ui.system("Vision not available for this model.")
                elif vision_client_args:
                    img_path = args.strip().strip('"').strip("'")
                    if not img_path:
                        ui.system("Usage: /img <path>")
                    elif not Path(img_path).exists():
                        ui.system(f"Image not found: {img_path}")
                    else:
                        label = await ui.prompt("What does this image represent?")
                        if label and label.strip():
                            ui.system("Processing image…")
                            try:
                                from my_code.vision import describe_image
                                desc = await asyncio.to_thread(
                                    describe_image, img_path, label.strip(), *vision_client_args
                                )
                                _pending_image_context = desc
                                ui.panel(desc, title="Image Context")
                            except Exception as exc:
                                ui.system(f"Could not process image: {exc}")

            elif cmd == "help":
                ui.panel(_cmd_help(vision_capable), title="Commands")

            else:
                ui.system(f"Unknown command: /{cmd}  (try /help)")
            continue

        if not raw.strip():
            continue

        text = raw.strip()
        if _pending_image_context:
            text = f"{text}\n\n[Image context: {_pending_image_context}]"
            _pending_image_context = ""

        _turn_snapshot = {
            "messages": list(messages),
            "last_response": last_response,
            "turn_count": session.turn_count,
            "story_log": list(session.story_log),
            "turn_message": text,
        }

        session.turn_count += 1
        messages.append({"role": "user", "content": text})
        last_response = await _stream_bot(client, model, system, messages, ui)
        if last_response:
            session.story_log.append(last_response)

    ui.system("Bye!")
