"""Interactive game loop — the heart of the adventure engine.

Manages the turn cycle: read player input → build turn message →
stream GM response → handle tool state mutations → save checkpoint.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from strands import Agent
from strands.types.exceptions import MaxTokensReachedException

from my_code.models.data_models import AdventureScene, GameState, WorldInfoEntry
from my_code.models.provider import get_vision_client_args
from my_code.agents.game_master import build_turn_message, create_game_master
from my_code.tools import memory_tools
from my_code.ui.terminal import Terminal
from my_code.vision.probe import probe_vision
from my_code.vision.describer import describe_image


_SAVES_DIR = Path(__file__).parent.parent / "saves"
_EXPORTS_DIR = Path(__file__).parent.parent / "exports"
_SAVES_DIR.mkdir(exist_ok=True)
_EXPORTS_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

def _cmd_save(args: str, state: GameState, gm: Agent, ui: Terminal) -> None:
    name = args.strip() or f"save_{state.turn_count}"
    path = _SAVES_DIR / f"{name}.json"
    data = {
        "turn_count": state.turn_count,
        "input_mode": state.input_mode,
        "memory": state.memory,
        "author_note": state.author_note,
        "world_info_entries": [
            {"keyword": e.keyword, "content": e.content}
            for e in state.world_info_entries
        ],
        "story_log": state.story_log,
        # Full conversation history so load fully restores GM context
        "messages": gm.messages,
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    ui.system(f"Game saved to [bold]{path.name}[/bold].")


def _cmd_load(args: str, state: GameState, gm: Agent, ui: Terminal) -> None:
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
    state.turn_count = data.get("turn_count", 0)
    state.input_mode = data.get("input_mode", "action")
    state.memory = data.get("memory", state.memory)
    state.author_note = data.get("author_note", state.author_note)
    state.world_info_entries = [
        WorldInfoEntry(keyword=e["keyword"], content=e["content"])
        for e in data.get("world_info_entries", [])
    ]
    state.story_log = data.get("story_log", [])
    # Restore full conversation history into the live agent
    if "messages" in data:
        gm.messages[:] = data["messages"]
    ui.system(
        f"Loaded save [bold]{name}[/bold] "
        f"(turn {state.turn_count}, {len(gm.messages)} messages, "
        f"{len(state.story_log)} story entries restored)."
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
        ui.system("Nothing to export yet — the story log is empty.")
        return

    name = args.strip() or f"export_{state.turn_count}"
    path = _EXPORTS_DIR / f"{name}.txt"

    title = state.scene.meta.title
    separator = "=" * len(title)
    body = f"{title}\n{separator}\n\n" + "\n\n".join(state.story_log)

    path.write_text(body, encoding="utf-8")
    ui.system(
        f"Story exported to [bold]{path.name}[/bold] "
        f"({len(state.story_log)} turns, {len(body)} chars)."
    )


async def _cmd_img(args: str, state: GameState, client_args: tuple, ui: Terminal) -> None:
    """Two-step /img flow: load image path → prompt for label → describe → store context."""
    image_path = args.strip().strip('"').strip("'")
    if not image_path:
        ui.system("Usage: /img <path>  — path to an image file (PNG/JPG/WEBP)")
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


def _cmd_help(ui: Terminal, vision_capable: bool = False) -> None:
    img_line = (
        "[bold]/img <path>[/bold]     — attach an image to your next action\n"
        if vision_capable
        else ""
    )
    ui.panel(
        "[bold]/save [name][/bold]    — save game (full snapshot for resuming)\n"
        "[bold]/load [name][/bold]    — load game (no name = list saves)\n"
        "[bold]/export [name][/bold]  — export story narration as plain text\n"
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
# State sync after GM turn
# ---------------------------------------------------------------------------

def _sync_state_from_holder(state: GameState) -> None:
    """Pull any tool mutations from memory_tools._state_holder back into GameState."""
    holder = memory_tools._state_holder
    if "memory" in holder:
        state.memory = holder["memory"]
    if "author_note" in holder:
        state.author_note = holder["author_note"]
    if "world_info_entries" in holder:
        state.world_info_entries = [
            WorldInfoEntry(keyword=e["keyword"], content=e["content"])
            for e in holder["world_info_entries"]
        ]


# ---------------------------------------------------------------------------
# Async streaming call
# ---------------------------------------------------------------------------

async def _stream_gm(
    gm: Agent, message: str, state: GameState, ui: Terminal
) -> tuple[str, Agent]:
    """Bind shared state, stream the GM response, return (full_text, gm).

    If the agent hits max_tokens it is in an unrecoverable state; we recreate
    it with a fresh conversation so the session can continue.
    """
    memory_tools.bind_state({
        "memory": state.memory,
        "author_note": state.author_note,
        "world_info_entries": [
            {"keyword": e.keyword, "content": e.content}
            for e in state.world_info_entries
        ],
    })

    collected: list[str] = []
    ui.gm_start()

    try:
        async for event in gm.stream_async(message):
            if isinstance(event, dict) and "data" in event:
                delta = event["data"]
                if isinstance(delta, str) and delta:
                    ui.gm_chunk(delta)
                    collected.append(delta)
    except MaxTokensReachedException:
        ui.gm_end()
        ui.system(
            "[yellow]Context limit reached — conversation history trimmed. "
            "The story continues but earlier turns are no longer in context. "
            "Use [bold]/save[/bold] to preserve your progress.[/yellow]"
        )
        # Agent is unrecoverable; recreate it fresh so the session continues
        gm = create_game_master(state.scene)
    except asyncio.CancelledError:
        ui.gm_end()
        raise  # let the loop handle clean exit
    except Exception as exc:
        ui.gm_end()
        ui.system(f"[red]GM error: {exc}[/red]")

    else:
        ui.gm_end()

    full = "".join(collected)
    ui.last_streamed = full
    return full, gm


# ---------------------------------------------------------------------------
# Main async loop
# ---------------------------------------------------------------------------

async def _setup_vision(scene: AdventureScene, ui: Terminal) -> tuple[bool, str, tuple | None]:
    """Probe vision capability and pre-describe any startup images.

    Returns (vision_capable, visual_context_text, client_args).
    visual_context_text is baked into the system prompt; images are discarded.
    """
    client_args = get_vision_client_args()
    if not client_args:
        return False, "", None

    ui.system("Checking vision capability…")
    capable = await asyncio.to_thread(probe_vision, *client_args)

    if not capable:
        ui.system("Vision: [yellow]not available[/yellow] — model loaded without mmproj or text-only mode.")
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


async def run_adventure(scene: AdventureScene, ui: Terminal) -> None:
    """Run the interactive adventure loop until the player quits."""
    vision_capable, visual_context, vision_client_args = await _setup_vision(scene, ui)

    state = GameState.from_scene(scene)
    state.vision_capable = vision_capable

    gm: Agent = create_game_master(scene, visual_context=visual_context)
    last_response: str = ""

    ui.banner(scene.meta.title)

    try:
        # Opening narration
        if scene.opening.strip():
            ui.gm_stream_text(scene.opening.strip())
            last_response = scene.opening.strip()
        else:
            opening_prompt = (
                f"[MEMORY]\n{state.memory}\n\n---\n"
                "Begin the adventure. Narrate the opening scene vividly. "
                "Place the player character in the world. Do not ask the player anything yet."
            )
            last_response, gm = await _stream_gm(gm, opening_prompt, state, ui)
        if last_response:
            state.story_log.append(last_response)

        # Turn loop
        while True:
            label = f"[{state.input_mode.upper()}]"
            raw = await ui.prompt(label)

            if raw is None or raw.strip().lower() in ("/quit", "/exit", "quit", "exit"):
                await _maybe_save_on_exit(state, gm, ui)
                break

            if raw.startswith("/"):
                parts = raw[1:].split(None, 1)
                cmd = parts[0].lower()
                args = parts[1] if len(parts) > 1 else ""
                if cmd == "save":
                    _cmd_save(args, state, gm, ui)
                elif cmd == "load":
                    _cmd_load(args, state, gm, ui)
                elif cmd == "export":
                    _cmd_export(args, state, ui)
                elif cmd == "memory":
                    _cmd_memory(state, ui)
                elif cmd == "note":
                    _cmd_note(args, state, ui)
                elif cmd == "mode":
                    _cmd_mode(state, ui)
                elif cmd == "img":
                    if not state.vision_capable:
                        ui.system("[yellow]Vision is not available — model not loaded with mmproj.[/yellow]")
                    elif vision_client_args:
                        await _cmd_img(args, state, vision_client_args, ui)
                elif cmd == "help":
                    _cmd_help(ui, vision_capable=state.vision_capable)
                elif cmd in ("quit", "exit"):
                    await _maybe_save_on_exit(state, gm, ui)
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
            state.pending_image_context = ""  # one turn only — discard before GM call

            last_response, gm = await _stream_gm(gm, turn_message, state, ui)

            if last_response:
                state.story_log.append(last_response)

            _sync_state_from_holder(state)
            ui.refresh_sidebar(state)

            # Silent checkpoint save after every turn
            _cmd_save("_checkpoint", state, gm, Terminal._null())

    except (KeyboardInterrupt, asyncio.CancelledError):
        ui.system("\nInterrupted.")
        await _maybe_save_on_exit(state, gm, ui)


async def _maybe_save_on_exit(state: GameState, gm: Agent, ui: Terminal) -> None:
    if await ui.confirm("Save before quitting? [y/N] "):
        _cmd_save("", state, gm, ui)
    ui.system("Farewell, adventurer.")
