# Plan — Rut detection

Status: **built** (2026-09-15). Read `CLAUDE.md` and `DESIGN.md` first — the
rules there still bind, especially append-only history and never mutating the
system prompt mid-session.

**Built as:** `src/rut.py` (`RutTracker`, exactly as designed below — no
changes from the plan) wired into `src/engine.py`: `self.rut = RutTracker()`
in `__post_init__`, `self.rut.nudge(speaker.name)` folded into the per-turn
directive before the continuation's `extra_directive`, `self.rut.record(...)`
after a reply is finalized. No `.env`/`Config` changes, no history schema
change.

**Verified:**
- Unit-level (`RutTracker` in isolation): a run of varied replies never
  nudges; a run of same-opener replies nudges by the 4th sample; a run of
  question-heavy replies nudges independently.
- Full harness (`python -m src.harness all` against
  `SCENARIO_LOC=/Volumes/d/code/aiml/prod/ensemble/late_shift`, real model):
  composite 99.4/100 (short) and 99.9/100 (long), unchanged from pre-rut
  baseline — no regression from the tracker sitting in the turn loop.
- Live, end-to-end, against the real model and the real `late_shift`
  scenario: pre-seeded `Priya`'s buffer with 5 identical-opener replies,
  spied on the actual `messages` sent to `client.chat.completions.create`,
  confirmed the outgoing system directive contained the nudge text
  (`"Don't open with the same phrase you've used recently. Vary how long
  this reply is from your recent ones."`), and the model's real reply used a
  different opener than the seeded pattern.

**Harness suite added** (2026-09-15, same day): `python -m src.harness rut`.
Seeds `RutTracker` with 5 identical stuck-opener replies for
`scenario.characters[0]` (resolved at runtime via a `"__first__"` key so the
suite isn't tied to the repo's default cast names), forces every scripted
turn to that same character via `force_speaker`, then mechanically asserts
the nudge text reached the real outgoing directive by scanning
`engine.history` for the nudge's marker phrases — not asserting the model
*complies* (same reasoning as promises/vision-recall: needs the model's
cooperation, read the transcript for that). Kept out of `all` (like
`vision`) since it deliberately mutates tracker state before the script
runs, so its score isn't comparable to a normal run. Verified live against
`late_shift`: `rut nudge reached outgoing directive: True` on turn 1.

## The problem

`DESIGN.md` names the failure directly: sibling project `chat-engine` shipped
with one character asking a rhetorical question in nearly every turn across a
long real session, and nothing noticed. This app has the same exposure today.
`src/metrics.py`'s `opener_variety` and `question_balance` catch this, but
only as a post-hoc harness score over a finished transcript — nothing watches
a *live* session, so a character can collapse into a verbal tic for the rest
of a real chat and the only way to find out is to remember to run the harness
or read back a long scrollback by hand.

## Goal

Notice a character sliding into a mechanical tic *during* the session, and
correct course automatically — nudge the next generation away from it via an
extra directive, the same mechanism `continuation.py` already uses to steer a
reply. Not a semantics or content check; purely reply-shape, same spirit as
the existing harness metrics.

## Decision: keep it small and independent

A new module, `src/rut.py`, holding one class, `RutTracker`. It does not
share code or a base class with `metrics.py` — that module does a single pass
over a whole finished transcript; this one is live and incremental, updated
one reply at a time as the session runs. Forcing them to share an
abstraction now would either make the harness stateful for no reason or make
the live tracker do a full-transcript rescan every turn. They can converge
later if a real duplication shows up; today the only thing in common is "count
openers and question-endings," which is a few lines each, not worth an
abstraction.

`RutTracker` takes no dependencies (no `Scenario`, no `Config` object it has
to reach into) — just per-character ring buffers of recent reply shape, plus
whatever thresholds it needs. It lives next to `Selector` conceptually (both
are small per-character-state trackers `Engine` owns) but is a fully separate
object, not a method bag hung off `Selector`.

## Design

```python
# src/rut.py
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

_WINDOW = 6          # replies remembered per character
_MIN_SAMPLES = 4     # don't judge on too little data
_OPENER_WORDS = 3    # how much of the start counts as "the opener"


@dataclass
class _Shape:
    opener: str
    ends_in_question: bool
    length: int


@dataclass
class RutTracker:
    window: int = _WINDOW
    _by_speaker: dict[str, deque[_Shape]] = field(default_factory=dict)

    def record(self, speaker: str, text: str) -> None:
        """Call once per generated reply, after it's finalized."""
        buf = self._by_speaker.setdefault(speaker, deque(maxlen=self.window))
        buf.append(_shape_of(text))

    def nudge(self, speaker: str) -> str:
        """Directive fragment to steer the next reply away from a detected
        tic, or "" if nothing's stuck. Call before generating."""
        buf = self._by_speaker.get(speaker)
        if not buf or len(buf) < _MIN_SAMPLES:
            return ""
        notes = []
        if _opener_stuck(buf):
            notes.append("don't open with the same phrase you've used recently")
        if _question_heavy(buf):
            notes.append("don't end this one in a question")
        if _length_flat(buf):
            notes.append("vary how long this reply is from your recent ones")
        return " ".join(notes)
```

