# ensemble-chat

A multi-character group chat that reads like texting, not like an LLM. You are a
participant, not a director — the characters reply to you, interrupt each other,
remember things across sessions, and follow up on things they said they'd do.

Runs against any OpenAI-compatible endpoint. Nothing is hardcoded to a model or
a machine.

## Install

```bash
cd /Volumes/d/code/aiml/ensemble-chat
python3 -m venv .venv && source .venv/bin/activate   # or any conda env — 3.11+
pip install -r requirements.txt
cp .env.example .env
```

Then edit `.env` (or export `SCENARIO_LOC` in your shell) to point at a
scenarios directory before doing anything else — see "Writing a scenario"
below; there is no in-project fallback, on purpose (rule 6 in `CLAUDE.md`).

This repo's own dev environment already has everything installed — see
"Run" below for the exact env it uses instead of a fresh venv.

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

(Substitute your own venv's `python` for `$PY` if you installed fresh above —
`$PY` here is just this dev setup's specific path, nothing the code requires.)

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
| `/log` | replay the full chat so far (user + character lines only), each reply tagged with its turn number for `/delete` |
| `/regenerate [guidance]` | redo the last reply, same speaker, with an optional short nudge (e.g. `/regenerate be blunter`). Only works while it's still the last thing that happened — a new message, a continuation, or an idle hop all invalidate it |
| `/delete <n>` | remove reply `<n>` (its turn number, from `/log`) and everything generated after it — asks for confirmation first, since it's irreversible once the session autosaves |
| `/image <path> [caption]` | attach an image (only shown if the model supports it) |
| `/quit` | exit (saves) |

After a reply, characters may answer each other for a few turns before
control comes back to you — addressed by name, a follow-up, or someone else
chiming in — capped and biased to hand back. See "Continuations" below.

### Autonomous / self-auto mode

Two unattended modes, terminal only, both bounded by a turn cap and/or a time
cap instead of you typing `/quit`:

```bash
PYTHONPATH=. $PY -m src late_shift --autonomous                       # no human at all
PYTHONPATH=. $PY -m src late_shift --auto-human                       # you're generated too
PYTHONPATH=. $PY -m src late_shift --autonomous --max-turns 20 --max-seconds 300
```

- `--autonomous` — the cast just talks to itself, no human turn ever happens.
- `--auto-human` — you're still a participant, but your own lines are
  generated instead of typed, using an optional `## You` persona from the
  scenario (see below) or a generic fallback if it's not defined.
- `--max-turns`/`--max-seconds` override `CHAT_AUTOPILOT_MAX_TURNS`/
  `CHAT_AUTOPILOT_MAX_SECONDS` for one run. Either mode also stops on Ctrl+C,
  saving normally on the way out.
- Mutually exclusive with each other, and with `--ui web` — start one of
  these against a scenario, then afterward point `--ui web` (or `/log`) at
  the same scenario to read back what was said; the session file is the same
  either way, so nothing extra is needed to view it once it's done.

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
- For `mode: f2f` scenarios specifically, the reply itself streams
  token-by-token as the model generates it, rather than appearing all at once
  when generation finishes — the engine already streams from the API either
  way, this just forwards it live instead of buffering. Scoped to F2F because
  it renders as one screenplay block; texting mode still delivers each reply
  whole so its bubble-split reveal isn't disturbed. The terminal UI streams
  F2F replies the same way, straight to the console as they arrive.
- A button per character stands in for `/next <name>`. The side panel is
  `/state` and `/who`, always visible rather than typed.
- A "↻ regenerate" button stands in for `/regenerate`, enabled only while
  there's still a last reply to redo. Clicking it prompts for an optional
  guidance nudge, then removes the old reply from the page and streams in
  its replacement (or replaces it outright for texting mode, which doesn't
  stream). Available once per session's worth of turns — it isn't restored
  from a resumed session on page load, only after at least one turn happens
  in the current browser session.
- Hovering a reply reveals a small "🗑 delete from here" control, standing
  in for `/delete <n>`. Confirms first (a plain browser `confirm()`), then
  removes that reply and everything generated after it and re-renders the
  chat from the now-shorter history. Works on any past reply, not just the
  last one, unlike regenerate — restored correctly on page load since it's
  driven off `/api/log`, not session-only client state.
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
| `CHAT_F2F_CONTINUATION_MAX` | same as above, for `mode: f2f` scenarios (default 4) |
| `CHAT_F2F_CONTINUATION_CHANCE` | same as above, for `mode: f2f` scenarios (default 0.35; addressing by name is boosted but decays with depth rather than being guaranteed — see `PLAN_F2F.md`) |
| `CHAT_TARGET_REPLY_SECONDS_F2F` | reply-length budget for `mode: f2f` scenarios (default 11.0, vs. 2.5 for texting) |
| `CHAT_IDLE_SECONDS_F2F` | idle-timer threshold for `mode: f2f` scenarios (default 120, vs. 45 for texting — F2F's turns already run longer; 0 disables it for f2f only, same as `CHAT_IDLE_SECONDS` does for texting) |
| `CHAT_WEB_HOST` | web UI bind address (default `127.0.0.1`) |
| `CHAT_WEB_PORT` | web UI port (default `8000`) |
| `CHAT_IDLE_SECONDS` | seconds of silence before the cast re-checks whether to keep talking (default 45, 0 disables) |
| `CHAT_VISION_MAX_DIMENSION` | longest edge an attached image is downscaled to before it's saved or sent (default 1024) |
| `CHAT_AUTOPILOT_MAX_TURNS` | stop `--autonomous`/`--auto-human` after this many replies (default 40) |
| `CHAT_AUTOPILOT_MAX_SECONDS` | stop `--autonomous`/`--auto-human` after this long, whichever hits first (default 900) |

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
PYTHONPATH=. $PY -m src.harness rut       # seeds a stuck opener, checks the nudge fires
PYTHONPATH=. $PY -m src.harness f2f --scenario <a mode: f2f scenario>   # screenplay register
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

`rut` is also separate and not part of `all` — it deliberately pre-loads
`RutTracker` with five identical stuck-opener replies before the script runs,
so the nudge fires on the very first turn instead of waiting for a character
to organically repeat itself, then checks the real outgoing directive
mechanically for the nudge text. See `PLAN_RUT_DETECTION.md`.

`f2f` needs a scenario with a `mode: f2f` line (see "Writing a scenario"
below) — pass one with `--scenario`; it skips with a clear message against a
text-mode scenario. It scores a different metric set (`brevity` and
`no_narration` are texting-only expectations F2F's register deliberately
violates on purpose) and its composite isn't comparable to `short`/`long`.
See `PLAN_F2F.md`.

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
| `opener_variety` | a character reusing one sentence shape — the rut failure (a post-hoc score; `RutTracker` in `src/engine.py` now also catches and nudges this live, mid-session — see `PLAN_RUT_DETECTION.md`) |
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

### Giving "you" a persona

Optional, and only used by `--auto-human` (see above) — everything else
about a scenario is unaffected by whether this section exists:

```markdown
## You

- name: Riya
A tired analyst who texts in lowercase, short and a little blunt. Overshares
about work stress, deflects with humor when called out.
```

`name:` is what the generated human is called (defaults to `"you"` if
omitted); the rest is free-text persona, same voice-not-biography advice as a
character. Leave the section out entirely and `--auto-human` falls back to a
generic "ordinary participant" persona instead — every scenario written
before this feature existed still parses and runs exactly as it did before.

### F2F mode

A one-line flag right after the title switches the whole register from
texting to in-person:

```markdown
# Kitchen Table
mode: f2f

Priya, Dev and Meera end up in the kitchen after everyone else has gone to bed.
```

No other schema change — the `## Characters` block is identical either way, a
personality doesn't change based on the medium. What does change is the
setting prose itself: "texting because everyone's apart" and "sitting in the
same room" are different facts about the scene, so converting a scenario to
F2F usually means writing a different setting, not just adding the flag.

With `mode: f2f`: replies read like short-story prose, not a chat
transcript — quoted dialogue with action and attribution woven into the same
sentence (`"Worst food I've had all year," Priya says, pushing her plate
away.`), action optional rather than something every turn needs. Since you
have no character block in the scenario, narration refers to you as "you" —
the register explicitly forbids the model inventing a label like "the human"
when it needs to mention you in third-person prose. Turns run
longer (`CHAT_TARGET_REPLY_SECONDS_F2F`) and render as one prose block instead
of split text bubbles. Continuations run looser
(`CHAT_F2F_CONTINUATION_MAX`/`CHANCE`) than texting's, decaying with each hop
rather than guaranteeing the next speaker forever — an early version made
every address-by-name a certainty, which meant characters naming each other
mid-conversation (completely normal dialogue) chained through the whole cast
on nearly every human line. Its idle timer also runs longer
(`CHAT_IDLE_SECONDS_F2F`) since F2F's turns already take longer to generate.
The one rule that doesn't change: a line that asks *you* something still
hands the floor back immediately, in both modes. No `mode:` line at all keeps
every existing scenario exactly as it behaved before this feature existed.
See `PLAN_F2F.md`.

The terminal UI needs no changes for this — an F2F turn is just a single,
longer block, so it prints as one line same as always. The web UI's
chat-bubble CSS is scoped off for `mode: f2f` scenarios (`body.f2f` in
`src/ui/static/index.html`): no bubble background or rounded box, the human's
own line renders as a plain labelled line instead of a right-aligned blue
bubble, and a stray `*aside*` (rare now that action is prose, not asterisks)
still italicizes if the model emits one out of habit.

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
just calls `/api/idle` client-side. `CHAT_IDLE_SECONDS=0` disables it — but
`mode: f2f` scenarios use the separate `CHAT_IDLE_SECONDS_F2F` threshold, so
set both to `0` to disable idle-triggered continuations everywhere.

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

`/regenerate` and `/delete` are the two deliberate exceptions: `/regenerate`
truncates history back to just before the last reply and redoes it;
`/delete <n>` truncates back to just before an arbitrary earlier reply and
leaves it truncated. Both only ever fire on explicit user action (`/delete`
asks for confirmation first), and both pay a full cache-reprocess on the
next request as a result — accepted as an occasional cost, not a hot-path
one. `Engine` tracks a checkpoint (history position, speaking debt, last
speaker, rut state) per reply specifically so either can roll everything
back correctly, not just the history list.

## Status

Working: multi-character turn-taking, texting register, affect/threads/traits
tracking, cross-session memory, promise-keeping, continuations including the
idle-timer (Tiers 1–3 — see `PLAN_CONTINUATIONS.md`), a local web UI, vision
(on models that support it — probed, not assumed), live rut detection (see
`PLAN_RUT_DETECTION.md`), an F2F/in-person mode (see `PLAN_F2F.md`), and
autonomous/self-auto unattended modes (terminal only — see "Autonomous /
self-auto mode" above, and `BACKLOG.md`).

Not built yet: a scripted user-side eval harness (the fixed scripts in
`src.harness` cover this today; a model-generated simulated human is a
different, unbuilt thing — see `BACKLOG.md`), and F2F's web-UI styling, which
works but still looks like a texting bubble rather than a screenplay block.

Known rough edge: long sessions are untested past ~20 turns. `RutTracker`
watches for one character collapsing into a repeated opener, question-heavy
pattern, or flat reply length mid-session and nudges against it, but broader
voice drift beyond those specific shapes is still something to watch for by
reading the transcript.

Known bug, terminal-only, cosmetic: F2F streaming can briefly show a raw
`"Name: "` echo if the model's own output happens to start that way — the
saved session, `/log`, and the web UI are all unaffected. See `BACKLOG.md`.
