# Plan — Tier 1 continuations

Status: **Tiers 1, 2 and 3 all built** (2026-09-14 / 2026-09-15). `src/continuation.py`,
the debt-charging fix, and the harness changes described below are all in.
Tier 3 landed as a local web UI (`src/ui/web.py`); Tier 2 (idle-timer,
`CHAT_IDLE_SECONDS`) landed in both the terminal and web front ends, reusing
the same `decide()`/`_continue` chain as Tier 1 rather than new logic — see
`BACKLOG.md`'s "Continuations Tier 3 / GUI" and "Continuations Tier 2 —
idle-timer" entries for the design and what was verified (mock-model
TestClient coverage; live-server idle behavior and real-terminal interactive
use are not yet manually verified). Read `CLAUDE.md` and `DESIGN.md` first;
the rules there still bind, especially append-only history and never
awaiting the classifier.

Two things landed alongside Tier 1, found while dogfooding it, documented in
`README.md`/`.env.example` rather than here since they aren't continuation-specific:
- `AsyncOpenAI` had no request timeout, so a stalled server looked like an
  indefinite hang. Fixed via `CHAT_REQUEST_TIMEOUT_SECONDS` (default 60s).
- `/log` — there was no way to see the full chat from inside the terminal UI;
  it only replayed live. Added a command that reprints the whole history.

## The problem

Right now every character line requires a human line first. Real group chats
don't work that way: people answer each other, and fire off a second thought
before you've replied. A real session produced this —

```
Dev    sorry lol
       my brain is just fried from work.
       pria please dont roast me.
you    I think Priya is off to sleep. Whatsup at work?
```

Dev addressed Priya by name and Priya never answered. The human had to
manually keep the conversation alive.

## What already exists

`Engine.turn("")` generates a character turn with no user input — that is what
`/next <name>` calls. So **no engine changes are needed to make characters
speak unprompted**, and continuations are pure appends, so there is no prompt
cache cost. This is a UI-and-orchestration job.

The decision logic ("should someone speak, and who?") is deliberately separable
from delivery. Tier 2 (idle-timer continuations via `prompt_toolkit`, already
installed) and Tier 3 (live, via `textual` or a web UI) reuse the same policy
and only change the input layer. Nothing built here is throwaway.

## Design

New module `src/continuation.py`, pure decision logic, no I/O:

```python
@dataclass(frozen=True)
class Continuation:
    speaker: str | None   # None = let the selector pick
    reason: str           # addressed | joinder | spontaneous
    directive: str        # extra_directive passed to Engine.turn

def decide(scenario, result, depth, cfg, rng) -> Continuation | None
```

Rules, evaluated in order:

1. **Hand back to the human** if the reply asks *them* something — ends with
   `?` and names no other character. The human must stay a participant.
2. **Stop** if `depth >= cfg.continuation_max` (default 2).
3. **Addressed** — `Selector._addressed(result.text)` returns a character other
   than the speaker. That character answers. Near-certain; this is the case
   from the transcript above and the main win.
   Directive: `"Reply to what {speaker} just said."`
4. **Joinder** — small chance (~15%) the same speaker adds a follow-up.
   Requires `force_speaker=result.speaker.name` to bypass the selector's
   exclusion of the last speaker.
   Directive: `"Add one short follow-up to what you just said."`
5. **Spontaneous** — small chance (~20%) someone else chimes in. Leave
   `speaker=None`; the selector already excludes the last speaker.
6. Otherwise stop.

The directive matters. An empty-user turn with no steer tends to restate rather
than advance.

## Wiring

- `src/__main__.py` — after `_play(...)`, loop: `decide(...)` → `_play` again
  with the returned speaker/directive, incrementing depth, until it returns
  `None`. Keep it in `_play`'s caller, not inside `Engine`.
- `src/ui/terminal.py` — a slightly longer pause before a continuation turn
  than between bubbles, so it reads as someone else picking up the thread.
- `src/config.py` — `CHAT_CONTINUATION_MAX` (default 2) and
  `CHAT_CONTINUATION_CHANCE` (default 0.25). `0` disables the feature. Nothing
  hardcoded; see CLAUDE.md rule 5.

## Fix this at the same time

**Forced speakers don't charge speaking debt** (verified 2026-09-14:
`engine.py:111-112` short-circuits `Selector.select`, and the debt increment
lives inside it at `selector.py:31`). In `Engine.turn`:

```python
forced = self.scenario.by_name(force_speaker) if force_speaker else None
speaker = forced or self.selector.select(user_text, self.last_speaker)
```

When forced, `Selector.select` never runs, so `debt` is not incremented. Today
that only affects `/next`. Once continuations use `force_speaker` routinely the
weighting will drift and `turn_distribution` in the harness will degrade.

Fix: extract the debt increment out of `Selector.select` into a `charge(char)`
method and call it for forced speakers too. (`chat-engine`'s orchestrator does
exactly this — "record it but still update debt".)

## Harness

`src/harness.py` records one `Turn` per script line, so continuation turns would
be generated but **not scored**. Two changes:

- Capture every turn, not just the scripted one.
- Default the suites to `continuation_max=0` so scores stay comparable to the
  numbers already recorded. Add a `--continuations` flag to exercise the feature
  separately; expect more variance when it is on.

`opener_variety` gets more data per character with continuations on, which makes
it a better rut detector.

## Verify

1. The transcript case: a reply naming another character gets answered.
2. Never more than `continuation_max` in a row.
3. A character asking the human something ends the chain immediately.
4. `/who` shows debt still tracking weights after a long session.
5. Burst latency stays tolerable — each continuation is a full generation
   (~2–4s on gemma-4-12b-qat).

## Do not

- Do not make continuations always-on or deep. The failure to avoid is the one
  diagnosed in `chat-engine`: the human becomes a spectator being narrated at
  rather than a participant. Cap hard, bias toward handing back.
- Do not touch prompt assembly or history handling.
- Do not await the state classifier.
