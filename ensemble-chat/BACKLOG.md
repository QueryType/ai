# Backlog — discussions and decisions

Running log of things raised in conversation that aren't built yet, so a later
session doesn't have to re-derive them. Each entry: the idea, the decision (if
one was made), and current status. Newest on top. Promote an entry to its own
`PLAN_*.md` (see `PLAN_CONTINUATIONS.md`) once it's actually being built.

## Checkpoint: 2026-09-15, commit `e00434b`

First git commit — repo initialized this session (`git init`, `.gitignore`
added for `.env`/`profiles/`/`__pycache__`/`.DS_Store`). Covers everything
through the idle-timer work (Tiers 1–3 of `PLAN_CONTINUATIONS.md` complete,
web UI built). This is the rollback point for the vision work starting below:
`git diff e00434b` / `git reset --hard e00434b` to bail out entirely.

---

## Bug: session save relied on a clean shutdown — fixed 2026-09-15

Reported live: tested the web UI (image upload etc.) successfully in one
browser session, closed the browser, hit Ctrl-C — and the saved session came
back essentially empty. Root cause found by reproduction, not guesswork:
the web UI (`ui/web.py`) only ever called `save_session()` in the FastAPI
`lifespan`'s code *after* `yield` — i.e. only on a clean shutdown. The
reporter has "a habit of pressing ctrl+c multiple times" — and uvicorn's own
log line during graceful shutdown says exactly what a second one does:
`"Waiting for connections to close. (CTRL+C to force quit)"`. A second
SIGINT force-aborts everything via `CancelledError` before the post-`yield`
code ever runs, so `save_session()` never executes — reproduced directly:
turn a real request mid-flight, send two SIGINTs close together, get no file
on disk at all. Same exposure existed in the terminal UI for a killed
terminal, a crash, or a slept machine — anything short of reaching the
`finally` block in `__main__.py`'s `run()`.

**Fixed by no longer depending on shutdown at all:**
- `session.py`'s `Session.save()` now writes atomically (temp file +
  `os.replace`) so a kill mid-*write* can't corrupt the file either — only
  fast-follows the main fix, but the same failure class.
- `ui/web.py` calls `save_session()` after every `engine.turn()` — the main
  turn, every continuation hop, every idle-triggered hop, and every
  due-promise raised at startup — not just at shutdown.
- `__main__.py`'s `_play()` (the single choke-point every terminal turn goes
  through — human input, `/next`, `/image`, and every continuation hop) does
  the same; `session`/`save_path` threaded through `_play`/`_continue`/
  `_raise_due_promises` to make that possible.

Verified by reproduction, not just code review: the exact double-SIGINT
sequence that previously produced zero saved entries now saves the turn that
completed before the kill and loses only the one turn that was still
generating when the second signal landed — the worst case is now "the one
in-flight exchange," not "everything since the last clean exit." Also
verified the terminal path writes to disk immediately after a single `_play`
call, with no shutdown code involved at all.

`README.md`'s "Where the chat is stored" section updated to describe this;
previously said "saves on exit," which was the bug's whole premise.

---

## Face-to-face (F2F) conversation mode

Raised: 2026-09-15.

The app currently only produces a texting register — short bubbles, no
narration, enforced by `prompt.py`'s `_REGISTER` and `register.py`'s bubble
splitting. Question was whether F2F (in-person, script-style) scenes are
possible.

**Decision: keep both, as a second mode rather than a fork.** Most of the
architecture is register-agnostic and carries over untouched: `state.py`,
`tracker.py`, `session.py`, `selector.py`'s debt math, and everything in
`DESIGN.md` about cache-stable prompting. What actually differs:

- `prompt.py` `_REGISTER` — F2F wants action beats and tone cues
  (`*picks up mug, doesn't look up*`), not a ban on narration; longer turns
  allowed.
- `register.py` bubble splitting — F2F is closer to a screenplay: one turn,
  one block, no typing-pause-timed reveal.
- `ui/terminal.py` rendering — a transcript/script layout instead of chat
  bubbles with name labels.
