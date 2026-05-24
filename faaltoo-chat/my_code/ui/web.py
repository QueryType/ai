"""FastAPI web UI for faaltoo-chat.

Single-user local app. One session lives in module-level state.
Run with: python -m my_code  (or: python -m my_code --ui web)
"""
from __future__ import annotations

import asyncio
import json
import logging
import tempfile
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, StreamingResponse

from my_code.chat_loop import _EXPORTS_DIR, _stream_bot
from my_code.dimensions import DIMENSIONS, PRESETS
from my_code.models.data_models import ChatSession
from my_code.models.provider import get_client, get_vision_client_args
from my_code.prompt_builder import build_system_prompt

logger = logging.getLogger("faaltoo.web")

_STATIC = Path(__file__).parent / "static"
_USER_PRESETS_PATH = Path(__file__).parent.parent.parent / "user_presets.json"
_USER_DIMS_PATH = Path(__file__).parent.parent.parent / "user_dimensions.json"


# ---------------------------------------------------------------------------
# User preset persistence
# ---------------------------------------------------------------------------

def _load_user_presets() -> dict:
    if _USER_PRESETS_PATH.exists():
        try:
            return json.loads(_USER_PRESETS_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_user_presets(data: dict) -> None:
    _USER_PRESETS_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# User dimension option persistence
# ---------------------------------------------------------------------------

def _load_user_dims() -> dict:
    if _USER_DIMS_PATH.exists():
        try:
            return json.loads(_USER_DIMS_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_user_dims(data: dict) -> None:
    _USER_DIMS_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Global session (single user)
# ---------------------------------------------------------------------------

_sess: dict[str, Any] = {
    "session": None,
    "messages": [],
    "system": "",
    "last_response": "",
    "turn_snapshot": None,
    "initial_msg_count": 0,
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
    session: ChatSession | None = _sess["session"]
    if session is None:
        return {}
    return {
        "turn_count": session.turn_count,
        "vision_capable": _sess["vision_capable"],
    }


# ---------------------------------------------------------------------------
# Web UI adapter
# ---------------------------------------------------------------------------

class _WebUI:
    def __init__(self):
        self.queue: asyncio.Queue[str | None] = asyncio.Queue()

    def bot_start(self) -> None:
        pass

    def bot_chunk(self, text: str) -> None:
        self.queue.put_nowait(text)

    def bot_end(self) -> None:
        pass

    def system(self, _: str) -> None:
        pass


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _run_and_drain(ui: _WebUI, client, model, system, messages, session) -> str:
    try:
        result = await _stream_bot(client, model, system, messages, ui)
    except Exception as exc:
        ui.queue.put_nowait(f"\n\n[Error: {exc}]")
        result = ""
    finally:
        ui.queue.put_nowait(None)
    return result


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    app = FastAPI(title="faaltoo chat")

    @app.get("/")
    async def index():
        return HTMLResponse((_STATIC / "index.html").read_text(encoding="utf-8"))

    # ------------------------------------------------------------------
    # Dimension data for setup screen
    # ------------------------------------------------------------------

    @app.get("/api/dimensions")
    async def get_dimensions():
        return JSONResponse({
            "dimensions": DIMENSIONS,
            "presets": PRESETS,
            "user_presets": _load_user_presets(),
            "user_dim_options": _load_user_dims(),
        })

    @app.post("/api/dimensions/{dim_key}")
    async def add_dim_option(dim_key: str, body: dict):
        if dim_key not in DIMENSIONS:
            return JSONResponse({"error": f"Unknown dimension: {dim_key!r}"}, status_code=400)
        value = body.get("value", "").strip()
        if not value:
            return JSONResponse({"error": "Value is required."}, status_code=400)
        builtin_options = [o.lower() for o in DIMENSIONS[dim_key]["options"]]
        data = _load_user_dims()
        existing = [o.lower() for o in data.get(dim_key, [])]
        if value.lower() in builtin_options or value.lower() in existing:
            return JSONResponse({"error": f"{value!r} already exists."}, status_code=409)
        data.setdefault(dim_key, []).append(value)
        _save_user_dims(data)
        return JSONResponse({"ok": True, "dim_key": dim_key, "value": value})

    @app.delete("/api/dimensions/{dim_key}/{value:path}")
    async def delete_dim_option(dim_key: str, value: str):
        data = _load_user_dims()
        options = data.get(dim_key, [])
        if value not in options:
            return JSONResponse({"error": f"{value!r} not found in user options."}, status_code=404)
        options.remove(value)
        if not options:
            del data[dim_key]
        else:
            data[dim_key] = options
        _save_user_dims(data)
        return JSONResponse({"ok": True})

    @app.post("/api/presets")
    async def create_preset(body: dict):
        name = body.get("name", "").strip()
        selections = body.get("selections", {})
        if not name:
            return JSONResponse({"error": "Name is required."}, status_code=400)
        if not all(selections.get(k) for k in ("archetype", "energy", "talk_type")):
            return JSONResponse({"error": "archetype, energy and talk_type are required."}, status_code=400)
        data = _load_user_presets()
        data[name] = selections
        _save_user_presets(data)
        return JSONResponse({"ok": True, "name": name})

    @app.put("/api/presets/{old_name:path}")
    async def update_preset(old_name: str, body: dict):
        data = _load_user_presets()
        if old_name not in data:
            return JSONResponse({"error": f"Preset {old_name!r} not found."}, status_code=404)
        new_name = body.get("name", old_name).strip()
        selections = body.get("selections", data[old_name])
        if not all(selections.get(k) for k in ("archetype", "energy", "talk_type")):
            return JSONResponse({"error": "archetype, energy and talk_type are required."}, status_code=400)
        if new_name != old_name:
            del data[old_name]
        data[new_name] = selections
        _save_user_presets(data)
        return JSONResponse({"ok": True, "name": new_name})

    @app.delete("/api/presets/{name:path}")
    async def delete_preset(name: str):
        data = _load_user_presets()
        if name not in data:
            return JSONResponse({"error": f"Preset {name!r} not found."}, status_code=404)
        del data[name]
        _save_user_presets(data)
        return JSONResponse({"ok": True})

    # ------------------------------------------------------------------
    # Start session
    # ------------------------------------------------------------------

    @app.post("/api/start")
    async def start_chat(body: dict):
        selections = body.get("selections", {})
        if not selections.get("archetype") or not selections.get("energy") or not selections.get("talk_type"):
            return JSONResponse({"error": "archetype, energy, and talk_type are required."}, status_code=400)

        nsfw_level = body.get("nsfw_level", "medium")
        server_url = body.get("server_url", "").strip()
        model_override = body.get("model", "").strip()
        if server_url:
            import os
            os.environ["FAALTOO_LOCAL_BASE_URL"] = server_url
        if model_override:
            import os
            os.environ["FAALTOO_MODEL"] = model_override

        try:
            client, model = get_client()
        except Exception as exc:
            return JSONResponse({"error": f"Provider error: {exc}"}, status_code=500)

        vision_capable = False
        vision_client_args = get_vision_client_args()
        if vision_client_args and body.get("vision", False):
            try:
                from my_code.vision import probe_vision
                vision_capable = await asyncio.to_thread(probe_vision, *vision_client_args)
            except Exception:
                pass

        system = build_system_prompt(selections, nsfw_level=nsfw_level)
        session = ChatSession(selections=selections, system_prompt=system, nsfw_level=nsfw_level)
        messages: list[dict] = []

        _sess.update({
            "session": session,
            "messages": messages,
            "system": system,
            "last_response": "",
            "turn_snapshot": None,
            "initial_msg_count": 0,
            "client": client,
            "model": model,
            "vision_capable": vision_capable,
            "vision_client_args": vision_client_args,
            "lock": asyncio.Lock(),
        })

        _sess["initial_msg_count"] = 0
        return JSONResponse({
            "ok": True,
            "vision_capable": vision_capable,
            **_state_payload(),
        })

    # ------------------------------------------------------------------
    # Chat turn
    # ------------------------------------------------------------------

    @app.post("/api/chat")
    async def chat(
        text: str = Form(""),
        image: Optional[UploadFile] = File(None),
        image_label: str = Form(""),
    ):
        if _sess["session"] is None:
            return JSONResponse({"error": "No chat in progress."}, status_code=400)

        lk = _lock()
        if lk.locked():
            return JSONResponse({"error": "A turn is already in progress."}, status_code=429)

        await lk.acquire()

        try:
            session: ChatSession = _sess["session"]
            messages: list = _sess["messages"]
            client = _sess["client"]
            model: str = _sess["model"]
            system: str = _sess["system"]

            image_desc = ""
            if image and _sess["vision_client_args"]:
                try:
                    label = image_label.strip() or "the image"
                    suffix = Path(image.filename or "img.jpg").suffix or ".jpg"
                    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                        tmp.write(await image.read())
                        tmp_path = tmp.name
                    from my_code.vision import describe_image
                    image_desc = await asyncio.to_thread(
                        describe_image, tmp_path, label, *_sess["vision_client_args"]
                    )
                    Path(tmp_path).unlink(missing_ok=True)
                except Exception as exc:
                    image_desc = f"[image error: {exc}]"

            user_text = text.strip()
            if not user_text:
                lk.release()
                return JSONResponse({"error": "Empty input."}, status_code=400)

            full_text = user_text
            if image_desc:
                full_text = f"{user_text}\n\n[Image: {image_desc}]"

            _sess["turn_snapshot"] = {
                "messages": list(messages),
                "last_response": _sess["last_response"],
                "turn_count": session.turn_count,
                "story_log": list(session.story_log),
                "turn_message": full_text,
            }

            session.turn_count += 1
            messages.append({"role": "user", "content": full_text})

            ui = _WebUI()
            task = asyncio.create_task(
                _run_and_drain(ui, client, model, system, messages, session)
            )

            async def generate():
                try:
                    yield _sse({"type": "user", "text": user_text})
                    if image_desc:
                        yield _sse({"type": "image_desc", "text": image_desc})
                    while True:
                        chunk = await asyncio.wait_for(ui.queue.get(), timeout=120)
                        if chunk is None:
                            break
                        yield _sse({"type": "chunk", "text": chunk})
                    response = await task
                    if response:
                        session.story_log.append(response)
                        _sess["last_response"] = response
                    yield _sse({"type": "state", **_state_payload()})
                    yield _sse({"type": "done"})
                except Exception as exc:
                    yield _sse({"type": "error", "message": str(exc)})
                finally:
                    lk.release()

            return StreamingResponse(
                generate(), media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )

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
            session: ChatSession = _sess["session"]
            messages: list = _sess["messages"]

            messages[:] = snap["messages"]
            session.turn_count = snap["turn_count"]
            session.story_log = list(snap["story_log"])
            _sess["last_response"] = snap["last_response"]
            session.turn_count += 1
            messages.append({"role": "user", "content": snap["turn_message"]})

            ui = _WebUI()
            task = asyncio.create_task(
                _run_and_drain(ui, _sess["client"], _sess["model"], _sess["system"], messages, session)
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
                        session.story_log.append(response)
                        _sess["last_response"] = response
                    yield _sse({"type": "state", **_state_payload()})
                    yield _sse({"type": "done"})
                except Exception as exc:
                    yield _sse({"type": "error", "message": str(exc)})
                finally:
                    lk.release()

            return StreamingResponse(
                generate(), media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )

        except Exception as exc:
            lk.release()
            return JSONResponse({"error": str(exc)}, status_code=500)

    # ------------------------------------------------------------------
    # Undo
    # ------------------------------------------------------------------

    @app.post("/api/undo")
    async def undo():
        if _sess["session"] is None:
            return JSONResponse({"error": "No chat in progress."}, status_code=400)
        session: ChatSession = _sess["session"]
        messages: list = _sess["messages"]
        initial = _sess["initial_msg_count"]

        if len(messages) <= initial:
            return JSONResponse({"error": "Nothing to undo."}, status_code=400)

        if (messages[-1].get("role") == "assistant" and
                len(messages) >= 2 and messages[-2].get("role") == "user"):
            del messages[-2:]
            if session.story_log:
                session.story_log.pop()
            session.turn_count = max(0, session.turn_count - 1)
            _sess["last_response"] = session.story_log[-1] if session.story_log else ""
            _sess["turn_snapshot"] = None

        return JSONResponse({"ok": True, **_state_payload()})

    # ------------------------------------------------------------------
    # Edit last response
    # ------------------------------------------------------------------

    @app.post("/api/edit")
    async def edit_last(body: dict):
        if _sess["session"] is None:
            return JSONResponse({"error": "No chat in progress."}, status_code=400)
        new_text = body.get("text", "").strip()
        if not new_text:
            return JSONResponse({"error": "Empty text."}, status_code=400)
        session: ChatSession = _sess["session"]
        messages: list = _sess["messages"]
        if not session.story_log:
            return JSONResponse({"error": "Nothing to edit."}, status_code=400)
        for i in reversed(range(len(messages))):
            if messages[i].get("role") == "assistant" and messages[i].get("content"):
                messages[i] = {**messages[i], "content": new_text}
                break
        session.story_log[-1] = new_text
        _sess["last_response"] = new_text
        return JSONResponse({"ok": True})

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    @app.get("/api/export")
    async def export_chat():
        session: ChatSession | None = _sess["session"]
        if not session or not session.story_log:
            return JSONResponse({"error": "Nothing to export."}, status_code=400)
        body = "\n\n".join(session.story_log)
        return PlainTextResponse(
            body,
            headers={"Content-Disposition": 'attachment; filename="chat.txt"'},
        )

    # ------------------------------------------------------------------
    # Reset (new chat)
    # ------------------------------------------------------------------

    @app.post("/api/reset")
    async def reset():
        _sess.update({
            "session": None,
            "messages": [],
            "system": "",
            "last_response": "",
            "turn_snapshot": None,
            "initial_msg_count": 0,
            "client": None,
            "model": "",
            "vision_capable": False,
            "vision_client_args": None,
            "lock": None,
        })
        return JSONResponse({"ok": True})

    return app
