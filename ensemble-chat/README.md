# ensemble-chat

A multi-character group chat that reads like texting, not like an LLM. You are a
participant, not a director — the characters reply to you, interrupt each other,
remember things across sessions, and follow up on things they said they'd do.

Runs against any OpenAI-compatible endpoint. Nothing is hardcoded to a model or
a machine.

## Run

The conda env lives off the default path, and `src` is imported as a package, so
both of these matter:

```bash
cd /Volumes/d/code/aiml/ensemble-chat
export PY=/Volumes/d/conda/conda_envs/strandsagents/bin/python
export SCENARIO_LOC=/path/to/your/scenarios     # required

PYTHONPATH=. $PY -m src.probe      # measure this host+model (do this first)
PYTHONPATH=. $PY -m src.policy     # show the constants derived from that profile
PYTHONPATH=. $PY -m src            # chat, terminal UI
PYTHONPATH=. $PY -m src late_shift --fresh      # named scenario, ignore saved session
PYTHONPATH=. $PY -m src late_shift --ui web     # chat, web UI at http://127.0.0.1:8000
```

Scenarios live outside the project, wherever `SCENARIO_LOC` points. Either
layout works — a flat folder of `.md` files, or a parent holding one folder per
scenario:

```
scenarios/late_shift.md          SCENARIO_LOC=.../scenarios
scenarios/late_shift/late_shift.md   SCENARIO_LOC=.../scenarios  or  .../late_shift
```

The positional argument takes a bare name (`late_shift`, `.md` optional) looked
up in either shape, or an explicit path to any file. With no argument it uses
the only scenario present, or lists them if there is more than one.

`src.probe` takes about 30 seconds and only needs re-running when you change
model or server.

### In-chat commands

| command | does |
|---|---|
| `/next <name>` | make someone speak unprompted |
| `/who` | speaking debt and history size |
| `/state` | mood, threads, traits, promises currently tracked |
| `/log` | replay the full chat so far (user + character lines only) |
| `/image <path> [caption]` | attach an image (only shown if the model supports it) |
| `/quit` | exit (saves) |

After a reply, characters may answer each other for a few turns before
control comes back to you — addressed by name, a follow-up, or someone else
chiming in — capped and biased to hand back. See "Continuations" below.

## Web UI

`--ui web` starts a small local FastAPI app instead of the terminal loop
(`--host`/`--port` or `CHAT_WEB_HOST`/`CHAT_WEB_PORT` to change where it
binds; loopback-only by default — this is a personal local tool, not
something to expose). Same `Engine`, same session file, same continuation
policy — only the delivery layer differs:

- The reply streams back over Server-Sent Events on the same POST that sent
  your message (`/api/turn`), not a WebSocket — which composes naturally with
  continuations: the same stream just keeps yielding turns, human or
  continuation, until the chain ends.
- A button per character stands in for `/next <name>`. The side panel is
  `/state` and `/who`, always visible rather than typed.
- One process, one in-process session — there's no login and no multi-tab
  support, on purpose; run one instance per scenario, the same as the
  terminal UI.

Ctrl-C shuts it down the same way as the terminal UI — the session saves on
the way out.

## Where the chat is stored

By default, **beside the scenario** as `<name>.session.json`, so each scenario
folder is a self-contained unit of cast plus history and nothing personal lands
in this repo:

```
prod/ensemble/late_shift/late_shift.md
prod/ensemble/late_shift/late_shift.session.json
```

Set `SESSION_LOC` to collect chats somewhere else instead; files there are named
`<name>-<hash>.json`, the hash being of the scenario's full path so two
scenarios sharing a filename can't clobber each other.

