"""Core streaming bot call and terminal chat loop."""
from __future__ import annotations

import asyncio
import os
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

_CORE_EVERY = 8   # extract permanent facts every N turns
_STATE_EVERY = 2  # refresh scene state every N turns

_CORE_PROMPT = (
    "Read the conversation above. "
    "Extract facts that will remain true for the rest of this conversation: "
    "names, nicknames, physical descriptions, preferences, dislikes, "
    "relationship history, background, recurring habits. "
    "Add new facts and update any that changed. "
    "NEVER remove a fact unless it is directly contradicted by a newer message. "
    "If no new permanent facts appear, return the existing list unchanged. "
    "Output only a bullet list, nothing else."
)

_STATE_PROMPT = (
    "Describe the CURRENT state of the scene as a bullet list. Include: "
    "exact clothing each person is wearing (including any changes such as unbuttoned, removed, or added items), "
    "current location and setting, "
    "what each person is currently doing or holding, "
    "current emotional mood. "
    "Only describe what is true RIGHT NOW. "
    "Output only the bullet list, nothing else."
)

_STATE_WINDOW = 8  # how many recent messages to feed the scene-state extraction


_GOODBYE_CHECK_PROMPT = (
    "Look at these last few messages. "
    "Answer YES only if BOTH sides have clearly signalled they are done with this conversation — "
    "this includes warm farewells, neutral sign-offs, cold dismissals, or angry endings, in any language. "
    "The tone does not matter. What matters is that both parties have shown a clear, explicit intention to end. "
    "One side wrapping up is NOT enough — both must signal closure. "
    "Reply YES or NO only."
)


async def _is_conversation_done(
    client: AsyncOpenAI,
    model: str,
    messages: Messages,
) -> bool:
    """Ask the LLM if the conversation has wrapped up. Language-agnostic."""
    if len(messages) < 2:
        return False
    recent = messages[-4:]  # last 4 messages is enough context
    try:
        resp = await client.chat.completions.create(
            model=model,
            messages=recent + [{"role": "user", "content": _GOODBYE_CHECK_PROMPT}],
            max_tokens=3,
            stream=False,
        )
        answer = resp.choices[0].message.content.strip().upper()
        return answer.startswith("YES")
    except Exception:
        return False


_AUTO_USER_PROMPT = (
    "You are the human side of this conversation. "
    "Write the single next message you would naturally send. "
    "Rules: "
    "(1) Never repeat a question or topic already covered earlier in the conversation. "
    "(2) Do not rush to wrap up — if there is more to explore, explore it. "
    "    Avoid agreeing to meet, saying bye, or concluding plans unless the conversation has genuinely run its course. "
    "(3) Keep it short and casual — the way a real person texts. "
    "(4) Vary your style: react, tease, ask something new, share something, go deeper on what was just said. "
    "Output only the message itself, no quotes, no labels."
)


async def _generate_auto_user_msg(
    client: AsyncOpenAI,
    model: str,
    base_system: str,
    messages: Messages,
) -> str | None:
    """Generate the next user-side message for auto chat. Returns None on failure."""
    gen_messages = (
        [{"role": "system", "content": base_system}]
        + messages
        + [{"role": "user", "content": _AUTO_USER_PROMPT}]
    )
    try:
        resp = await client.chat.completions.create(
            model=model,
            messages=gen_messages,
            max_tokens=120,
            stream=False,
        )
        return resp.choices[0].message.content.strip()
    except Exception:
        return None


def _get_temperature() -> float:
    """Read FAALTOO_TEMPERATURE from env. Default 0.85, clamped 0.0–2.0."""
    try:
        return max(0.0, min(2.0, float(os.environ.get("FAALTOO_TEMPERATURE", "0.85"))))
    except (ValueError, TypeError):
        return 0.85


def _effective_system(base_system: str, core_facts: str, scene_state: str) -> str:
    parts = [base_system]
    if core_facts:
        parts.append(f"[Character memory — permanent facts, treat as ground truth:\n{core_facts}]")
    if scene_state:
        parts.append(f"[Current scene state:\n{scene_state}]")
    return "\n\n".join(parts)


async def _extract_core_facts(
    client: AsyncOpenAI,
    model: str,
    base_system: str,
    messages: Messages,
    current_core: str,
    since_idx: int,
) -> tuple[str, int]:
    """Returns (updated_core_facts, new_since_idx). Additive only — never drops facts."""
    new_since_idx = len(messages)
    prompt = _CORE_PROMPT
    if current_core:
        prompt += f"\n\nExisting facts (add/update only, never remove):\n{current_core}"
    extract_messages = (
        [{"role": "system", "content": base_system}]
        + messages[since_idx:]
        + [{"role": "user", "content": prompt}]
    )
    try:
        resp = await client.chat.completions.create(
            model=model,
            messages=extract_messages,
            max_tokens=400,
            stream=False,
        )
        return resp.choices[0].message.content.strip(), new_since_idx
    except Exception:
        return current_core, since_idx


