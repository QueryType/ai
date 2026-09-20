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


async def _stream_or_await(engine: Engine, run) -> AsyncIterator[dict]:
    """Yields `stream_start`/`stream_chunk` SSE dicts live, then one final
    `{"type": "stream_result", "result": TurnResult}` — F2F only, since it
    renders as one screenplay block (register.f2f_block) that raw deltas map
    straight onto. Texting mode just awaits `run()` as before and yields the
    single final event, so its behavior is unchanged.

    `run(on_chunk, on_speaker) -> Awaitable[TurnResult]` wraps whichever
    Engine call the caller wants streamed (turn() or regenerate()) — same
    shape as __main__.py's `_Run`, so both front ends share the idea even
    though the code isn't shared.
    """
    if engine.scenario.mode != "f2f":
        result = await run(lambda _: None, None)
        yield {"type": "stream_result", "result": result}
        return

    queue: asyncio.Queue[dict] = asyncio.Queue()

    def on_speaker(character) -> None:
        queue.put_nowait({"type": "stream_start", "speaker": character.name})

    def on_chunk(delta: str) -> None:
        queue.put_nowait({"type": "stream_chunk", "text": delta})

    async def _run() -> TurnResult:
        try:
            return await run(on_chunk, on_speaker)
        finally:
            await queue.put({"type": "_done"})

    task = asyncio.create_task(_run())
    while True:
        event = await queue.get()
        if event["type"] == "_done":
            break
        yield event
    result = await task
    yield {"type": "stream_result", "result": result}