- Continuations become the default texture, not the occasional add-on — real
  conversation interrupts and overlaps constantly. Tier 1's cap-and-bias-to
  -hand-back would need much looser defaults for this mode (higher
  `CHAT_CONTINUATION_CHANCE`, and probably don't require addressing by name —
  people rarely say each other's names mid-conversation the way texters do).
- `policy.py`'s reply-length budget is tuned to a texting decode-rate target;
  F2F likely wants a different `CHAT_TARGET_REPLY_SECONDS`/length shape.

**Not decided yet:** how the mode is selected (per-scenario flag in the
markdown cast file vs. a CLI/env switch), and whether it needs its own
`Policy`/`Config` fields or just a second `_REGISTER` + render path keyed off
that flag. Needs a design pass before implementation — this is bigger than
Tier 1 continuations was.

Status: **not started**.

---

## Continuations Tier 2 — idle-timer

Raised: 2026-09-14 (as a plan item). Raised again 2026-09-15 as a live
complaint — "the chat waits for me to resume it... a little unnatural" —
which is exactly Tier 2's symptom, not a new issue. Built 2026-09-15.

**Built as:** the same `decide()` chain Tier 1 already runs after a human
turn, re-triggered by silence instead. Both front ends reuse the *existing*
`_continue`-shaped loop rather than inventing new logic:

- **Terminal** (`ui/terminal.py`'s `ask()`): races the `prompt_toolkit`
  `PromptSession.prompt_async()` against `asyncio.sleep(idle_seconds)` via
  `asyncio.wait(..., timeout=...)`. The prompt task is never cancelled on
  timeout — it keeps waiting for real stdin — the loop just calls `on_idle()`
  (which runs `_continue` on whatever `last_result` currently is) and then
  waits again. `patch_stdout()` wraps the whole thing so the idle turn's
  `rich` output can't corrupt the in-progress input line. Verified: builds
  cleanly with no real TTY attached (just prompt_toolkit's own "not a
  terminal" warning); full interactive behavior wants a manual check in a
  real terminal (no pty available this session).
- **Web** (`ui/web.py`): a new `POST /api/idle`, calling the same
  `_run_continuations()` generator `/api/turn` uses, against a `last["result"]`
  tracked across requests (seeded from the startup due-promises raise same as
  `/api/turn`). Client-side `index.html` resets a `setTimeout` on every turn
  completion and fires `/api/idle` on expiry; `/api/cast` now reports
  `idle_seconds` so the client knows the threshold.
- `src/__main__.py`'s `_continue` and `_raise_due_promises` now both return
  the final `TurnResult` (previously `_continue` returned `None`) so both
  front ends can track "what the conversation currently stands on" across the
  idle wait, not just within one exchange.
- New config: `CHAT_IDLE_SECONDS` (default 45, 0 disables).

**Verified via the mock-model TestClient harness** (same pattern as the GUI
verification): `/api/idle` before any turn correctly no-ops (`last["result"]`
is `None`); after a turn, with `CHAT_CONTINUATION_CHANCE=1.0` forced, it fires
and correctly caps at `CHAT_CONTINUATION_MAX`, charging debt correctly for
each forced speaker. Live-server verification (real idle wait, real model)
not done this session.

Status: **built**.

## Continuations Tier 3 / GUI

Raised: 2026-09-15. Built: 2026-09-15.

Before building, checked sibling projects for prior art per user request:
`story-engine` has no UI (pure CLI/pipeline, nothing to learn there).
`faaltoo-chat` already had a working local web UI (`my_code/ui/web.py` + a
single ~1900-line static `index.html`, vanilla JS, no build step) that shaped
the approach — SSE over a plain POST rather than a WebSocket, one global
in-process session (no auth/multi-tab), one entrypoint with a `--ui` flag
rather than a separate binary.

**Built as:**
- `src/ui/web.py` — FastAPI app. `POST /api/turn` streams SSE frames
  (`data: {...}`) for the human turn and every subsequent continuation turn in
  the same request, using the exact `Engine`/`Selector`/`continuation.decide()`
  from the terminal path — no engine or prompt changes, per
  `PLAN_CONTINUATIONS.md`'s Tier 2/3 promise. `GET /api/cast` and `/api/log`
  back the initial page load; a `Lifespan` raises due promises on startup and
  saves the session on shutdown, same as the terminal's `finally` block.
- `src/ui/static/index.html` — single-file vanilla-JS page: colored bubbles
  per character with the same stagger-reveal pacing as `Terminal.show()`, a
  side panel for `/state`/`/who`, a nudge button per character for `/next`.
- `src/bootstrap.py` — extracted the engine/session assembly that both front
  ends now share (`build_engine`/`save_session`), so terminal and web can't
  drift into building the engine two different ways.
- `src/transcript.py` — `Engine.history` → plain entries, shared by `/log`
  and the web UI's initial transcript fetch (previously duplicated inline in
  `ui/terminal.py`).
- Launch: `python -m src <scenario> --ui web` (`--host`/`--port` or
  `CHAT_WEB_HOST`/`CHAT_WEB_PORT`, default `127.0.0.1:8000`).

**Verified live** against the real model server in `.env`
(`google/gemma-4-12b-qat`) using the real `late_shift` scenario: correct cast
data over `/api/cast`, a real in-voice reply at ~3s latency, continuation rule
1 correctly holding back on an unaddressed question, and (via a deterministic
mock — `CHAT_CONTINUATION_CHANCE=0`) the "addressed" rule firing a real
continuation turn with debt charged correctly for the forced speaker. Session
save-on-shutdown confirmed via the lifespan hook. Not yet verified: sustained
multi-turn use in the actual browser (no browser tooling available this
session) — worth a manual pass before relying on it day-to-day.

**Not decided yet:** whether the terminal UI stays maintained long-term or the
web UI replaces it as the only front end. Both currently work and share all
underlying logic, so this is deferrable.

Status: **built** (Tier 1 continuations + this GUI = Tier 1–3 of
`PLAN_CONTINUATIONS.md` all delivered). `textual` was not pursued — the web
path won for the reasons above.

## Rut detection

From `DESIGN.md`: no per-character mechanism currently notices a character
collapsing into a verbal tic (e.g. asking a rhetorical question almost every
turn — the failure `chat-engine` shipped with). Planned shape: per-character
ring buffers of reply shape — opening n-gram, ends-in-question, length band —
checked after each turn. `metrics.py`'s `opener_variety` and
`question_balance` do something adjacent but only as a post-hoc harness score,
not a live guard during a real session.

Status: **not started**.

## Vision

Raised: 2026-09-15, revised same day after checking `faaltoo-chat`, built
2026-09-15.

First pass assumed the `faaltoo-chat` pattern — describe the image once via a
prose caption, discard the bytes, fold the caption into history as plain
text. Working through it further, that was rejected in favor of something
richer: **keep the image genuinely visible to the model on every turn**, not
flattened to one narrator description — because a probe against the real
server showed the character model (`google/gemma-4-12b-qat`) is *already*
multimodal, removing the sharpest risk (a second model needing to swap in,
evicting the character model's KV cache).

The remaining concern — raw bytes bloating `session.json` forever — was
solved with a reference + hydration split rather than by flattening the
image away: `Engine.history` stores only `{"type": "image_ref", "path": ...}`;
the real bytes live in a file beside the session and only get read back and
re-attached at the moment a request is actually built. See `DESIGN.md`'s
"Vision: hydrate at send time, never store the bytes" for the full rationale
— it was written as a permanent design note, not just a backlog entry, since
it's exactly the kind of thing `CLAUDE.md` says to read before touching
`engine.py` again.

**Built as:**
- `src/vision.py` — `probe_vision()` (adapted from `faaltoo-chat`'s
  synthetic-PNG approach, no Pillow needed for the probe itself),
  `save_attachment()` (downscale once via Pillow — installed, nothing new to
  add — to `CHAT_VISION_MAX_DIMENSION`), `image_ref()`, `hydrate()`.
- `probe.py`/`policy.py` — `vision_capable` measured and cached in
  `profiles/`, same shape as `structured_mode`.
- `engine.py` — `turn(..., image: bytes | None)`; hydrates `self.history`
  before both the main reply call and the classifier's tail
  (`_classifier_tail()`) — both needed it, since both send raw history to a
  model.
- `session.py` — `attachments_dir()`, colocated with the session file, never
  in this repo.
- `transcript.py` — carries `image_path` through so `/log` and the web UI's
  replay can show past images, not just text.
- Web UI: `/api/turn` takes `multipart/form-data` now (was JSON) to accept an
  optional file; new `GET /api/attachments/{name}` serves a saved image back
  (name validated — it's always a bare `<uuid>.jpg`, but checked anyway);
  `📎` control in `index.html`, shown only when `/api/cast` reports
  `vision_capable`.
- Terminal: `/image <path> [caption]`, same `vision_capable` gate, shown in
  the banner only when true.

**Verified against the live model server** (not a mock): a solid-color test
image correctly identified in-voice through `Engine.turn()` directly, then
again through the full web stack (`/api/turn` → SSE → `/api/log` →
`/api/attachments/{name}`, including a path-traversal probe that correctly
404s). The richer-capability bet paid off in testing too: a continuation
turn had a *second* character give an independent, differently-worded read of
the same image rather than repeating the first character's description —
exactly the thing flatten-to-prose would have prevented.

**Harness coverage added** (2026-09-15, same day): a `vision` suite in
`src/harness.py`, kept out of `all` since it needs a vision-capable model
(skips with a clear message otherwise). Attaches a synthetic solid-color
image (`vision.synthetic_png`, factored out of the probe's own test-image
code) on turn 2, refers back to it on turn 5 — three turns and two unrelated
replies later, deliberately, to test that `hydrate()` keeps re-sending the
real image rather than the model coasting on a one-time description that was
never actually stored. `run_suite` also builds the harness's `Engine` with a
real `attachments_dir` (a cleaned-up temp dir) instead of the default
`Path(".")`, which would otherwise litter the repo root with `.jpg` files the
moment a suite attaches one, and asserts *mechanically* that the image
reference survived in history (recall correctness itself stays unasserted,
same reasoning as promises — needs the model's cooperation). Live run: Dev
called the color "beige" on first seeing the tiny synthetic image, then
correctly called it "aggressive ochre... depressed orange" (true color was
burnt orange) three turns later when asked to recall it — only possible if
the real pixels were re-examined at that later turn, since no description was
ever cached anywhere to coast on. Composite 99.4/100, mechanical check 1/1.

Voice remains out of scope per `DESIGN.md`, no revisit planned — kept here
only so it isn't silently forgotten if priorities shift.

Status: vision **built**. Voice: **not started, not currently planned**.

---

## Housekeeping done alongside other work (for context, not pending)

- Request timeout on the inference client (`CHAT_REQUEST_TIMEOUT_SECONDS`,
  default 60s) — added 2026-09-14 after a session hang with no clear cause;
  the SDK default was a silent 10-minute wait.
- `/log` terminal command — added 2026-09-14, replays the full chat
  (user + character lines) from `Engine.history`, since there was previously
  no way to see it beyond live scrollback or reading the session JSON by hand.
