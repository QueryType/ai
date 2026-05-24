"""Interactive game loop — owns the conversation history and drives the GM.

The conversation is a plain list[dict] (OpenAI message format) that we own
entirely. No framework wrapper — full control for editing, saving, and
future GUI integration.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

from my_code.agents.game_master import TOOL_SCHEMAS, build_system_prompt, build_turn_message
from my_code.models.data_models import AdventureScene, GameState, WorldInfoEntry
from my_code.models.provider import get_client, get_vision_client_args
from my_code.tools.dice_tools import roll_dice
from my_code.ui.terminal import Terminal
from my_code.vision.describer import describe_image
from my_code.vision.probe import probe_vision


_SAVES_DIR = Path(__file__).parent.parent / "saves"
_EXPORTS_DIR = Path(__file__).parent.parent / "exports"
_SAVES_DIR.mkdir(exist_ok=True)
_EXPORTS_DIR.mkdir(exist_ok=True)

Messages = list[dict[str, Any]]

_MAX_TOOL_ROUNDS = 8  # safety cap on consecutive tool calls before forcing a text response


# ---------------------------------------------------------------------------
# Tool dispatch
# ---------------------------------------------------------------------------

def _dispatch_tool(name: str, args_json: str, state: GameState) -> str:
    try:
        args = json.loads(args_json) if args_json.strip() else {}
    except json.JSONDecodeError:
        return f"Tool error: could not parse arguments for {name!r}"

    if name == "roll_dice":
        return roll_dice(args.get("notation", "1d20"))

    if name == "update_memory":
        content = args.get("content", "").strip()
        state.memory = content
        return f"Memory updated ({len(content.split())} words)."

    if name == "update_authors_note":
        state.author_note = args.get("content", "").strip()
        return "Author's note updated."

    if name == "add_world_info_entry":
        keyword = args.get("keyword", "").strip()
        content = args.get("content", "").strip()
        for entry in state.world_info_entries:
            if entry.keyword.lower() == keyword.lower():
                entry.content = content
                return f"World info updated: {keyword!r}."
        state.world_info_entries.append(WorldInfoEntry(keyword=keyword, content=content))
        return f"World info added: {keyword!r}."

    return f"Unknown tool: {name!r}"


# ---------------------------------------------------------------------------
# Streaming GM call
# ---------------------------------------------------------------------------

async def _stream_gm(
    client: AsyncOpenAI,
    model: str,
    system: str,
    messages: Messages,
    state: GameState,
    ui: Terminal,
) -> str:
    """Run one full GM turn: stream response, handle tool calls, return final text.

    Appends assistant message(s) and tool results to `messages` in place.
    May call the model multiple times if it uses tools before generating prose.
    """
    for _round in range(_MAX_TOOL_ROUNDS + 1):
        text_parts: list[str] = []
        tc_acc: dict[int, dict] = {}
        finish_reason: str | None = None
        streaming_text = False

        try:
            stream = await client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": system}] + messages,
                tools=TOOL_SCHEMAS,
                stream=True,
            )

            async for chunk in stream:
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                delta = choice.delta

                if delta.content:
                    if not streaming_text:
                        ui.gm_start()
                        streaming_text = True
                    text_parts.append(delta.content)
                    ui.gm_chunk(delta.content)

                if delta.tool_calls:
                    for tc_d in delta.tool_calls:
                        idx = tc_d.index
                        if idx not in tc_acc:
                            tc_acc[idx] = {"id": tc_d.id or "", "name": "", "args": ""}
                        if tc_d.id:
                            tc_acc[idx]["id"] = tc_d.id
                        if tc_d.function:
                            if tc_d.function.name:
                                tc_acc[idx]["name"] += tc_d.function.name
                            if tc_d.function.arguments:
                                tc_acc[idx]["args"] += tc_d.function.arguments

                if choice.finish_reason:
                    finish_reason = choice.finish_reason

        except Exception as exc:
            if streaming_text:
                ui.gm_end()
            ui.system(f"[red]GM error: {exc}[/red]")
            full_text = "".join(text_parts)
            if full_text:
                messages.append({"role": "assistant", "content": full_text})
            return full_text

        if streaming_text:
            ui.gm_end()

        full_text = "".join(text_parts)

        if tc_acc and _round < _MAX_TOOL_ROUNDS:
            tc_list = [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {"name": tc["name"], "arguments": tc["args"]},
                }
                for _, tc in sorted(tc_acc.items())
            ]
            asst_msg: dict[str, Any] = {"role": "assistant", "tool_calls": tc_list}
            if full_text:
                asst_msg["content"] = full_text
            messages.append(asst_msg)

            for tc in tc_list:
                result = _dispatch_tool(
                    tc["function"]["name"], tc["function"]["arguments"], state
                )
                messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result})
            # Loop: model will see tool results and generate a response
        else:
            messages.append({"role": "assistant", "content": full_text})
            return full_text

    return ""  # unreachable


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

def _cmd_save(args: str, state: GameState, messages: Messages, ui: Terminal) -> None:
    name = args.strip() or f"save_{state.turn_count}"
    path = _SAVES_DIR / f"{name}.json"
    data = {
        **state.snapshot(),
        "messages": messages,
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    ui.system(f"Saved to [bold]{path.name}[/bold].")


def _cmd_load(args: str, state: GameState, messages: Messages, ui: Terminal) -> None:
    name = args.strip()
    if not name:
        saves = sorted(_SAVES_DIR.glob("*.json"))
        if not saves:
            ui.system("No saves found.")
        else:
            ui.system("Saves: " + ", ".join(s.stem for s in saves))
        return

    path = _SAVES_DIR / f"{name}.json"
    if not path.exists():
        ui.system(f"Save not found: {name!r}")
        return

    data = json.loads(path.read_text(encoding="utf-8"))
    state.restore(data)
    messages[:] = data.get("messages", [])
    ui.system(
        f"Loaded [bold]{name}[/bold] "
        f"(turn {state.turn_count}, {len(messages)} messages)."
    )


def _cmd_memory(state: GameState, ui: Terminal) -> None:
    ui.panel(state.memory or "(empty)", title="Memory")


def _cmd_note(args: str, state: GameState, ui: Terminal) -> None:
    if not args.strip():
        ui.panel(state.author_note or "(empty)", title="Author's Note")
        return
    state.author_note = args.strip()
    ui.system("Author's note updated.")


def _cmd_mode(state: GameState, ui: Terminal) -> None:
    state.input_mode = "story" if state.input_mode == "action" else "action"
    ui.system(f"Input mode: [bold]{state.input_mode.upper()}[/bold]")


def _cmd_export(args: str, state: GameState, ui: Terminal) -> None:
    if not state.story_log:
        ui.system("Nothing to export yet.")
        return
    name = args.strip() or f"export_{state.turn_count}"
    path = _EXPORTS_DIR / f"{name}.txt"
    title = state.scene.meta.title
    body = f"{title}\n{'=' * len(title)}\n\n" + "\n\n".join(state.story_log)
    path.write_text(body, encoding="utf-8")
    ui.system(f"Exported to [bold]{path.name}[/bold] ({len(state.story_log)} turns).")


async def _cmd_img(
    args: str, state: GameState, client_args: tuple, ui: Terminal
) -> None:
    image_path = args.strip().strip('"').strip("'")
    if not image_path:
        ui.system("Usage: /img <path>")
        return
    if not Path(image_path).exists():
        ui.system(f"[red]Image not found: {image_path}[/red]")
        return
    label_raw = await ui.prompt("What does this represent in the scene?")
    if not label_raw or not label_raw.strip():
        ui.system("Cancelled.")
        return
    ui.system("Processing image…")
    try:
        desc = await asyncio.to_thread(
            describe_image, image_path, label_raw.strip(), *client_args
        )
        state.pending_image_context = desc
        ui.panel(desc, title="Image Context")
    except Exception as exc:
        ui.system(f"[red]Could not process image: {exc}[/red]")


async def _cmd_edit(
    state: GameState, messages: Messages, ui: Terminal
) -> str | None:
    """Inline-edit the last GM response. Returns new text, or None if cancelled."""
    if not state.story_log:
        ui.system("Nothing to edit yet.")
        return None

    current = state.story_log[-1]
    ui.panel(current, title="Current response")
    ui.system("Enter replacement — blank line to finish, [bold]/cancel[/bold] to abort:")

    lines: list[str] = []
    while True:
        raw = await ui.prompt("")
        if raw is None:
            ui.system("Cancelled.")
            return None
        if raw.strip() == "/cancel":
            ui.system("Cancelled.")
            return None
        if raw.strip() == "":
            break
        lines.append(raw)

    if not lines:
        ui.system("No changes made.")
        return None

    new_text = "\n".join(lines)

    # Update the last assistant message that has text content
    for i in reversed(range(len(messages))):
        if messages[i].get("role") == "assistant" and messages[i].get("content"):
            messages[i] = {**messages[i], "content": new_text}
            break

    state.story_log[-1] = new_text
    ui.system("Saved.")
    return new_text


def _cmd_help(ui: Terminal, vision_capable: bool = False) -> None:
    img_line = "[bold]/img <path>[/bold]     — attach an image to your next action\n" if vision_capable else ""
    ui.panel(
        "[bold]/save [name][/bold]    — save game\n"
        "[bold]/load [name][/bold]    — load game (no name = list saves)\n"
        "[bold]/export [name][/bold]  — export story as plain text\n"
        "[bold]/regen[/bold]          — regenerate the last GM response\n"
        "[bold]/edit[/bold]           — edit the last GM response inline\n"
        "[bold]/memory[/bold]         — show current memory block\n"
        "[bold]/note [text][/bold]    — show or update author's note\n"
        "[bold]/mode[/bold]           — toggle action ↔ story input mode\n"
        + img_line +
        "[bold]/help[/bold]           — this message\n"
        "[bold]/quit[/bold]           — exit",
        title="Commands",
    )


# ---------------------------------------------------------------------------
# Input pre-processing
# ---------------------------------------------------------------------------

def _preprocess_input(raw: str, state: GameState) -> str:
    text = raw.strip()
    if state.input_mode == "action" and not text.lower().startswith("you "):
        text = "You " + text
    return text


# ---------------------------------------------------------------------------
# Vision setup
# ---------------------------------------------------------------------------

async def _setup_vision(
    scene: AdventureScene, ui: Terminal
) -> tuple[bool, str, tuple | None]:
    client_args = get_vision_client_args()
    if not client_args:
        return False, "", None

    ui.system("Checking vision capability…")
    capable = await asyncio.to_thread(probe_vision, *client_args)

    if not capable:
        ui.system("Vision: [yellow]not available[/yellow]")
        return False, "", client_args

    ui.system("Vision: [green]enabled[/green]")
    descs: list[str] = []

    if scene.scene_image and Path(scene.scene_image).exists():
        ui.system(f"Describing scene image: {scene.scene_image}")
        try:
            desc = await asyncio.to_thread(
                describe_image, scene.scene_image, "the game scene and environment", *client_args
            )
            descs.append(f"Scene environment: {desc}")
            ui.panel(desc, title="Scene")
        except Exception as exc:
            ui.system(f"[yellow]Could not describe scene image: {exc}[/yellow]")

    for char in scene.characters:
        if char.portrait and Path(char.portrait).exists():
            ui.system(f"Describing portrait: {char.name}")
            try:
                desc = await asyncio.to_thread(
                    describe_image, char.portrait, f"the character {char.name}", *client_args
                )
                descs.append(f"{char.name}: {desc}")
                ui.panel(desc, title=f"Portrait — {char.name}")
            except Exception as exc:
                ui.system(f"[yellow]Could not describe portrait for {char.name}: {exc}[/yellow]")

    return True, "\n\n".join(descs), client_args


# ---------------------------------------------------------------------------
# Main async loop
# ---------------------------------------------------------------------------

async def run_adventure(scene: AdventureScene, ui: Terminal) -> None:
    """Run the interactive adventure loop until the player quits."""
    vision_capable, visual_context, vision_client_args = await _setup_vision(scene, ui)

    state = GameState.from_scene(scene)
    state.vision_capable = vision_capable

    client, model = get_client()
    system = build_system_prompt(scene, visual_context=visual_context)

    # Owned conversation history (no system message — passed separately each call)
    messages: Messages = []
    last_response: str = ""

    # Snapshot of messages+state taken just before each GM call — enables /regen
    _turn_snapshot: dict | None = None

    ui.banner(scene.meta.title)

    try:
        # Opening narration
        if scene.opening.strip():
            ui.gm_stream_text(scene.opening.strip())
            last_response = scene.opening.strip()
            messages.append({"role": "assistant", "content": last_response})
        else:
            opening_prompt = (
                f"[MEMORY]\n{state.memory}\n\n---\n"
                "Begin the adventure. Narrate the opening scene vividly. "
                "Place the player character in the world. Do not ask the player anything yet."
            )
            messages.append({"role": "user", "content": opening_prompt})
            last_response = await _stream_gm(client, model, system, messages, state, ui)

        if last_response:
            state.story_log.append(last_response)

        # Turn loop
        while True:
            label = f"[{state.input_mode.upper()}]"
            raw = await ui.prompt(label)

            if raw is None or raw.strip().lower() in ("/quit", "/exit", "quit", "exit"):
                await _maybe_save_on_exit(state, messages, ui)
                break

            if raw.startswith("/"):
                parts = raw[1:].split(None, 1)
                cmd = parts[0].lower()
                args = parts[1] if len(parts) > 1 else ""

                if cmd == "save":
                    _cmd_save(args, state, messages, ui)
                elif cmd == "load":
                    _cmd_load(args, state, messages, ui)
                    _turn_snapshot = None  # snapshot is invalid after load
                elif cmd == "export":
                    _cmd_export(args, state, ui)
                elif cmd == "memory":
                    _cmd_memory(state, ui)
                elif cmd == "note":
                    _cmd_note(args, state, ui)
                elif cmd == "mode":
                    _cmd_mode(state, ui)
                elif cmd == "regen":
                    if _turn_snapshot is None:
                        ui.system("Nothing to regenerate — no turn played yet.")
                    else:
                        ui.system("Regenerating…")
                        messages[:] = _turn_snapshot["messages"]
                        state.restore(_turn_snapshot["state"])
                        last_response = _turn_snapshot["last_response"]
                        turn_msg = _turn_snapshot["turn_message"]
                        messages.append({"role": "user", "content": turn_msg})
                        last_response = await _stream_gm(
                            client, model, system, messages, state, ui
                        )
                        if last_response:
                            state.story_log.append(last_response)
                        _cmd_save("_checkpoint", state, messages, Terminal._null())
                elif cmd == "edit":
                    new_text = await _cmd_edit(state, messages, ui)
                    if new_text is not None:
                        last_response = new_text
                elif cmd == "img":
                    if not state.vision_capable:
                        ui.system("[yellow]Vision not available for this model.[/yellow]")
                    elif vision_client_args:
                        await _cmd_img(args, state, vision_client_args, ui)
                elif cmd == "help":
                    _cmd_help(ui, vision_capable=state.vision_capable)
                elif cmd in ("quit", "exit"):
                    await _maybe_save_on_exit(state, messages, ui)
                    break
                else:
                    ui.system(f"Unknown command: /{cmd}  (try /help)")
                continue

            if not raw.strip():
                continue

            player_input = _preprocess_input(raw, state)
            state.turn_count += 1

            turn_message = build_turn_message(
                player_input, last_response, state,
                image_context=state.pending_image_context,
            )
            state.pending_image_context = ""

            # Snapshot before this turn so /regen can roll back
            _turn_snapshot = {
                "messages": list(messages),  # shallow copy; items are immutable (we only append)
                "state": state.snapshot(),
                "last_response": last_response,
                "turn_message": turn_message,
            }

            messages.append({"role": "user", "content": turn_message})
            last_response = await _stream_gm(client, model, system, messages, state, ui)

            if last_response:
                state.story_log.append(last_response)

            ui.refresh_sidebar(state)
            _cmd_save("_checkpoint", state, messages, Terminal._null())

    except (KeyboardInterrupt, asyncio.CancelledError):
        ui.system("\nInterrupted.")
        await _maybe_save_on_exit(state, messages, ui)


async def _maybe_save_on_exit(
    state: GameState, messages: Messages, ui: Terminal
) -> None:
    if await ui.confirm("Save before quitting? [y/N] "):
        _cmd_save("", state, messages, ui)
    ui.system("Farewell, adventurer.")