async def _extract_scene_state(
    client: AsyncOpenAI,
    model: str,
    base_system: str,
    messages: Messages,
) -> str:
    """Returns a fresh scene snapshot (replaces previous state entirely)."""
    recent = messages[-_STATE_WINDOW:]
    extract_messages = (
        [{"role": "system", "content": base_system}]
        + recent
        + [{"role": "user", "content": _STATE_PROMPT}]
    )
    try:
        resp = await client.chat.completions.create(
            model=model,
            messages=extract_messages,
            max_tokens=250,
            stream=False,
        )
        return resp.choices[0].message.content.strip()
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Core streaming call (no tools)
# ---------------------------------------------------------------------------

async def _stream_bot(
    client: AsyncOpenAI,
    model: str,
    system: str,
    messages: Messages,
    ui: Any,
    max_tokens: int = 700,
) -> str:
    text_parts: list[str] = []
    try:
        stream = await client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system}] + messages,
            max_tokens=max_tokens,
            temperature=_get_temperature(),
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
        "  /tokens <level> — set response length: brief|short|medium|long|extended\n"
        "  /auto          — toggle auto chat (bot drives both sides)\n"
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

    base_system = build_system_prompt(selections)
    session = ChatSession(selections=selections, system_prompt=base_system)

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
    max_tokens = 700
    core_facts = ""
    core_since_idx = 0
    scene_state = ""
    auto_mode = False

    _initial_msg_count = 0

    # ── Chat loop ──
    while True:
        # ── Auto mode: generate user side ──
        if auto_mode:
            try:
                generated = await _generate_auto_user_msg(client, model, base_system, messages)
            except (KeyboardInterrupt, asyncio.CancelledError):
                auto_mode = False
                ui.system("Auto chat stopped.")
                continue
            if generated is None:
                ui.system("Auto chat stopped — could not generate message.")
                auto_mode = False
                raw = await ui.prompt("[YOU]")
            else:
                try:
                    await ui.auto_type("[AUTO]", generated)
                except (KeyboardInterrupt, asyncio.CancelledError):
                    auto_mode = False
                    ui.system("Auto chat stopped.")
                    continue
                raw = generated
        else:
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
                    last_response = await _stream_bot(
                        client, model, _effective_system(base_system, core_facts, scene_state), messages, ui, max_tokens
                    )
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
                                    describe_image, img_path, label.strip(), *vision_client_args,
                                    session.nsfw_level,
                                )
                                _pending_image_context = desc
                                ui.panel(desc, title="Image Context")
                            except Exception as exc:
                                ui.system(f"Could not process image: {exc}")

            elif cmd == "tokens":
                _token_labels = {"brief": 150, "short": 350, "medium": 700, "long": 1400, "extended": 2800}
                val = args.strip().lower()
                if val in _token_labels:
                    max_tokens = _token_labels[val]
                    ui.system(f"Response length: {val} ({max_tokens} tokens).")
                else:
                    try:
                        n = int(val)
                        if not (150 <= n <= 2800):
                            raise ValueError
                        max_tokens = n
                        ui.system(f"Response length set to {max_tokens} tokens.")
                    except ValueError:
                        ui.system("Usage: /tokens brief|short|medium|long|extended  (or 150–2800)")

            elif cmd == "auto":
                auto_mode = not auto_mode
                ui.system(f"Auto chat {'ON — press Ctrl+C to stop.' if auto_mode else 'OFF.'}")

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
        last_response = await _stream_bot(
            client, model, _effective_system(base_system, core_facts, scene_state), messages, ui, max_tokens
        )
        if last_response:
            session.story_log.append(last_response)

        if session.turn_count % _STATE_EVERY == 0:
            scene_state = await _extract_scene_state(client, model, base_system, messages)
        if session.turn_count % _CORE_EVERY == 0:
            core_facts, core_since_idx = await _extract_core_facts(
                client, model, base_system, messages, core_facts, core_since_idx
            )

        # Stop auto mode if context is getting full or conversation wrapped up
        if auto_mode:
            total_chars = sum(len(m.get("content", "")) for m in messages)
            ctx_limit_chars = 16000  # ~4k tokens * 4 chars, conservative
            if total_chars > ctx_limit_chars * 0.8:
                ui.system("Auto chat stopped — context nearly full.")
                auto_mode = False
            elif await _is_conversation_done(client, model, messages):
                ui.system("Auto chat stopped — conversation wrapped up naturally.")
                auto_mode = False

    ui.system("Bye!")
