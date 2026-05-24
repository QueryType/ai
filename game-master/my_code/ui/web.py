"""FastAPI web UI for the game-master adventure engine.

Single-user local app. One session lives in module-level state.
Run with: python -m my_code --ui web
Connect from any browser on the LAN: http://<host-ip>:7860
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, StreamingResponse

from my_code.agents.game_master import build_system_prompt, build_turn_message
from my_code.game_loop import _EXPORTS_DIR, _SAVES_DIR, _stream_gm
from my_code.models.data_models import GameState, WorldInfoEntry
from my_code.models.provider import get_client, get_vision_client_args
from my_code.parser import ParseError, parse_scene_file
from my_code.vision.describer import describe_image
from my_code.vision.probe import probe_vision

logger = logging.getLogger("game_master.web")


# ── NSFW CLASSIFIER BEGIN (revert by removing this function) ────────────────
async def _classify_nsfw(text: str, client, model: str) -> bool:
    """Returns True if the text contains explicit sexual content, False otherwise.
    Uses a single non-streaming LLM call with max_tokens=1 for minimal latency."""
    try:
        resp = await client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Does the following text contain explicit sexual content? "
                        "Reply YES or NO only.\n\n"
                        f"Text: {text!r}"
                    ),
                }
            ],
            max_tokens=1,
            temperature=0,
            stream=False,
        )
        answer = resp.choices[0].message.content.strip().upper()
        return answer == "YES"
    except Exception as exc:
        logger.warning("NSFW classifier error (skipping check): %s", exc)
        return False
# ── NSFW CLASSIFIER END ──────────────────────────────────────────────────────

_STATIC = Path(__file__).parent / "static"


# ---------------------------------------------------------------------------
# Global session (single user)
# ---------------------------------------------------------------------------

_sess: dict[str, Any] = {
    "scene": None,
    "state": None,
    "messages": [],
    "system": "",
    "last_response": "",
    "turn_snapshot": None,
    "client": None,
    "model": "",
    "vision_capable": False,
    "vision_client_args": None,
    "lock": None,
}


def _lock() -> asyncio.Lock:
    if _sess["lock"] is None:
        _sess["lock"] = asyncio.Lock()
    return _sess["lock"]


def _state_payload() -> dict:
    state: GameState | None = _sess["state"]
    if state is None:
        return {}
    return {
        "memory": state.memory,
        "author_note": state.author_note,
        "turn_count": state.turn_count,
        "input_mode": state.input_mode,
    }


# ---------------------------------------------------------------------------
# Minimal UI adapter: feeds stream chunks into an asyncio queue
# ---------------------------------------------------------------------------

class _WebUI:
    def __init__(self):
        self.queue: asyncio.Queue[str | None] = asyncio.Queue()

    def gm_start(self) -> None:
        pass

    def gm_chunk(self, text: str) -> None:
        self.queue.put_nowait(text)

    def gm_end(self) -> None:
        pass

    def system(self, _: str) -> None:
        pass

    def refresh_sidebar(self, _: Any) -> None:
        pass


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _do_save(name: str, state: GameState, messages: list) -> None:
    path = _SAVES_DIR / f"{name}.json"
    path.write_text(json.dumps({**state.snapshot(), "messages": messages}, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Streaming helper
# ---------------------------------------------------------------------------

async def _run_and_drain(ui: _WebUI, client, model, system, messages, state) -> str:
    """Run _stream_gm and put a None sentinel on the queue when done."""
    try:
        result = await _stream_gm(client, model, system, messages, state, ui)
    except Exception as exc:
        ui.queue.put_nowait(f"\n\n[Error: {exc}]")
        result = ""
    finally:
        ui.queue.put_nowait(None)
    return result


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app(default_scenario: str | None = None) -> FastAPI:
    app = FastAPI(title="Game Master")
    app.state.default_scenario = default_scenario

    # ------------------------------------------------------------------
    # Static
    # ------------------------------------------------------------------

    @app.get("/")
    async def index():
        return HTMLResponse((_STATIC / "index.html").read_text(encoding="utf-8"))

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    @app.get("/api/scenarios")
    async def list_scenarios():
        d = Path(__file__).parent.parent.parent / "scenarios"
        files = sorted(d.glob("*.md")) if d.exists() else []
        return JSONResponse({
            "scenarios": [{"name": f.stem, "path": str(f)} for f in files],
            "default": app.state.default_scenario,
        })

    @app.post("/api/start")
    async def start_game(body: dict):
        scenario_path = body.get("scenario") or app.state.default_scenario
        if not scenario_path:
            return JSONResponse({"error": "No scenario specified."}, status_code=400)

        # Allow browser to override connection settings
        server_url = body.get("server_url", "").strip()
        model_override = body.get("model", "").strip()
        if server_url:
            os.environ["STORY_ENGINE_LOCAL_BASE_URL"] = server_url
            os.environ["STORY_ENGINE_GAME_MASTER_BASE_URL"] = server_url
        if model_override:
            os.environ["STORY_ENGINE_GAME_MASTER_MODEL"] = model_override

        try:
            scene = parse_scene_file(scenario_path)
        except (FileNotFoundError, ParseError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

        try:
            client, model = get_client()
        except Exception as exc:
            return JSONResponse({"error": f"Provider error: {exc}"}, status_code=500)

        # Optional vision probe (skipped if body.vision is false/absent)
        vision_capable = False
        vision_client_args = get_vision_client_args()
        if vision_client_args and body.get("vision", False):
            try:
                vision_capable = await asyncio.to_thread(probe_vision, *vision_client_args)
            except Exception:
                pass

        visual_context = ""
        if vision_capable and vision_client_args:
            descs: list[str] = []
            if scene.scene_image and Path(scene.scene_image).exists():
                try:
                    desc = await asyncio.to_thread(
                        describe_image, scene.scene_image, "the game scene and environment",
                        *vision_client_args,
                    )
                    descs.append(f"Scene: {desc}")
                except Exception:
                    pass
            for char in scene.characters:
                if char.portrait and Path(char.portrait).exists():
                    try:
                        desc = await asyncio.to_thread(
                            describe_image, char.portrait, f"character {char.name}",
                            *vision_client_args,
                        )
                        descs.append(f"{char.name}: {desc}")
                    except Exception:
                        pass
            visual_context = "\n\n".join(descs)

        system = build_system_prompt(scene, visual_context=visual_context)
        state = GameState.from_scene(scene)
        state.vision_capable = vision_capable
        messages: list[dict] = []

        _sess.update({
            "scene": scene,
            "state": state,
            "messages": messages,
            "system": system,
            "last_response": "",
            "turn_snapshot": None,
            "client": client,
            "model": model,
            "vision_capable": vision_capable,
            "vision_client_args": vision_client_args,
            "lock": asyncio.Lock(),
        })

        async def generate():
            if scene.opening.strip():
                opening = scene.opening.strip()
                messages.append({"role": "assistant", "content": opening})
                state.story_log.append(opening)
                _sess["last_response"] = opening
                yield _sse({"type": "chunk", "text": opening})
            else:
                opening_prompt = (
                    f"[MEMORY]\n{state.memory}\n\n---\n"
                    "Begin the adventure. Narrate the opening scene vividly. "
                    "Place the player in the world. Do not ask questions yet."
                )
                messages.append({"role": "user", "content": opening_prompt})
                ui = _WebUI()
                task = asyncio.create_task(_run_and_drain(ui, client, model, system, messages, state))
                while True:
                    chunk = await asyncio.wait_for(ui.queue.get(), timeout=120)
                    if chunk is None:
                        break
                    yield _sse({"type": "chunk", "text": chunk})
                opening = await task
                if opening:
                    state.story_log.append(opening)
                    _sess["last_response"] = opening

            yield _sse({"type": "state", **_state_payload()})
            yield _sse({"type": "done", "title": scene.meta.title,
                        "vision_capable": vision_capable,
                        "nsfw": scene.meta.nsfw})

        return StreamingResponse(generate(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    # ------------------------------------------------------------------
    # Player action
    # ------------------------------------------------------------------

    @app.post("/api/action")
    async def player_action(
        text: str = Form(""),
        image: Optional[UploadFile] = File(None),
        image_label: str = Form(""),
    ):
        if _sess["state"] is None:
            return JSONResponse({"error": "No game in progress."}, status_code=400)

        lk = _lock()
        if lk.locked():
            return JSONResponse({"error": "A turn is already in progress."}, status_code=429)

        await lk.acquire()

        try:
            state: GameState = _sess["state"]
            messages: list = _sess["messages"]
            client = _sess["client"]
            model: str = _sess["model"]
            system: str = _sess["system"]

            # Handle attached image
            image_desc = ""
            if image and _sess["vision_client_args"]:
                try:
                    label = image_label.strip() or "the scene"
                    suffix = Path(image.filename or "img.jpg").suffix or ".jpg"
                    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                        tmp.write(await image.read())
                        tmp_path = tmp.name
                    image_desc = await asyncio.to_thread(
                        describe_image, tmp_path, label,
                        *_sess["vision_client_args"],
                    )
                    Path(tmp_path).unlink(missing_ok=True)
                except Exception as exc:
                    image_desc = f"[image error: {exc}]"

            raw = text.strip()
            if not raw:
                lk.release()
                return JSONResponse({"error": "Empty input."}, status_code=400)

            # ── NSFW CLASSIFIER BEGIN (revert by removing this block) ──────────
            if not state.scene.meta.nsfw:
                flagged = await _classify_nsfw(raw, client, model)
                if not flagged and image_label:
                    flagged = await _classify_nsfw(image_label, client, model)
                if flagged:
                    logger.warning(
                        "NSFW bypass attempt (turn %d, scenario: %s) — %r",
                        state.turn_count, state.scene.meta.title, raw,
                    )
            # ── NSFW CLASSIFIER END ─────────────────────────────────────────

            if state.input_mode == "action" and not raw.lower().startswith("you "):
                player_input = "You " + raw
            else:
                player_input = raw

            state.turn_count += 1
            turn_message = build_turn_message(
                player_input, _sess["last_response"], state,
                image_context=image_desc,
            )

            _sess["turn_snapshot"] = {
                "messages": list(messages),
                "state": state.snapshot(),
                "last_response": _sess["last_response"],
                "turn_message": turn_message,
                "player_input": player_input,
            }

            messages.append({"role": "user", "content": turn_message})

            ui = _WebUI()
            task = asyncio.create_task(_run_and_drain(ui, client, model, system, messages, state))

            async def generate():
                try:
                    yield _sse({"type": "player", "text": player_input})
                    if image_desc:
                        yield _sse({"type": "image_desc", "text": image_desc})
                    while True:
                        chunk = await asyncio.wait_for(ui.queue.get(), timeout=120)
                        if chunk is None:
                            break
                        yield _sse({"type": "chunk", "text": chunk})
                    response = await task
                    if response:
                        state.story_log.append(response)
                        _sess["last_response"] = response
                    _do_save("_checkpoint", state, messages)
                    yield _sse({"type": "state", **_state_payload()})
                    yield _sse({"type": "done"})
                except Exception as exc:
                    yield _sse({"type": "error", "message": str(exc)})
                finally:
                    lk.release()

            return StreamingResponse(generate(), media_type="text/event-stream",
                                     headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

        except Exception as exc:
            lk.release()
            return JSONResponse({"error": str(exc)}, status_code=500)

    # ------------------------------------------------------------------
    # Regen
    # ------------------------------------------------------------------

    @app.post("/api/regen")
    async def regen():
        if _sess["turn_snapshot"] is None:
            return JSONResponse({"error": "Nothing to regenerate."}, status_code=400)

        lk = _lock()
        if lk.locked():
            return JSONResponse({"error": "A turn is already in progress."}, status_code=429)

        await lk.acquire()

        try:
            snap = _sess["turn_snapshot"]
            state: GameState = _sess["state"]
            messages: list = _sess["messages"]

            messages[:] = snap["messages"]
            state.restore(snap["state"])
            _sess["last_response"] = snap["last_response"]
            messages.append({"role": "user", "content": snap["turn_message"]})

            ui = _WebUI()
            task = asyncio.create_task(
                _run_and_drain(ui, _sess["client"], _sess["model"], _sess["system"], messages, state)
            )

            async def generate():
                try:
                    yield _sse({"type": "regen"})
                    while True:
                        chunk = await asyncio.wait_for(ui.queue.get(), timeout=120)
                        if chunk is None:
                            break
                        yield _sse({"type": "chunk", "text": chunk})
                    response = await task
                    if response:
                        state.story_log.append(response)
                        _sess["last_response"] = response
                    _do_save("_checkpoint", state, messages)
                    yield _sse({"type": "state", **_state_payload()})
                    yield _sse({"type": "done"})
                except Exception as exc:
                    yield _sse({"type": "error", "message": str(exc)})
                finally:
                    lk.release()

            return StreamingResponse(generate(), media_type="text/event-stream",
                                     headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

        except Exception as exc:
            lk.release()
            return JSONResponse({"error": str(exc)}, status_code=500)

    # ------------------------------------------------------------------
    # State / saves / commands
    # ------------------------------------------------------------------

    @app.get("/api/state")
    async def get_state():
        return JSONResponse(_state_payload())

    @app.get("/api/saves")
    async def list_saves():
        saves = [{"name": s.stem} for s in sorted(_SAVES_DIR.glob("*.json"))
                 if s.stem != "_checkpoint"]
        return JSONResponse({"saves": saves})

    @app.post("/api/save")
    async def save_game(body: dict):
        if _sess["state"] is None:
            return JSONResponse({"error": "No game in progress."}, status_code=400)
        name = body.get("name", "").strip() or f"save_{_sess['state'].turn_count}"
        _do_save(name, _sess["state"], _sess["messages"])
        return JSONResponse({"name": name})

    @app.post("/api/load")
    async def load_game(body: dict):
        name = body.get("name", "").strip()
        if not name:
            return JSONResponse({"error": "No save name."}, status_code=400)
        if _sess["state"] is None:
            return JSONResponse({"error": "Start a game first."}, status_code=400)
        path = _SAVES_DIR / f"{name}.json"
        if not path.exists():
            return JSONResponse({"error": f"Save not found: {name!r}"}, status_code=404)
        data = json.loads(path.read_text(encoding="utf-8"))
        _sess["state"].restore(data)
        _sess["messages"][:] = data.get("messages", [])
        _sess["turn_snapshot"] = None
        log = _sess["state"].story_log
        _sess["last_response"] = log[-1] if log else ""
        return JSONResponse({"story_log": log, **_state_payload()})

    @app.post("/api/mode")
    async def toggle_mode():
        if _sess["state"] is None:
            return JSONResponse({"error": "No game in progress."}, status_code=400)
        state = _sess["state"]
        state.input_mode = "story" if state.input_mode == "action" else "action"
        return JSONResponse({"input_mode": state.input_mode})

    @app.post("/api/undo")
    async def undo_last():
        if _sess["state"] is None:
            return JSONResponse({"error": "No game in progress."}, status_code=400)
        state: GameState = _sess["state"]
        messages: list = _sess["messages"]
        if not state.story_log or state.turn_count == 0:
            return JSONResponse({"error": "Nothing to undo."}, status_code=400)

        # Find the last player turn (user message that is not a tool result)
        last_player_idx = None
        for i in reversed(range(len(messages))):
            if messages[i].get("role") == "user" and "tool_call_id" not in messages[i]:
                last_player_idx = i
                break

        if last_player_idx is not None:
            del messages[last_player_idx:]

        state.story_log.pop()
        state.turn_count = max(0, state.turn_count - 1)
        _sess["last_response"] = state.story_log[-1] if state.story_log else ""
        _sess["turn_snapshot"] = None
        return JSONResponse({"ok": True, **_state_payload()})

    @app.post("/api/edit")
    async def edit_last(body: dict):
        if _sess["state"] is None:
            return JSONResponse({"error": "No game in progress."}, status_code=400)
        new_text = body.get("text", "").strip()
        if not new_text:
            return JSONResponse({"error": "Empty text."}, status_code=400)
        state: GameState = _sess["state"]
        if not state.story_log:
            return JSONResponse({"error": "Nothing to edit."}, status_code=400)
        messages: list = _sess["messages"]
        for i in reversed(range(len(messages))):
            if messages[i].get("role") == "assistant" and messages[i].get("content"):
                messages[i] = {**messages[i], "content": new_text}
                break
        state.story_log[-1] = new_text
        _sess["last_response"] = new_text
        return JSONResponse({"ok": True})

    @app.post("/api/note")
    async def update_note(body: dict):
        if _sess["state"] is None:
            return JSONResponse({"error": "No game in progress."}, status_code=400)
        content = body.get("content", "").strip()
        if content:
            _sess["state"].author_note = content
        return JSONResponse({"author_note": _sess["state"].author_note})

    @app.get("/api/export")
    async def export_story():
        if not _sess["state"] or not _sess["state"].story_log:
            return JSONResponse({"error": "Nothing to export."}, status_code=400)
        state = _sess["state"]
        title = state.scene.meta.title
        body = f"{title}\n{'=' * len(title)}\n\n" + "\n\n".join(state.story_log)
        safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in title)
        return PlainTextResponse(
            body,
            headers={"Content-Disposition": f'attachment; filename="{safe_title}.txt"'},
        )

    return app
