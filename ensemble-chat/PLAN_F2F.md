# Plan — Face-to-face (F2F) conversation mode

Status: **built** (2026-09-15). Read `CLAUDE.md` and `DESIGN.md` first —
the rules there still bind, especially append-only history and never
mutating the system prompt mid-session. Read `PLAN_CONTINUATIONS.md` too;
this mode reuses its decision logic rather than replacing it.

**Built exactly as designed below**, no deviations from the sections that
follow. Wiring: `src/cast.py` (`Scenario.mode`, parsed as a one-line flag),
`src/prompt.py` (`_REGISTER_F2F`), `src/register.py` (`f2f_block`),
`src/engine.py` (bubble choice by mode), `src/continuation.py`
(`_decide_f2f`), `src/config.py` (`f2f_continuation_max`,
`f2f_continuation_chance`, `target_reply_seconds_f2f`), `src/policy.py`
(`derive`/`load_policy` take `mode`), `src/bootstrap.py` and `src/harness.py`
(load scenario before policy so `scenario.mode` is known in time),
`src/metrics.py` (`evaluate(..., mode)` drops `brevity`/`no_narration` for
f2f).

**Verified:**
- Regression: full `python -m src.harness all` against `late_shift` (a
  pre-existing, `mode`-less scenario) unchanged at 99.4/99.9 — confirms the
  branch-on-mode changes are inert for every scenario written before this
  feature existed.
- Parsing: `mode: f2f` line correctly consumed out of the setting text;
  `late_shift` with no such line correctly resolves to `mode="text"`.
- Live, real model, a throwaway `kitchen_table` (`mode: f2f`) scenario: one
  screenplay block per turn with inline action beats, `reply_max_tokens=175`
  (matches the `target_reply_seconds_f2f=6.0` × measured `decode_tok_s`
  calculation), continuation depth reaching the full
  `f2f_continuation_max=5` on one human line and 8 total continuations across
  4 lines mixing `addressed` and `spontaneous` reasons — confirming
  addressing is no longer the primary trigger — and the hand-back-on-`?`
  invariant still holding (verified separately: replies ending in `?` capped
  continuation at depth 0 in both modes).
