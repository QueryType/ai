"""Local web UI. Single-user, single in-process session — same personal-tool
shape as the terminal UI, just a different delivery layer.

Streaming follows faaltoo-chat's pattern (SSE over a plain POST, not a
websocket): the reply streams back as `data: {...}` chunks on the same
request, which composes naturally with continuations — the generator just
keeps yielding turns, human or continuation, until the chain ends.

Engine, Selector and continuation.decide() are untouched. This module only
turns their output into SSE events instead of rich-console prints.
"""
from __future__ import annotations

import asyncio
import json
import random
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse

from src.bootstrap import save_session
from src.continuation import decide
from src.engine import Engine, TurnResult
from src.session import Session
from src.transcript import entries as transcript_entries

_STATIC = Path(__file__).parent / "static"
_CONTINUATION_PAUSE_SECONDS = 1.1  # a beat longer than generation alone, see Terminal.pause_for_continuation


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def _turn_event(result: TurnResult, *, continuation: bool) -> dict:
    return {
        "type": "turn",
        "speaker": result.speaker.name,
        "bubbles": result.bubbles,
        "tics": result.tics,
        "continuation": continuation,
    }


def _state_payload(engine: Engine) -> dict:
    return {
        **asdict(engine.state),
        "debt": dict(engine.selector.debt),
        "history_len": len(engine.history),
    }


def _stream(generate: AsyncIterator[str]) -> StreamingResponse:
    return StreamingResponse(
        generate,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _run_continuations(
    engine: Engine, result: TurnResult, rng: random.Random
) -> AsyncIterator[TurnResult]:
    """Same decide()-driven chain as the terminal's `_continue` — kept out of
    Engine, this is orchestration. Yields each continuation turn as it's
    generated; the caller re-checks `engine.state_error` after each one."""
    depth = 0
    while True:
        cont = decide(engine.scenario, result, depth, engine.cfg, rng)
        if cont is None:
            return
        await asyncio.sleep(_CONTINUATION_PAUSE_SECONDS)
        result = await engine.turn(
            "", lambda _: None, force_speaker=cont.speaker, extra_directive=cont.directive
        )
        yield result
        depth += 1


def create_app(engine: Engine, session: Session, save_path: Path) -> FastAPI:
    lock = asyncio.Lock()
    rng = random.Random()
    # The last turn produced, human- or idle-triggered — what the idle-timer
    # check reasons about, same as the terminal's `last_result` in __main__.py.
    last: dict[str, TurnResult | None] = {"result": None}

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        for promise in engine.state.due_promises():
            promise.fulfilled = True
            last["result"] = await engine.turn(
                "",
                lambda _: None,
                force_speaker=promise.speaker or None,
                extra_directive=(
                    f'You said you would do this: "{promise.text}". '
                    "Bring it up now, in your own words, as if it just occurred to you."
                ),
            )
            save_session(engine, session, save_path)
        yield
        await engine.drain()
        save_session(engine, session, save_path)

    app = FastAPI(title="ensemble-chat", lifespan=lifespan)

    @app.get("/")
    async def index() -> HTMLResponse:
        return HTMLResponse((_STATIC / "index.html").read_text(encoding="utf-8"))

    @app.get("/api/cast")
    async def cast() -> JSONResponse:
        return JSONResponse({
            "title": engine.scenario.title,
            "characters": [
                {"name": c.name, "weight": c.weight} for c in engine.scenario.characters
            ],
            "reply_max_tokens": engine.policy.reply_max_tokens,
            "model": engine.cfg.model,
            "idle_seconds": engine.cfg.idle_seconds,
            "vision_capable": engine.policy.vision_capable,
        })

    @app.get("/api/log")
    async def log() -> JSONResponse:
        return JSONResponse({
            "entries": [
                {"role": e.role, "speaker": e.speaker, "text": e.text, "image_path": e.image_path}
                for e in transcript_entries(engine.history)
            ],
            "state": _state_payload(engine),
        })

    @app.get("/api/attachments/{name}", response_model=None)
    async def attachment(name: str) -> FileResponse | JSONResponse:
        # `name` only ever comes from a path we generated (see vision.image_ref,
        # always a bare `<uuid>.jpg`), but validate anyway before touching disk.
        if "/" in name or "\\" in name or name in (".", ".."):
            return JSONResponse({"error": "invalid name"}, status_code=400)
        path = engine.attachments_dir / name
        if not path.is_file():
            return JSONResponse({"error": "not found"}, status_code=404)
        return FileResponse(path)

    @app.post("/api/turn", response_model=None)
    async def turn(
        text: str = Form(""),
        speaker: str | None = Form(None),
        image: UploadFile | None = File(None),
    ) -> StreamingResponse | JSONResponse:
        if lock.locked():
            return JSONResponse({"error": "a turn is already in progress"}, status_code=429)
        if image is not None and not engine.policy.vision_capable:
            return JSONResponse({"error": "this model doesn't accept image input"}, status_code=400)

        async def generate() -> AsyncIterator[str]:
            async with lock:
                try:
                    stripped = text.strip()
                    image_bytes = await image.read() if image is not None else None
                    if stripped or image_bytes:
                        yield _sse({"type": "user", "text": stripped, "has_image": image_bytes is not None})
                    result = await engine.turn(
                        stripped, lambda _: None, force_speaker=speaker or None, image=image_bytes
                    )
                    save_session(engine, session, save_path)
                    yield _sse(_turn_event(result, continuation=False))
                    if engine.state_error:
                        yield _sse({"type": "state_error", "message": engine.state_error})

                    async for cont_result in _run_continuations(engine, result, rng):
                        result = cont_result
                        save_session(engine, session, save_path)
                        yield _sse(_turn_event(result, continuation=True))
                        if engine.state_error:
                            yield _sse({"type": "state_error", "message": engine.state_error})

                    last["result"] = result
                    yield _sse({"type": "state", **_state_payload(engine)})
                except Exception as exc:
                    yield _sse({"type": "error", "message": f"{type(exc).__name__}: {exc}"})
                finally:
                    yield _sse({"type": "done"})

        return _stream(generate())

    @app.post("/api/idle", response_model=None)
    async def idle() -> StreamingResponse | JSONResponse:
        """Same check as the terminal's on_idle callback: re-run decide() on
        whatever the conversation currently stands on. A no-op most of the
        time — rule 1 (don't badger the human after an unanswered question)
        or plain bad luck on the roll — which is exactly the point."""
        if lock.locked():
            return JSONResponse({"error": "a turn is already in progress"}, status_code=429)

        async def generate() -> AsyncIterator[str]:
            async with lock:
                try:
                    result = last["result"]
                    if result is None:
                        return
                    produced = False
                    async for cont_result in _run_continuations(engine, result, rng):
                        produced = True
                        result = cont_result
                        save_session(engine, session, save_path)
                        yield _sse(_turn_event(result, continuation=True))
                        if engine.state_error:
                            yield _sse({"type": "state_error", "message": engine.state_error})
                    if produced:
                        last["result"] = result
                        yield _sse({"type": "state", **_state_payload(engine)})
                except Exception as exc:
                    yield _sse({"type": "error", "message": f"{type(exc).__name__}: {exc}"})
                finally:
                    yield _sse({"type": "done"})

        return _stream(generate())

    return app