def _turn_event(engine: Engine, result: TurnResult, *, continuation: bool) -> dict:
    return {
        "type": "turn",
        "speaker": result.speaker.name,
        "bubbles": result.bubbles,
        "tics": result.tics,
        "truncated": result.truncated,
        "reasoning_tokens": result.reasoning_tokens,
        "continuation": continuation,
        # For the delete control — addresses this exact reply later via
        # Engine.delete_from(). Always set: _turn_event is only ever built
        # right after a turn that produced this same result.
        "turn_index": engine.last_turn_index(),
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
) -> AsyncIterator[dict]:
    """Same decide()-driven chain as the terminal's `_continue` — kept out of
    Engine, this is orchestration. Yields `_stream_or_await`'s event dicts
    (stream_start/stream_chunk live for F2F, then stream_result) for each
    continuation turn; the caller re-checks `engine.state_error` after each
    stream_result."""
    depth = 0
    while True:
        cont = decide(engine.scenario, result, depth, engine.cfg, rng)
        if cont is None:
            return
        await asyncio.sleep(_CONTINUATION_PAUSE_SECONDS)
        async for ev in _stream_or_await(
            engine,
            lambda on_chunk, on_speaker: engine.turn(
                "",
                on_chunk,
                force_speaker=cont.speaker,
                extra_directive=cont.directive,
                on_speaker=on_speaker,
            ),
        ):
            if ev["type"] == "stream_result":
                result = ev["result"]
            yield ev
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
            "setting": engine.scenario.setting,
            "characters": [
                {"name": c.name, "weight": c.weight} for c in engine.scenario.characters
            ],
            "reply_max_tokens": engine.policy.reply_max_tokens,
            "model": engine.cfg.model,
            "idle_seconds": (
                engine.cfg.idle_seconds_f2f
                if engine.scenario.mode == "f2f"
                else engine.cfg.idle_seconds
            ),
            "vision_capable": engine.policy.vision_capable,
            "mode": engine.scenario.mode,
        })

    @app.get("/api/log")
    async def log() -> JSONResponse:
        return JSONResponse({
            "entries": [
                {
                    "role": e.role,
                    "speaker": e.speaker,
                    "text": e.text,
                    "image_path": e.image_path,
                    "turn_index": e.turn_index,
                }
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

                    result: TurnResult | None = None
                    async for ev in _stream_or_await(
                        engine,
                        lambda on_chunk, on_speaker: engine.turn(
                            stripped,
                            on_chunk,
                            force_speaker=speaker or None,
                            image=image_bytes,
                            on_speaker=on_speaker,
                        ),
                    ):
                        if ev["type"] == "stream_result":
                            result = ev["result"]
                            save_session(engine, session, save_path)
                            yield _sse(_turn_event(engine, result, continuation=False))
                            if engine.state_error:
                                yield _sse({"type": "state_error", "message": engine.state_error})
                        else:
                            yield _sse(ev)

                    async for ev in _run_continuations(engine, result, rng):
                        if ev["type"] == "stream_result":
                            result = ev["result"]
                            save_session(engine, session, save_path)
                            yield _sse(_turn_event(engine, result, continuation=True))
                            if engine.state_error:
                                yield _sse({"type": "state_error", "message": engine.state_error})
                        else:
                            yield _sse(ev)

                    last["result"] = result
                    yield _sse({"type": "state", **_state_payload(engine)})
                except Exception as exc:
                    yield _sse({"type": "error", "message": f"{type(exc).__name__}: {exc}"})
                finally:
                    yield _sse({"type": "done"})

        return _stream(generate())

    @app.post("/api/regenerate", response_model=None)
    async def regenerate(guidance: str = Form("")) -> StreamingResponse | JSONResponse:
        """Redo the last reply, same speaker — only while it's still the
        most recent thing that happened (Engine.can_regenerate()). A true
        history mutation, unlike every other endpoint here — see
        BACKLOG.md for why that's accepted for this one action."""
        if lock.locked():
            return JSONResponse({"error": "a turn is already in progress"}, status_code=429)
        if not engine.can_regenerate():
            return JSONResponse({"error": "nothing to regenerate"}, status_code=400)

        async def generate() -> AsyncIterator[str]:
            async with lock:
                try:
                    result: TurnResult | None = None
                    async for ev in _stream_or_await(
                        engine,
                        lambda on_chunk, on_speaker: engine.regenerate(
                            on_chunk, guidance=guidance.strip(), on_speaker=on_speaker
                        ),
                    ):
                        if ev["type"] == "stream_result":
                            result = ev["result"]
                            save_session(engine, session, save_path)
                            yield _sse({**_turn_event(engine, result, continuation=False), "type": "regenerate"})
                            if engine.state_error:
                                yield _sse({"type": "state_error", "message": engine.state_error})
                        else:
                            yield _sse(ev)

                    async for ev in _run_continuations(engine, result, rng):
                        if ev["type"] == "stream_result":
                            result = ev["result"]
                            save_session(engine, session, save_path)
                            yield _sse(_turn_event(engine, result, continuation=True))
                            if engine.state_error:
                                yield _sse({"type": "state_error", "message": engine.state_error})
                        else:
                            yield _sse(ev)

                    last["result"] = result
                    yield _sse({"type": "state", **_state_payload(engine)})
                except Exception as exc:
                    yield _sse({"type": "error", "message": f"{type(exc).__name__}: {exc}"})
                finally:
                    yield _sse({"type": "done"})

        return _stream(generate())

    @app.post("/api/delete", response_model=None)
    async def delete(turn_index: int = Form(...)) -> JSONResponse:
        """Removes that reply and everything generated after it — a true
        history mutation like /api/regenerate, and pays the same
        cache-reprocess cost on the next request. No streaming: deleting
        produces nothing new to generate. The client is expected to have
        already confirmed with the user before this ever fires."""
        if lock.locked():
            return JSONResponse({"error": "a turn is already in progress"}, status_code=429)
        try:
            engine.delete_from(turn_index)
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        save_session(engine, session, save_path)
        # Rebuilding a TurnResult for whatever's now last isn't worth the
        # bother — idle-continuation just stays quiet until the next real
        # turn re-seeds it, same accepted-rough-edge shape as elsewhere here.
        last["result"] = None
        return JSONResponse({"ok": True, **_state_payload(engine)})

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
                    async for ev in _run_continuations(engine, result, rng):
                        if ev["type"] != "stream_result":
                            yield _sse(ev)
                            continue
                        produced = True
                        result = ev["result"]
                        save_session(engine, session, save_path)
                        yield _sse(_turn_event(engine, result, continuation=True))
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