- New `python -m src.harness f2f` suite: skips with a clear message against
  a non-f2f scenario (tested against `late_shift`); against `kitchen_table`
  scored 95.0/100 with `brevity`/`no_narration` correctly absent from the
  table, mean turn ~13s (vs. texting's ~3s), 15 turns generated from 4
  scripted human lines.

**Left as noted in the plan, not further pursued this session:**
`ui/terminal.py`/`ui/web.py` needed no changes at all, confirmed by the live
run rather than just the code-reading argument in section 3 below.

**Round 2, 2026-09-16 — retuned after actually looking at it:**

1. Web UI screenshot review found the rendering genuinely bad: every turn
   showed as one heavy grey rounded chat-bubble, and the human's own line was
   a right-aligned blue iMessage-style bubble — neither reads as a screenplay.
   Fixed in `src/ui/static/index.html`/`src/ui/web.py`: a `body.f2f` CSS scope
   strips the bubble chrome (no background, no border-radius, no padding,
   wider column), the human's turn renders as a plain labelled `you` line
   like anyone else's, and `*asides*` italicize instead of showing raw
   asterisks. All scoped behind `body.f2f`; texting mode's CSS is untouched.
   `/api/cast` now reports `mode` so the client can toggle the class.
2. Live use surfaced two tuning problems the plan explicitly flagged as
   "feel it out against a real transcript, not settle on paper":
   - **The idle timer was a single global value** (`CHAT_IDLE_SECONDS=45`,
     shared with texting mode). F2F's turns already run ~10-19s each, so 45s
     of literal silence felt rushed against that pace. Fixed: new
     `CHAT_IDLE_SECONDS_F2F` (default 120), wired the same way as the other
     F2F-specific config, threaded through `src/__main__.py` and
     `src/ui/web.py`'s `/api/cast`.
   - **Nearly every human line cascaded through the whole cast.** Root cause,
     found by reading `_decide_f2f`, not guessed: the "addressed" branch was
     an *unconditional* continuation — any reply that happened to name
     another character (extremely common in ordinary dialogue: "Dev, you
     should...") guaranteed another hop, with no decay, so chains just rolled
     until they hit the hard `f2f_continuation_max` cap almost every time.
     Fixed in `src/continuation.py`: both the addressed and spontaneous
     branches are now a probability that decays per depth
     (`_F2F_DEPTH_DECAY=0.5`), addressed boosted over spontaneous but no
     longer guaranteed (`_F2F_ADDRESSED_RATIO=2.5`), and the defaults
     retuned (`f2f_continuation_chance` 0.6→0.35, `f2f_continuation_max`
     5→4). Verified with a 5,000-trial synthetic distribution (44% zero
     continuations, 40% one, ~14% two-plus, cap hit ~0.1% of the time,
     versus the old logic which reliably hit the cap almost every turn) and
     confirmed live: the same 4-line script that generated 15 total turns
     under the old logic generated 5 under the new one.
3. Live feedback on the register itself, reading real output: the original
   asterisk/screenplay convention (section 2, superseded below) produced a
   hybrid that still read like a chat transcript with narration stapled on —
   a third-person action paragraph, then a separate paragraph of unquoted
   first-person dialogue. Rewritten to actual short-story prose: quoted
   dialogue, attribution and action woven into the same sentence, action
   made explicitly optional rather than a per-turn habit. See section 2 for
   the current text and the reasoning; verified live, output changed exactly
   as intended on the first run.
4. Web UI, round 3: the per-turn name label is now redundant once the prose
   self-attributes ("Priya said...") — dropped entirely for `mode: f2f`
   (`body.f2f .label { display: none }`), replaced by a thin colored
   left-accent bar per speaker (set inline in JS from the same `colorOf` map
   the label used) so a quick visual scan still works without repeating the
   name in text. The input placeholder also switches to "Say something…" —
   "Message the group…" doesn't fit an in-person scene.
5. **"The human" leak**: prose narration needs *some* noun to refer to the
   user when they're not speaking, and since the user has no character block
   in the scenario, the model invented "the human" / third-person labels —
   immersion-breaking, and not scenario-specific, since no F2F scenario gives
   the human a name. Fixed with an explicit register rule: refer to the user
   as "you" in narration, never a label. Verified live across three turns
   that previously would have triggered it — no leak.
6. **Speaker ambiguity after the name label was dropped** (round 4's own
   change, from item 4): removing the label meant a turn opening on a bare
   pronoun ("She said...") had nothing on the page to point to — a real
   ambiguity, not just cosmetic, since the label used to carry that
   information. Fixed with an explicit register rule: name yourself in the
   first sentence (as the action's subject or the first dialogue tag),
   pronouns fine after that. Verified live across 4 consecutive turns, each
   opening with the speaker's actual name.

## The problem

The app currently produces exactly one register: short texting bubbles, no
narration, enforced by `prompt.py`'s `_REGISTER` and `register.py`'s bubble
splitting. That's right for a scenario like `late_shift` (people apart,
texting late at night) but wrong for an in-person scene — two people at a
table, a scene in a room — where the actual texture of real dialogue is
longer turns, actions and tone (`*picks up mug, doesn't look up*`), and people
almost never say each other's names mid-conversation the way texters do.

## Decisions made in conversation (2026-09-15)

- **Same schema, different files.** `Scenario`'s shape (`title`, `setting`,
  `### Name` character blocks) does not change — a character's personality is
  mode-agnostic. What changes is the *content* of the setting prose: "everyone
  texting from separate apartments" and "sitting in the same room" are
  different facts about the scene, not different renderings of the same fact.
  So converting a texting scenario to F2F is, in practice, writing a second
  file with a different setting — not a schema fork. One new one-line flag in
  the file (`mode: f2f`, same style as a character's existing `weight:` line)
  declares which register applies; a scenario file with no such line defaults
  to today's texting behavior, so every existing scenario keeps working
  unmodified.
- **Continuations: much looser, no name-addressing requirement.** Real
  in-person talk overlaps and interrupts constantly, and people rarely say
  each other's names mid-conversation the way `_addressed()` currently
  detects. F2F needs continuation to fire on its own, not mostly gated behind
  someone being named.
- **Rendering: screenplay block.** One turn, one prose block, name label,
  action beats and tone cues allowed inline. No typing-pause bubble reveal —
  it should read like a script, not a text thread.

## Design

### 1. Scenario: `mode` field

`src/cast.py`:

```python
@dataclass(frozen=True)
class Scenario:
    title: str
    setting: str
    characters: tuple[Character, ...]
    mode: str = "text"   # "text" | "f2f"
```

Parsing: the first non-blank line immediately after the title, if it matches
the existing `_META` pattern with key `mode`, sets it and is *not* included in
`setting`; anything else falls through to `setting` exactly as today. This
mirrors how a character's `weight:` line is already parsed out of its body
rather than left in the description — same pattern, applied once at the
scenario level instead of once per character.

```markdown
# Kitchen Table
mode: f2f

Priya, Dev and Meera end up in the kitchen after everyone else has gone to bed.
```

No change to `load_scenario`'s character-parsing loop at all.

### 2. Prompt register: `prompt.py`

Add `_REGISTER_F2F` alongside the existing `_REGISTER` (renamed in-place to
`_REGISTER_TEXT` for clarity), and pick one in `build_system_prompt` based on
`scenario.mode`:

**Retuned 2026-09-16, after reading real output.** The first version below
(asterisk action beats, screenplay-style) shipped and got read live — it
produced a mixed convention: third-person stage direction as its own leading
paragraph, then a separate paragraph of unquoted first-person dialogue. That
still read as a chat transcript with narration stapled on, not prose. Live
feedback asked for actual short-story prose instead: quoted dialogue with the
action and attribution woven into the same sentence
(`"Worst food," Priya says, pushing her plate away.`), and action treated as
optional rather than something every turn needs. Current text:

```python
_REGISTER_F2F = """\
How everyone writes:
- Write like a short story, not a chat transcript or a screenplay. Weave
  action, tone, and spoken dialogue into the same flowing prose — never an
  action description as its own paragraph followed by a separate paragraph
  of dialogue. That split-paragraph shape is exactly what this isn't.
- Spoken words go in double quotes, with any attribution or action woven into
  the same sentence, the way fiction does it:
  "Worst food I've had all year," Priya says, pushing her plate away.
  Dev doesn't look up. "You say that every time."
- Action and physical detail are optional, not required every turn. Plain
  dialogue alone, with no action at all, is often the right call — don't pad
  a short line with a gesture just to have one.
- Turns can run longer than a text message, but stay in the moment: no
  narrating the whole scene, no summarising what already happened.
- Disagree, tease, change the subject, let things go unanswered.
- Rarely say each other's names inside the spoken dialogue itself — real
  conversation doesn't, even though the narration around it can name anyone
  freely.
- Never offer help, never summarise, never ask if there is anything else.
- Speak only as yourself. Never write anyone else's spoken lines."""
```

The original asterisk-based text is gone, not kept as a second option —
there was no reason found to keep both once the prose version was verified
better. `src/ui/static/index.html`'s `setBubbleText()` still knows how to
italicize a stray `*aside*` if the model ever emits one out of habit; that's
now a harmless fallback rather than the primary convention.

`build_system_prompt`:

```python
def build_system_prompt(scenario: Scenario) -> str:
    parts = [f"This is a group chat: {scenario.title}."] if scenario.mode == "text" \
        else [f"This is a scene: {scenario.title}."]
    ...
    parts.append(_REGISTER_F2F if scenario.mode == "f2f" else _REGISTER_TEXT)
    return "\n\n".join(parts)
```

Still built once in `__post_init__`, still never mutated — rule 1 is
untouched, this only changes *what* gets built, not *when*.

### 3. Bubble splitting: `register.py` / `engine.py`

`split_bubbles()` stays as-is for text mode. For F2F, a turn is one block by
construction — add a trivial `f2f_block(text) -> list[str]` that returns
`[text]` unless empty (mirrors `split_bubbles`'s empty-string handling), and
have `Engine.turn` pick which to call based on `self.scenario.mode`:

```python
bubbles = f2f_block(text) if self.scenario.mode == "f2f" else split_bubbles(text)
```

This is the one place the render decision actually lives. Both
`ui/terminal.py`'s `show()` and the web UI already iterate `result.bubbles`
generically — a one-element list naturally renders as a single block with no
stagger-reveal pause, since the multi-bubble pause logic only triggers when
`i` (the loop index) is nonzero. **No rendering code changes needed in either
front end** — the mode only changes what `Engine` puts in `bubbles`.

`strip_speaker_prefix` and `find_tics` apply unchanged in both modes — a
model imitating a `Name:` label or slipping into assistant-voice is a bug in
either register.

### 4. Continuations: `continuation.py`

`decide()` gains a `mode` parameter (or reads `scenario.mode` directly, since
`scenario` is already a parameter). New behavior for `mode == "f2f"`:

- **Rule 1 (hand back to human) is unchanged** — a line ending in `?` with no
  one else addressed still stops the chain in both modes. F2F doesn't relax
  the one invariant that keeps the human a participant rather than a
  spectator; that's the exact failure `PLAN_CONTINUATIONS.md` already warns
  against, and it applies at least as much to a mode designed to feel more
  continuous.
- **Addressed-by-name still wins if it happens** — cheap, still correct
  signal when present, just no longer the *main* driver.
- **New: spontaneous is the default continuation**, not a low-probability
  fallback gated behind "nobody was addressed." For F2F, roll a much higher
  chance on *every* turn regardless of addressing, using a separate ratio so
  the single `CHAT_CONTINUATION_CHANCE` knob doesn't have to serve two very
  different textures:

  ```python
  # New Config fields, same pattern as continuation_max/continuation_chance.
  # Defaults as originally shipped; retuned in Round 2 above to 4 / 0.35 plus
  # a per-depth decay, once live use showed these numbers cascaded through
  # the whole cast almost every turn.
  f2f_continuation_max: int        # CHAT_F2F_CONTINUATION_MAX, default 5
  f2f_continuation_chance: float   # CHAT_F2F_CONTINUATION_CHANCE, default 0.6
  ```

  `decide()` picks `cfg.f2f_continuation_max` / `cfg.f2f_continuation_chance`
  over the text-mode fields when `scenario.mode == "f2f"`, and for F2F treats
  the "joinder" and "spontaneous" branches as one merged roll — a person
  picking the conversation back up doesn't meaningfully distinguish "the same
  person adds one more thought" from "someone else jumps in," the way the
  texting mode's two separate branches do. Whether that merge is exactly
  right is something to feel out against a real transcript, not settle on
  paper — flag it for review after the first real run (see Verify).

- Depth caps at `f2f_continuation_max` (proposed default 5 vs. text mode's 2)
  — a real conversation runs longer stretches without the human typing than a
  text thread does before it'd feel like people are ignoring them.

This is still pure decision logic, still no I/O, still lives in
`continuation.py` — no changes to how `src/__main__.py` or `ui/web.py` call
it beyond passing the scenario through (they already do).

### 5. Reply length: `policy.py` — decided 2026-09-15

`policy.py::derive` sizes `reply_max_tokens` off `cfg.target_reply_seconds *
p.decode_tok_s` — one global budget tuned for a texting decode-rate target.
F2F turns are allowed to run longer per the register text above, which the
current single budget doesn't leave room for.

**Decision: a separate time budget, same measured decode rate.** New config
field `target_reply_seconds_f2f` (env `CHAT_TARGET_REPLY_SECONDS_F2F`,
default `6.0`, vs. texting's `2.5`). `derive()` takes a `mode` parameter and
picks `cfg.target_reply_seconds_f2f` over `cfg.target_reply_seconds` when
`mode == "f2f"`; `load_policy` threads `scenario.mode` through. This still
satisfies rule 5 — nothing new is hardcoded, and the *measured* `decode_tok_s`
from `probe.py` is reused as-is, only the time allowance changes.

On the currently measured profile (`decode_tok_s ≈ 29.27`), 6.0s works out to
≈176 tokens — inside `_clamp`'s existing `(48, 400)` bounds, so no change
needed there. That's roughly a short paragraph plus one action beat: long
enough to read as real dialogue, short enough to stay in the register text's
own limit ("no narrating the whole scene"). Treat 6.0 as a starting point to
retune after reading real F2F output, same as `target_reply_seconds` already
is for texting.

## Wiring

- `src/cast.py` — `Scenario.mode`, parsed as described above.
- `src/prompt.py` — `_REGISTER_TEXT` (renamed from `_REGISTER`),
  `_REGISTER_F2F` (new), `build_system_prompt` branches on `scenario.mode`.
- `src/register.py` — new `f2f_block()`, `split_bubbles()` untouched.
- `src/engine.py` — one branch in `turn()` choosing which bubble function to
  call. No other change; `history`, prompt caching, and the classifier tail
  are all mode-agnostic already.
- `src/continuation.py` — `decide()` branches on `scenario.mode` for the
  continuation-chance/depth logic described above.
- `src/config.py` — `f2f_continuation_max`, `f2f_continuation_chance`,
  `target_reply_seconds_f2f`.
- `src/policy.py` — `derive(cfg, profile, mode="text")`, `load_policy(cfg,
  mode="text")`, both defaulting to today's behavior for any caller that
  doesn't pass `mode` yet.
- `ui/terminal.py`, `ui/web.py` — **no changes expected**, per the bubble-list
  reasoning in section 3. Verify this holds once real F2F output exists
  rather than assuming it from reading the code.

## Harness

`src/harness.py`'s `no_narration` metric would actively penalize F2F output,
since action beats in asterisks are exactly what it flags as a defect in
texting mode. An F2F suite needs either:

- a separate `evaluate()` call that omits `no_narration` and `brevity` (both
  texting-specific expectations), or
- a `mode` passed into `metrics.evaluate` that swaps which metrics apply.

Given `RutTracker`'s precedent of staying independent rather than
retrofitting shared code, the lighter option — a separate small metric set
for F2F rather than threading `mode` through every existing metric function —
is probably right, but this is a "decide once real F2F transcripts exist"
call, not one to lock in before any F2F scenario has actually been run.

A dedicated `f2f` suite (own script, own scenario fixture with `mode: f2f`)
should stay out of `all` the same way `vision` and `rut` are — different
register, not comparable to the texting composite score.

## Verify

1. A scenario with `mode: f2f` produces one prose block per turn in the
   terminal, no stagger-reveal, quoted dialogue with action woven in rather
   than a separate action paragraph.
2. A scenario with no `mode:` line (every existing scenario) behaves exactly
   as before — this is the regression check that matters most, since it's a
   shared code path (`prompt.py`, `engine.py`, `continuation.py`) now
   branching on something that used to be unconditional.
3. In a live F2F session, characters pick up from each other repeatedly
   without the human retyping, and it reads like people in a room — not
   texting with paragraphs.
4. The human still gets the floor back promptly when a line ends in `?` and
   addresses them — same check `PLAN_CONTINUATIONS.md` already verifies for
   text mode, re-run against F2F's looser defaults to confirm the one hard
   invariant survives the looser tuning.
5. Latency stays reasonable per turn even at the depth cap (retuned to 4,
   see Round 2 above) — several consecutive full generations back-to-back is
   a real wait; read the actual burst time before locking in a default. In
   practice the decay makes hitting the cap rare, not the common case.

## Do not

- Do not relax the hand-back-on-question rule for F2F. Bias toward the human
  staying a participant is the one rule that must survive every mode.
- Do not fork `Engine.history` handling, prompt caching, or the classifier
  tail by mode — everything except register text, bubble shaping, and
  continuation tuning stays exactly as it is today.
- Do not silently change existing scenarios' behavior — `mode` must default
  to today's texting behavior when absent, with zero output difference for
  every scenario that predates this feature.