The file holds the whole message history, the tracked state (affect, threads,
traits, promises), speaking debt and last speaker. It saves after **every**
turn, atomically (write-then-rename, so a kill mid-write can't corrupt it) —
not just on a clean exit. A killed terminal, a crashed process, or an
impatient double Ctrl-C (which force-aborts the web UI's shutdown before it
can run its own final save) costs at most the one turn that was actively
in-flight, never the session before it. Delete the file or pass `--fresh` to
start over.

## Configuration

All of it lives in `.env` — copy `.env.example`.

| variable | meaning |
|---|---|
| `SCENARIO_LOC` | directory holding scenario `.md` files, outside this project |
| `SESSION_LOC` | optional; where chats are written. Unset = beside the scenario |
| `CHAT_BASE_URL` | any OpenAI-compatible endpoint |
| `CHAT_MODEL` | model id as the server reports it |
| `CHAT_CONTEXT_TOKENS` | declared, not probed — probing it means overflowing the server |
| `CHAT_PARALLEL_SLOTS` | informational; real concurrency is measured by the probe |
| `CHAT_TEMPERATURE` | 0.9 suits character work |
| `CHAT_TARGET_APPEND_MS` | latency budget the state-block size is derived from |
| `CHAT_TARGET_REPLY_SECONDS` | latency budget the reply length is derived from |
| `CHAT_REQUEST_TIMEOUT_SECONDS` | fail a stalled request loudly instead of hanging (default 60) |
| `CHAT_CONTINUATION_MAX` | how many characters can speak in a row before control returns to you (default 2, 0 disables) |
| `CHAT_CONTINUATION_CHANCE` | base chance of a follow-up or a third party chiming in (default 0.25) |
| `CHAT_WEB_HOST` | web UI bind address (default `127.0.0.1`) |
| `CHAT_WEB_PORT` | web UI port (default `8000`) |
| `CHAT_IDLE_SECONDS` | seconds of silence before the cast re-checks whether to keep talking (default 45, 0 disables) |
| `CHAT_VISION_MAX_DIMENSION` | longest edge an attached image is downscaled to before it's saved or sent (default 1024) |

Change the model, re-run `src.probe`, and reply length, state-block size,
history strategy and the background-task flag all re-derive from measurement.
Profiles are keyed per host+model, so switching back doesn't re-probe. With no
profile at all the app still starts on conservative defaults — it just runs
untuned, and the banner says so.

## Evaluating quality

```bash
PYTHONPATH=. $PY -m src.harness short     # 5 turns  — smoke test and latency
PYTHONPATH=. $PY -m src.harness long      # 24 turns — where repetition shows up
PYTHONPATH=. $PY -m src.harness all --save report.txt
PYTHONPATH=. $PY -m src.harness long --continuations   # exercise continuations too
PYTHONPATH=. $PY -m src.harness vision    # image attached, referred back to 3 turns later
```

Both `short`/`long` (and `all`, which bundles them) run a **fixed** human
script against the cast, print the transcript, and score it. Evaluation never
touches your saved session — the engine starts empty and writes nothing
unless you pass `--save`; a synthetic test image is written to a temp
directory that's cleaned up on exit, never this repo.

`vision` is separate and not part of `all` — it needs a vision-capable
model (probed, same as the app itself; skips with a clear message if not) and
attaches a synthetic solid-color image on turn 2, then asks what color it was
on turn 5, three turns and two unrelated replies later. That gap is the point:
it's checking that `vision.hydrate()` re-sends the real image on every turn
that needs it, not just the one right after it was attached — a character
correctly recalling the color three turns on (rather than just reacting to it
immediately) is good evidence the mechanism, not a lucky guess, is what's
working. Whether the color is actually *right* isn't asserted — that needs
the model's cooperation — but whether the reference mechanically survived in
history is, and prints as a pass/fail line of its own.

Continuation turns are off by default so scores stay comparable run to run;
`--continuations` scores those turns too and expect more variance when it's on.

The human side is scripted rather than model-generated on purpose: score changes
then reflect changes to the engine, not variance in a simulated user, and it
avoids the trap where the simulated human is primed with the cast's own persona
and both sides end up sounding alike.

| metric | catches |
|---|---|
| `tic_free` | assistant-voice leaking in ("is there anything else") |
| `brevity` | replies drifting from texting into essays |
| `opener_variety` | a character reusing one sentence shape — the rut failure |
| `question_balance` | interrogation mode, every line ending in "?" |
| `no_narration` | asterisk actions and stage directions |
| `voice_integrity` | speaking as someone else, or self-labelling "Name:" |
| `lexical_diversity` | global repetitiveness |
| `turn_distribution` | speaking shares tracking the scenario weights |
| `state_health` | memory capturing what the script put in front of it (long only) |

Read the composite as approximate. At temperature 0.9 a 2-3 point move between
runs is noise; 10 points is real. A metric with too little data to judge shows
`n/a` and is excluded rather than being awarded full marks.

**These measure mechanical texture, not writing quality.** A 95 means the output
doesn't read like an LLM. Whether it reads like *these particular people* still
needs your eyes on the transcript — which is why the transcript always prints.

## Writing a scenario

Plain markdown. Everything before `## Characters` is the setting.

```markdown
# Late Shift

A group chat that has been alive for eleven years. You are the fourth member.

## Characters

### Priya
weight: 1.0
Blunt to the point of rudeness with people she likes, which is how you can
tell. Types fast and badly, doesn't fix typos. Deflects anything about her own
life into a question about yours.
```

`weight` is how often they speak relative to the others (default 1.0). A 0.55
character speaks roughly half as often as a 1.0 one, but still gets pulled in
when addressed by name.

Write the description as **voice**, not biography. "Types fast and badly,
doesn't fix typos" produces a character; "is a 34-year-old operations manager"
produces a résumé. The single biggest quality lever in this whole system is how
these paragraphs are written.

## Continuations

Real group chats don't wait for you to reply to every line — people answer
each other, or fire off a second thought unprompted. After each reply, the
engine decides whether someone else should speak next, with no new input from
you:

1. If the reply asks *you* something and names no other character, it stops —
   you stay a participant, not a spectator.
2. Otherwise, if the reply names another character, that character answers.
3. Small chance the same speaker adds a short follow-up, or someone else jumps
   in.
4. Capped at `CHAT_CONTINUATION_MAX` in a row either way.

This is pure decision logic in `src/continuation.py` — no engine or prompt
changes, so it costs nothing extra against the cache. See
`PLAN_CONTINUATIONS.md` for the design.

**Idle-timer:** after `CHAT_IDLE_SECONDS` of you not sending anything, the
same `decide()` check re-runs on wherever the conversation currently stands —
so most idle ticks do nothing (rule 1 held back, or just a missed roll), and
occasionally the cast picks the thread back up on its own, the way a real
group chat doesn't just freeze because you stepped away. Works identically in
both UIs: the terminal races the input prompt against the timer with
`prompt_toolkit` (so it can't corrupt whatever you're mid-typing), the web UI
just calls `/api/idle` client-side. `CHAT_IDLE_SECONDS=0` disables it.

## Vision

If the configured model accepts image input — probed once, like every other
capability here, never assumed — you can attach one image per turn: drag one
onto the web UI's composer (📎), or `/image <path> [caption]` in the terminal.
`/api/cast` (and the terminal banner) only show the control at all when the
probe found it supported.

The image is downscaled once to `CHAT_VISION_MAX_DIMENSION` and saved beside
the session — never inside this repo, never inlined into `session.json`.
`Engine.history` only ever stores a small reference to that file; the real
bytes get re-read and re-attached fresh every time a request actually needs
them (your reply, and later ones, and the background classifier's tail). That
reference is appended once and never rewritten, same as everything else in
history — see `DESIGN.md`'s "Vision" section for why it has to work this way
rather than either flattening the image to one shared text description or
inlining it into the stored history directly.

Because the real pixels go out on every request that includes that turn, not
just a one-time caption, different characters can — and did, in testing —
notice different things about the same photo instead of parroting one
canned description back.

No separate vision model, no dual endpoint: it's the same model that voices
the cast, or the feature is simply off this session.

## How it works, briefly

Each turn: pick a speaker (direct address wins, else lowest weighted speaking
debt) → generate a short reply → classify the conversation state in the
background → append any state change to the history for the next turn.

The system prompt is built once and never changes. Everything volatile is
appended. See `DESIGN.md` for why that matters more than anything else here.

## Status

Working: multi-character turn-taking, texting register, affect/threads/traits
tracking, cross-session memory, promise-keeping, continuations including the
idle-timer (Tiers 1–3 — see `PLAN_CONTINUATIONS.md`), a local web UI, and
vision (on models that support it — probed, not assumed).

Not built yet: rut detection (catching a character collapsing into a verbal
tic) and an F2F/in-person register mode. See `BACKLOG.md`.

Known rough edge: long sessions are untested past ~20 turns. Character voice
drift is the thing to watch for, and there is currently nothing that detects it.
