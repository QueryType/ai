# Backlog — discussions and decisions

Running log of things raised in conversation that aren't built yet, so a later
session doesn't have to re-derive them. Each entry: the idea, the decision (if
one was made), and current status. Newest on top. Promote an entry to its own
`PLAN_*.md` (see `PLAN_CONTINUATIONS.md`) once it's actually being built.

## Idea: show scene setting at session start — scoped, not built

Raised: 2026-09-19, while live-testing autonomous mode with a new model.
Today's banner (terminal) and header (web) show the title, character names,
and model info, but never the scenario's own setting/premise text — you only
see it by reading the `.md` file directly.

**Scope, agreed but not yet built:**
- `Scenario.setting` already exists (`cast.py`) and is already parsed for
  every scenario — this is purely a display gap, no schema change.
- Terminal (`ui/terminal.py`'s `banner()`): print the setting as a wrapped,
  dim line between the title and the character list.
- Web (`ui/web.py` + `index.html`): add `setting` to the `/api/cast`
  payload; show it as a small collapsible section at the top of the sidebar
  (`aside`), above "what the cast has picked up on you" — collapsible so it
  doesn't eat space during a long session.
- Deliberately showing the *scene*, not the *characters* — the character
  roster is already visible (names in the header/meta line); this fills the
  other gap, what the scene actually is.

Status: **scoped, not built** — picked resume verification (see below) to
do first instead.

---

## Bug: F2F/autonomous replies compounding a "Name: Name: ..." prefix chain — found and fixed 2026-09-19

Found live: running `--autonomous` for 20 turns against a newly-tried model
(`qwen3.6-35b-a3b`) produced replies that accumulated a growing chain of
other characters' names at the start, worse each turn:

```
turn 7:  Priya: Dev: ...
turn 9:  Priya: Meera: Dev: ...
turn 11: Dev: Meera: Priya: Priya: ...
turn 13: Priya: Meera: Dev: Priya: Priya: ...
```

**Root cause**, found by tracing the exact stored history, not guessing:
`register.py`'s `strip_speaker_prefix(text, name)` only ever stripped the
*current* speaker's own name (`^Priya:`). When a reply legitimately opened
with a different character's name as a reply-quote convention the model
invented on its own (e.g. Priya's reply starting `"Meera: Dev: ..."`), that
never matched and passed straight through. Since history stores every reply
as `"{speaker.name}: {text}"`, the stored line became
`"Priya: Meera: Dev: ..."` — and the *next* turn, the model saw that exact
shape in its own context as if it were the normal format here, and imitated
it by extending the chain by one more name. Purely a feedback loop: nothing
capped it, so it grew without bound the longer a session ran. The earlier
F2F pronoun-attribution fix (`b0a2dde`) was a different, narrower case (a
model *never* naming itself); this is the opposite failure — naming
*everyone*, compounding.

**Fixed**: `strip_speaker_prefix()` (`register.py`) now takes any known
name or collection of names, not just one, and strips a whole leading chain
of them (`^(?:\s*(?:Name1|Name2|...)\s*:\s*)+`) in one pass, still per-line
(`MULTILINE`, catching a self-label restart mid-reply same as before). Call
sites updated: `engine.py` now passes every character in the scenario
(`self.scenario.characters`), not just the speaker; `human_agent.py` passes
the human persona's name plus every character's name, for the same reason
on the self-auto side. The colon requirement (`Name\s*:`) means ordinary
prose naming a character — `"Dev leaned back..."`, `"Priya, are you
kidding me?"` — is never touched; only the literal label-with-colon shape
that only ever shows up as this artifact.

**Verified**: a unit-level check against the exact chains from the live
transcript (`"Meera: Dev: you restarted..."` →
`"you restarted the redis cache..."`, `"Meera: Dev: Priya: Priya: oh..."` →
clean) alongside safe non-matching prose left untouched. Re-ran the exact
same scenario/model/turn-count (`autonomous_test`, `qwen3.6-35b-a3b`,
`--max-turns 20`) that showed the bug — zero chains anywhere across 20 full
turns, user-confirmed live. `python -m src.harness all` unchanged at
99.4/98.7, no regression.

Status: **built, verified live, not yet committed.**

---

## Autonomous mode / Self-Auto mode — built 2026-09-19

Raised: two related features, discussed together since they share almost
all their machinery. **Autonomous**: no human at all, the cast just talks to
itself. **Self-Auto**: a human is still in the scene, but their lines are
generated too instead of typed. Both run through `--autonomous`/`--auto-human`
on the terminal entrypoint, capped by `CHAT_AUTOPILOT_MAX_TURNS` (default 40)
/ `CHAT_AUTOPILOT_MAX_SECONDS` (default 900), or Ctrl+C.

Neither needed engine/prompt/history changes — `Engine.turn("")` already
generates a character turn with no user input (what `/next` and continuations
already use), so this was pure orchestration:

- `src/continuation.py` gained `decide_autonomous()`, deliberately **separate**
  from `decide()` rather than a flag on it — the interactive hand-back-to-human
  invariant and the per-turn `continuation_max` cap stay untouched for every
  existing caller. It reuses the same addressed/joinder/spontaneous ratios
  (including the F2F-specific decay) so autonomous chatter still feels
  selector-weighted, and always returns a `Continuation` (never `None`) since
  the driver's own turn/time budget is the only stop condition.
- `src/driver.py` is new — `_play`/`_run_turn`/`_continue`/etc. moved out of
  `__main__.py` (previously module-private, nothing else used them) so the
  interactive terminal loop and the new autopilot loops go through the exact
  same streaming/save/warning path, not a parallel reimplementation.
- `src/human_agent.py` is new — generates the "you" line for self-auto via a
  short, separate, uncached completion. Deliberately outside
  `Engine.turn()`'s system-prompt machinery, so CLAUDE.md rule 1 (immutable
  character system prompt) is untouched; this is a one-off call, infrequent
  and short enough that skipping the cache costs nothing.
- `src/autopilot.py` is new — `run_autonomous()`/`run_self_auto()`, thin loops
  over `driver.play()`/`continue_chain()` bounded by `Engine.turn_count`
  (new property, `len(self._checkpoints)`) against the turn/time cap.
- **Schema addition**: an optional `## You` section in scenario markdown
  (`cast.py`) — `- name: X` plus free-text persona, used only by self-auto.
  No section defined → `Scenario.human_persona` is `None` and self-auto falls
  back to a generic "ordinary participant" persona. Fully backward compatible
  — verified both old-style and new-style scenarios parse correctly, and
  `python -m src.harness all` is unchanged at 99.4/99.9 after the
  `driver.py` extraction.

**Verified live against the real model**, both modes, both `mode: text` and
`mode: f2f`: autonomous produces real in-voice chatter with no human line
anywhere and correctly ignores the "hand back on a question" rule; self-auto
produces a consistent, in-voice "you" persona and correctly still stops a
continuation chain when a reply asks "you" something directly. No web UI
changes were needed — `build_engine` already loads a saved session from disk
on startup regardless of front end, so a finished/interrupted autopilot run
just shows up normally under `--ui web` afterward (confirmed live).

One caught-and-fixed bug along the way: the self-auto generated "you" line
was never echoed to the terminal (no real stdin for the terminal to bounce
it off, unlike interactive typing) — fixed with `Terminal.show_human()`.

One accepted rough edge: `max_turns` is only checked between top-level human
turns in self-auto, so a run can overshoot slightly within the last
continuation chain (e.g. 5 replies for `--max-turns 4`) — same "soft cap"
shape as the existing interactive continuation depth cap, not a bug.

Status: **built**.

---

## Bug: F2F terminal streaming can show a raw "Name: " echo — found 2026-09-19, not yet fixed

Found while live-testing autonomous/self-auto against a `mode: f2f` scenario
(see above), not caused by that work — this is the original streaming
feature's code path (`f245451`).

The model sometimes opens its own raw output with its own name as if writing
the `Name: text` label the history storage convention uses (e.g. the model
literally generates `"Dev: Dev leaned back in his chair..."` as one string —
`register.py`'s own docstring already calls this out: "it imitates that
label when it starts a second message mid-reply"). `engine.turn()` correctly
strips this via `strip_speaker_prefix()` once generation finishes, and
everything that reads the *finished* text — `Engine.history` storage,
`transcript.entries()` (used by both `/log` and the web UI's `/api/log`), and
the web UI's live view (`index.html` explicitly replaces the streamed bubble
with the authoritative `stream_result` text once it arrives) — sees the
correct, stripped text. **`/log` and the browser are both fine**, confirmed
by reading `transcript.entries()`: it only splits on the *first* `": "` in
the stored string, which is exactly the one the storage convention added.

What's *not* corrected: the **terminal's live F2F stream**. `StreamPrinter`
(`src/ui/terminal.py`) prints each raw delta to the console as it arrives,
before `strip_speaker_prefix()` ever runs on the complete text, and
`StreamPrinter.finish()` just prints a trailing newline — it never
re-renders the corrected text over what already scrolled by. So if the raw
stream happened to start with the name-echo, that's what stays on screen,
even though the actual stored/logged/browser text is correct.

**Fix area, not yet built**: `src/ui/terminal.py`'s `StreamPrinter` needs to
either (a) overwrite what it already printed once `driver.run_turn()` has
the final `TurnResult.text` in hand — the web UI's approach, but the
terminal has no DOM node to just replace, so this means `rich`'s `Live`
display (or manual cursor-up + reprint) wrapping the whole F2F stream
instead of plain sequential `console.print(delta, end="")` calls — or (b)
buffer the first few characters before printing anything, so a leading
"Name: " can be detected and dropped before it ever reaches the screen
(cheaper, but a heuristic — an edge case where the model's own text
legitimately starts with `"Name likes to..."` followed later by an
unrelated colon could misfire). (a) is the more correct fix, matching what
`index.html` already does for the same reason.

Status: **found, documented, not fixed** — cosmetic and terminal-only,
doesn't affect what's actually saved.

---

## Checkpoint: 2026-09-17, commit `853c9a4`

All three features from this session's opening design discussion are now
built: F2F cutoff fix (`50657ee`), streaming (`f245451`), regenerate
(`70dd149`), the pronoun-attribution fix found while testing those live
(`b0a2dde`), and delete-with-rewind (`853c9a4`). Streaming and regenerate
are user-confirmed live in the browser; delete is curl/harness-verified
only so far, not yet tried live. `git reset --hard 853c9a4` is the
rollback point if anything here needs unwinding.

---

## Checkpoint: 2026-09-17, commit `b188637`

Rollback point before starting delete-with-rewind. User has now tried
streaming and regenerate live in the actual browser (that's how the pronoun
bug just below got found) — so unlike the two checkpoints below this one,
the web UI's JS for both features is confirmed working by a real person,
not just harness/curl. Everything through this commit is solid ground:
F2F cutoff fix (`50657ee`), streaming (`f245451`), regenerate (`70dd149`),
and the pronoun-attribution fix (`b0a2dde`). `git reset --hard b188637`
returns here if delete's work needs unwinding.

---

## Bug: F2F replies drifting into unattributed pronouns — fixed 2026-09-17

Reported live while trying out streaming/regenerate: a real F2F transcript
read back as a wall of "he said... she said..." with no name anywhere for
most turns — genuinely hard to follow with two same-pronoun characters in
the cast (Priya and Meera both "she").

First instinct was a UI fix — the web UI hides speaker labels in F2F mode
entirely (`body.f2f .label { display: none; }`, from `bb770b6`, the
original F2F commit — confirmed via `git show` this predates everything
from this session, not a regression from streaming/regenerate). Asked the
user whether to restore the label or leave it; **they rejected both** —
"That css hiding is so unatural" — and correctly redirected to the real
fix: the attribution belongs in the prose itself, the way actual fiction
handles multi-character scenes (`"...," Dev said.`), not a UI crutch.

Root cause was in `prompt.py`'s F2F register, which already had a rule for
this — name yourself early, "Pronouns are fine after that first mention" —
but that phrasing is ambiguous about scope, and the model was reading
"first mention" as first-ever-in-the-conversation rather than
first-in-this-turn. Only the earliest replies named themselves; everything
after assumed the name still carried over, which nothing on the page
actually enforces since each turn is a fresh, standalone block.

**Fixed** (commit `b0a2dde`): reworded the bullet to say explicitly that
*every* reply must name its speaker early, not just the first one, and
narrowed "pronouns are fine after" to the rest of that same turn. One
paragraph, no code logic touched.

Verified via `python -m src.harness all` on a fresh session (prompt changes
only take effect for new sessions — rule 1): all 35 + 9 replies across both
suites now open by naming their speaker, zero bare-pronoun openers.
99.1/100 (short), 93.8/100 (long), no regressions.

Status: **built**.

---

## Checkpoint: 2026-09-17, commit `70dd149`

Rollback point before starting delete-with-rewind, the last of the three
features from this session's design discussion. Covers regenerate
(`70dd149`), F2F streaming (`f245451`), and the F2F cutoff fix (`50657ee`) —
all harness-verified and live-`curl`-verified against the real model this
session, but **none of the web UI's JS (streaming render, regenerate
button) has been exercised by the user in an actual browser yet.** If either
needs fixes once tried live, `git reset --hard 70dd149` returns to this
exact state without touching delete's work.

---

## Checkpoint: 2026-09-17, commit `e0e0081`

Rollback point before starting the regenerate feature. Covers the F2F
cutoff fix and F2F streaming, both built and verified via harness this
session, but **streaming has not yet been tried live by the user** — only
verified by a `curl -N` smoke test and the harness (which doesn't exercise
the web UI's JS at all). If the streaming UI turns out to need changes once
actually used, `git reset --hard e0e0081` (or `git diff e0e0081` to inspect
first) returns to this exact state without touching any of the regenerate
work that follows. `f245451` is the streaming commit itself, `e0e0081` just
adds the BACKLOG note on top of it.

---

## Checkpoint: 2026-09-17, commit `50657ee`

Covers the F2F cutoff fix below plus the streaming/regenerate/delete design
discussion that follows it. Build order decided: **streaming next**, then
regenerate, then delete — streaming is self-contained (mostly `ui/web.py` +
`index.html`, doesn't touch `engine.py`'s history/state), regenerate reuses
`turn()`'s existing forced-speaker path with a small blast radius, and
delete is the most invasive (per-turn checkpointing, a `transcript.py`
change, an unresolved confirm-dialog question) — saved for last, once
regenerate's snapshot pattern already exists to build on.

---

## Bug: F2F replies cutting off mid-sentence — fixed 2026-09-17

Reported live: F2F replies would sometimes stop mid-sentence. Root cause
traced by reading the code, not guessing: `policy.py::derive` sizes
`reply_max_tokens = target_reply_seconds × decode_tok_s`, clamped to
`(48, 400)`. On the currently measured profile (`decode_tok_s ≈ 29.2`),
`target_reply_seconds_f2f=6.0` (the value picked when F2F was built, see the
entry below) works out to only **~175 tokens** — well under the 400 ceiling,
so the clamp wasn't the limiter at all. The budget itself was just too tight
for a screenplay-style turn (action beat + dialogue), and `engine.py` sent
that number straight through as a hard `max_tokens` to the streaming
completion call with **no `finish_reason` check anywhere** — a mid-generation
stop and a clean stop were indistinguishable, so the partial text got stored
and shown exactly as truncated.

**Fixed** (commit `50657ee`):
- `CHAT_TARGET_REPLY_SECONDS_F2F` default raised 6.0 → 11.0 (≈320 tokens on
  the measured profile) — the actual root-cause fix, still fully overridable
  via `.env` per rule 5.
- `engine.py::turn` now tracks `finish_reason` from the stream. When it's
  `"length"`, `register.py::trim_incomplete_sentence` cuts the reply back to
  its last complete sentence rather than leaving a mid-word fragment.
- `TurnResult` gained a `truncated: bool` field, surfaced in both UIs with
  the same visual treatment as the existing verbal-tic warning (⚠, dim red /
  `.tics` CSS class) — so a truncation stays *visible* for future retuning
  instead of silently degrading. Terminal: `ui/terminal.py`. Web:
  `ui/web.py`'s `_turn_event` + `index.html`'s `renderTurn`.

This is a safety net, not a guarantee — a sufficiently long turn can still
hit the new (higher) ceiling. The visible warning is deliberate so that's
noticeable rather than silent if it recurs.

Verified via `python -m src.harness all`: 99.1/100 (short), 94.9/100 (long),
no regressions, no truncation warnings in the transcript.

Status: **built**.

---

## Streaming support, at least for F2F — built 2026-09-17

Question raised: how complex would real token-by-token streaming be, at
least for `mode: f2f`. Finding, from reading `engine.py`: **the hard part
already exists**. `Engine.turn()` already calls the API with `stream=True`
and invokes an `on_chunk(delta)` callback per token — but both
`ui/terminal.py` and `ui/web.py` currently pass `on_chunk=lambda _: None`,
discarding every chunk. The full reply only becomes visible after the whole
`turn()` coroutine returns; the human-visible "reveal" (bubble-by-bubble
pauses) is a post-hoc presentation effect, not real streaming. So this is UI
plumbing, not an engine change.

Scoped to F2F specifically because that's the tractable half:
- **F2F** renders as one screenplay block (`register.py::f2f_block`) — a
  live-growing text block maps 1:1 onto that, no reconciliation needed.
- **Texting mode** splits one reply into up to 3 bubbles *after the fact*
  (`register.py::split_bubbles`) — streaming raw deltas and then
  retroactively re-splitting into bubble boundaries would look wrong
  (bubbles would need to un-merge mid-stream). Doing this for texting too is
  the genuinely complex half; out of scope unless asked for separately.

**Sketch, if/when built:**
- Terminal: trivial — `on_chunk` becomes `console.print(delta, end="")` for
  F2F turns; `tics`/`truncated` warnings still print after, once the full
  text is known.
- Web: moderate — `ui/web.py`'s `/api/turn` SSE generator currently
  `await`s `engine.turn()` fully before yielding anything. Streaming needs
  the turn run as a background task with `on_chunk` feeding a queue, the SSE
  generator interleaving `chunk` events off that queue with the existing
  final `turn` event (bubbles/tics/truncated are only knowable once
  generation completes), and `index.html` needs a growing text block that
  gets finalized/replaced by the structured event at the end.
- Continuations (`_run_continuations` in `ui/web.py`) call `engine.turn()`
  the same way and would need the same queue plumbing to stream too.

Built as designed (commit `f245451`): `engine.py` gained an `on_speaker`
hook (fired the instant a speaker is chosen, before generation starts, so a
label/block can render before the first token arrives); `ui/web.py`'s new
`_stream_or_await()` runs `engine.turn()` as a background task and forwards
`stream_start`/`stream_chunk` SSE events off a queue for F2F, a single
buffered event otherwise; `_run_continuations` forwards the same event
vocabulary so continuation turns stream too; `index.html` builds a growing
bubble live and lets the final `turn` event overwrite it with the
authoritative text (needed because streaming truncation-trimming can differ
from the raw concatenation). Terminal got the same treatment via a small
`StreamPrinter` class.

Verified two ways: a live `curl -N` smoke test against the real model
confirmed `stream_start` firing at +0.1s and individual word/sub-word
`stream_chunk` events arriving before the final `turn` event, whose text
matched the streamed reconstruction exactly; `python -m src.harness all`
came back 97.9/100 (short) / 96.5/100 (long), no regressions.

Status: **built**.

---

## Regenerate last message / delete-with-rewind — both built 2026-09-17

Both features run straight into the project's core non-negotiable rule:
**history is append-only, forever** (`DESIGN.md`, `CLAUDE.md` rule 2) — any
mutation before the current tail invalidates the KV-cache prefix, which is a
measured 377x cost difference (~26s cold vs. ~0.1s cached, see `DESIGN.md`).
Asked the user directly whether either feature needed to be cache-safe
(cosmetic hide only) or could pay that cost when triggered. **Decision: pay
the cost.** Both are true, history-mutating operations, accepted as an
occasional deliberate cost rather than a hot-path one.

### Regenerate

**Decision:** only the most-recent message, from the same speaker, with an
optional short (10–20 word) "guidance" nudge for the retry.

Mechanically simpler than it looks, because `Engine.turn()` already supports
re-invoking a forced speaker with an extra directive — that's exactly what
`continuation.py`-driven turns already do. Design:

- After every `turn()`, `Engine` keeps one `_last_turn` snapshot: the
  history length *before* that turn's directive was appended, plus copies of
  `selector.debt`, `last_speaker`, and `rut.RutTracker`'s per-speaker buffer.
  Invalidated (set back to `None`) the instant anything else appends to
  history — a new human turn, a continuation, an idle hop, or a state-block
  sync — so regenerate is only ever possible while that message is still
  actually the last thing that happened.
- `Engine.regenerate(guidance: str = "")`: raises if there's no live
  snapshot; otherwise truncates `history` back to the snapshot point,
  restores `debt`/`last_speaker`/rut buffer, then calls
  `self.turn("", on_chunk, force_speaker=<that speaker>, extra_directive=guidance)`.
- **Known accepted rough edge:** the background state classifier
  (`tracker.py`, fire-and-forget per `CLAUDE.md` rule 4) may have already
  finished for the discarded reply by the time regenerate fires. `State` is
  *not* snapshotted/rolled back — it's a bigger object and self-corrects on
  the very next real turn's classification anyway, so a briefly-stale
  mood/thread/trait read is an acceptable cost, not a bug to chase.
- UI: a "regenerate" affordance only on the most recent message, with an
  optional one-line guidance text box. Terminal: `/regenerate [guidance]`.

Built as designed (commit `70dd149`), with one change from the plan above:
rather than snapshotting `debt`/`last_speaker`/rut separately from history,
`Engine._LastTurn` just records the history index right before the
directive was appended (`directive_start`) plus a `history_end` — validity
becomes a plain `len(self.history) == history_end` check instead of a
separate invalidation flag, since anything that appends to history (a new
turn, a continuation, an idle hop, a state-block sync — all of which only
ever happen inside `turn()`/`_sync_state()`) changes that length naturally.
`rut.RutTracker` gained `unrecord()` to pop exactly the one entry the
discarded reply added. `__main__.py`'s `_play` and `ui/web.py`'s
`_stream_or_await` were both refactored to take a `run(on_chunk,
on_speaker)` callable instead of being hardcoded to `engine.turn()`, so
`/regenerate` (terminal) and `POST /api/regenerate` (web) reuse the exact
same streaming/saving/warning/continuation-chain treatment as a normal
turn — only the Engine call differs.

Verified live against the real model via `curl`: the 400 when nothing to
regenerate, `debt`/`history_len` returning to their pre-regenerate values
across repeated regenerates (no double-charging, no leftover entries), and
regenerate correctly re-targeting whatever a continuation chain left as the
true last speaker (tested regenerating a message that was itself several
continuations deep). `python -m src.harness all`: 99.2/100 (short), 93.9/100
(long), no regressions.

Known limitation, not yet addressed: the web UI's regenerate button isn't
restored from a resumed session on page load — only becomes available after
at least one turn happens in the current browser session.

`_LastTurn` (the single-snapshot version above) was generalized into a full
per-turn checkpoint list when delete got built right after, in the same
session — see delete's writeup below for what changed.

Status: **built**.

### Delete (true removal, message + everything generated after it)

**Decision:** true forget, not cosmetic. Deleting message N rewinds to just
before N — N and everything generated after it (including continuations) is
gone from what's sent to the model on future turns.

This is a rewind to an arbitrary point, not just the last turn, so it needs
more bookkeeping than regenerate:

- A checkpoint per turn (not just the latest one): after each `turn()`
  appends its directive+reply, store `(history_len, debt copy, last_speaker,
  rut snapshot)` in a list parallel to the turns. Cheap — small dicts, no
  cost beyond what already grows with history.
- `Engine.delete_from(turn_index)`: truncate `history` to that checkpoint's
  `history_len`, restore `debt`/`last_speaker`/rut from it, drop later
  checkpoints. Same `State`-not-rewound caveat as regenerate.
- Since it's a true mutation, the *next* request after a delete pays the
  full cold reprocess (~26s on the current profile) — expected, accepted.
- `transcript.py::entries()` currently returns role/speaker/text with **no
  index back into `history` or a turn number** — needs a turn index added to
  `Entry` so the UI can address "delete from here."
- Session autosave already runs after every turn (`save_session()`), so a
  delete just needs the same call afterward to persist the truncation.

**Open question, resolved:** confirm step before it fires — yes, on both
front ends (terminal: a y/N `Console.input()` prompt; web: the browser's
`confirm()`).

Built as designed (commit `853c9a4`), generalizing regenerate's
`_LastTurn` into `_TurnCheckpoint` — a list, one per turn that actually
produced a reply (checkpoints are skipped for empty replies, so the list
stays in exact 1:1 order with `transcript.entries()`'s assistant entries).
Each checkpoint carries `directive_start`/`history_end`, a `debt_snapshot`,
`last_speaker_before`, and now a full `rut_snapshot` (via new
`RutTracker.snapshot()`/`restore()`) rather than just the `unrecord()` pop
regenerate could get away with — delete needs to rewind to *any* point, not
just undo the most recent turn. `regenerate()` and `delete_from()` both
route through one shared `_restore_checkpoint()` helper. `transcript.py`'s
`Entry` gained `turn_index` (position among assistant replies, in
production order — `None` for user entries); `Engine.last_turn_index()`
exposes the just-produced turn's index so `ui/web.py` can hand it back to
the client on every turn/regenerate SSE event, not just via `/api/log`.

UI: a "🗑 delete from here" control appears on hover over *any* past reply
in the web UI (not just the last one, unlike regenerate) — confirms, then
re-renders the whole chat from a fresh `/api/log` rather than working out
which DOM nodes an arbitrary rewind touches. Terminal: `/delete <n>`,
reading `<n>` off `/log`'s now-visible turn numbers.

Verified live against the real model via `curl`: `turn_index` mapping
confirmed exact; deleting from a mid-conversation turn correctly kept
everything before it and dropped everything after (including a later
unrelated exchange); `debt`/rut correctly restored to their
pre-deleted-turn values, not left stale; regenerate correctly became
unavailable afterward when the new history tail was an unanswered user
message (correct per regenerate's own "still the last thing that happened"
rule, not a delete-specific bug); deleting all the way back to turn 0
correctly reset debt to all-zero and a fresh turn afterward worked
normally. `python -m src.harness all`: 99.9/100 (short), 93.3/100 (long),
no regressions.

Status: **built.**

---

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

Promoted to `PLAN_F2F.md` (2026-09-15). Resolved in conversation: mode is a
one-line `mode: f2f` flag in the scenario markdown, not a CLI/env switch —
converting a scenario to F2F changes the setting prose anyway (different
premise, not a different rendering of the same premise), so it's effectively
a second file either way. Continuations go much looser with no
name-addressing requirement (new `f2f_continuation_max`/
`f2f_continuation_chance` config, higher default depth/chance than text
mode's). Rendering is a screenplay block (name label + one prose block, no
bubble stagger) — turns out to need **no UI code changes** in either front
end, since a single-element `bubbles` list already renders as one block.

Reply length resolved too (2026-09-15): a separate `target_reply_seconds_f2f`
config field (default 6.0s vs. texting's 2.5s), reusing the same measured
`decode_tok_s` from `probe.py` rather than needing a new probe — satisfies
`CLAUDE.md` rule 5. Works out to ≈176 tokens on the currently measured
profile, inside `policy.py`'s existing clamp bounds.

Built 2026-09-15, same day as the plan — every open question got resolved in
conversation before implementation, so it went straight through. Verified
live against a throwaway `mode: f2f` scenario: screenplay-block rendering
with action beats (needed **zero UI code changes**, confirmed live not just
argued from reading the code), continuation chains up to the full
`f2f_continuation_max=5` mixing addressed/spontaneous reasons, hand-back-on-
question invariant still holding, and a full `python -m src.harness all`
regression run against a pre-existing text-mode scenario unchanged at
99.4/99.9. New `python -m src.harness f2f` suite added (skips cleanly
without a `mode: f2f` scenario). See `PLAN_F2F.md` for the full build/verify
log.

Retuned 2026-09-16 after actually looking at the output (screenshots +
transcript reading, not just harness scores):

- **Web UI was genuinely bad**, not just unstyled: every turn was a heavy
  grey rounded chat-bubble, and the human's own line was a right-aligned
  blue iMessage bubble. Fixed with a `body.f2f` CSS scope in
  `src/ui/static/index.html` (no bubble chrome, `you` renders like any other
  speaker) — texting mode's CSS untouched.
- **The continuation cascade was real**, not a one-off: the "addressed"
  branch was unconditional, and characters naming each other is completely
  normal dialogue, so nearly every human line rolled the chain out to the
  cap. Fixed with per-depth decay on both branches and retuned defaults
  (`f2f_continuation_max` 5→4, `f2f_continuation_chance` 0.6→0.35,
  `_F2F_ADDRESSED_RATIO`/`_F2F_DEPTH_DECAY` new constants in
  `continuation.py`). A 4-line script that produced 15 total turns under the
  old logic produced 5 under the new one.
- **Idle timer needed its own value**: new `CHAT_IDLE_SECONDS_F2F` (120 vs.
  texting's 45), since F2F turns already run 2-4x longer per generation.
- **The register itself was still chat-transcript-flavored**: asterisk
  action beats plus unquoted first-person dialogue read as a hybrid, not
  prose. Rewritten to actual short-story convention — quoted dialogue,
  attribution/action woven into the same sentence, action made explicitly
  optional. Verified live: output changed exactly as intended on the first
  run after the edit.

See `PLAN_F2F.md`'s "Round 2" section for the full diagnosis and numbers.

Status: **built**.

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
turn — the failure `chat-engine` shipped with). `metrics.py`'s
`opener_variety` and `question_balance` do something adjacent but only as a
post-hoc harness score, not a live guard during a real session.

Promoted to `PLAN_RUT_DETECTION.md` (2026-09-15), built same day: a small,
independent `RutTracker` (per-character ring buffers of opener/question/length
shape) feeding a nudge into the per-turn directive already sent to the model —
no sharing with `metrics.py`, no new `.env` knobs, no history changes.
Verified live against the real model on the `late_shift` scenario — a stuck
opener buffer produced a real nudge in the outgoing directive and a
differently-shaped real reply — plus a clean full-harness run (99.4/99.9)
showing no regression. A dedicated `python -m src.harness rut` suite was
added the same day (seeds the buffer, forces the speaker, mechanically
asserts the nudge reached the real directive) — kept out of `all` since it
deliberately mutates tracker state before scripting starts.

Status: **built**.

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