Thresholds (exact values to tune while testing, not treated as load-bearing
constants worth a `.env` knob — see "Not configurable" below):

- **opener stuck**: the same first-`_OPENER_WORDS`-word opener (lowercased,
  punctuation-stripped — reuse the normalization `metrics.py::_opener`
  already does, but call it locally rather than importing from `metrics.py`,
  to keep the two modules independent per the decision above) appears in
  more than half the window.
- **question heavy**: more than ~70% of the window ends in `?` — same bar
  `metrics.py::question_balance`'s `_QUESTION_OK` already encodes; pick the
  same number so the live nudge and the harness score agree on what "too
  many" means, but as a literal copied constant, not a shared import.
- **length flat**: all replies in the window fall within a narrow band (e.g.
  every length within 20% of the window's mean) — the one signal
  `metrics.py` doesn't already compute, new to this module.

## Wiring

`src/engine.py`:

- `Engine.__post_init__` — `self.rut = RutTracker()`, alongside
  `self.selector = Selector(...)`.
- In `Engine.turn`, right where `directive` is assembled (before the
  `extra_directive` from continuations is folded in):
  ```python
  directive = speaker_directive(speaker.name)
  if nudge := self.rut.nudge(speaker.name):
      directive = f"{directive} {nudge}"
  if extra_directive:
      directive = f"{directive} {extra_directive}"
  ```
  Rut nudges and continuation directives can coexist in the same turn; they
  address different things (shape vs. content) and both are just appended
  text, so order doesn't matter beyond keeping the existing continuation
  suffix last.
- After the reply is finalized (where `self.last_speaker = speaker.name` is
  set), call `self.rut.record(speaker.name, text)`.

No change to `history` — the nudge is folded into the same per-turn system
directive message that already gets appended (`self.history.append({"role":
"system", "content": directive})`), so this doesn't add a new append-only
history entry type or touch anything already in history. No change to
`selector.py`, `continuation.py`, `prompt.py`, or the system prompt.

## Not configurable

Per `CLAUDE.md` rule 5, tunables that are genuinely about model/hardware
capability belong in `.env`. The rut thresholds aren't that — they're a
judgment call about what "too repetitive" means, closer to the
`_QUESTION_OK` constant already hardcoded in `metrics.py`. Keep them as
module-level constants in `src/rut.py`, not new `Config`/`.env` fields.
Revisit only if real sessions show the defaults are wrong for a specific
scenario.

## Harness

`src/harness.py` doesn't need to change to exercise this — `RutTracker` runs
inside `Engine.turn` regardless of caller, so harness suites already pick it
up for free once wired. What's worth adding:

- A `rut` suite (or an addition to an existing long suite): a scripted
  scenario baited to make one character repeat an opener or over-question,
  asserting the *directive sent to the model* on a later turn contains a
  nudge (mock-model harness can inspect the request messages directly,
  same as other mechanical checks) — not asserting the model actually
  changes its behavior, since that needs the model's cooperation, same
  caveat `CLAUDE.md`'s testing section already gives for promises.

## Verify

1. Unit-level: feed `RutTracker.record` a synthetic run of replies that all
   start "Yeah so" — confirm `nudge()` fires by the `_MIN_SAMPLES`'th call
   and not before.
2. Same for a run of replies that all end in `?`.
3. Confirm a normal, varied run never fires a nudge (no false positives on
   healthy dialogue) — feed it the transcript from an existing harness run
   if one gives varied output.
4. Live session: run a real scenario long enough to accumulate `_WINDOW`
   replies per character, check `/log` or the transcript for whether a
   nudged reply actually reads differently, not just whether the nudge text
   was sent.
5. Confirm latency is unaffected — this is pure in-memory bookkeeping, no
   new model call, so it should be free; verify no accidental await/extra
   round trip snuck in.

## Do not

- Do not merge this with `metrics.py` into one shared module. Different
  cadence (incremental vs. whole-transcript), different callers, kept
  separate on purpose.
- Do not make `RutTracker` reach into `Scenario`, `Config`, or `Selector` —
  it should take a speaker name and text and nothing else, so it stays easy
  to unit test and easy to delete if it turns out not to help.
- Do not add a new history entry type or persist rut state across sessions —
  it's a within-session live signal only; a fresh session starts with empty
  buffers, same as `Selector.debt` does today.
- Do not touch prompt assembly, the system prompt, or await anything new in
  the turn loop.
