# Design

Why this is built the way it is. Most of it follows from one measurement.

## The measurement everything rests on

Taken against `google/gemma-4-12b-qat` on 192.168.1.2:7890, 2026-09-14:

| | 6,651-token prompt |
|---|---|
| cold, or after the prefix changed | **~26 s** |
| identical prefix, cached | **~0.1 s** |

That is a **377x** difference. Prefill runs at ~266 tok/s, so reprocessing a
full 262k context would take about 17 minutes. Cache stability is not an
optimisation here; it is the difference between a chat app and an unusable one.

Two rules follow, and they are not negotiable:

1. **The system prompt is built once and never mutates for the life of a
   session.** Any edit to it invalidates everything and pays the full cost.
2. **History is append-only.** Nothing is ever rewritten, summarised in place,
   trimmed from the middle, or reordered. State blocks are *appended* at the
   moment they change and then left alone forever.

This is why the Strands SDK is not used despite the env being named for it. Its
conversation managers rewrite history — `SummarizingConversationManager.reduce_context()`
is documented in this repo's sibling `story-engine` as having destroyed the SWA
cache. Any library that owns your message list will eventually rewrite it. We
assemble `messages` by hand with the raw `openai` client.

Appending is not free either — at ~266 tok/s each appended token costs ~4ms — so
the injected state block is budgeted, not unbounded. See `policy.py`.

## Nothing is hardcoded to a model or a box

The numbers above are true for one model on one machine. The *architecture*
doesn't change when those change — immutable prefix plus appended tail is
optimal on a caching backend and merely neutral on one without, never worse.
Only constants and three feature flags vary.

`probe.py` measures, once per (host, model): structured-output support, prefill
rate, decode rate, cache speedup, and real concurrency. `policy.py` turns that
into runtime constants:

| measured | derives |
|---|---|
| prefill tok/s | state-block token budget |
| decode tok/s | reply `max_tokens` |
| real concurrency | whether the classifier runs in background |
| structured-output tier | `json_schema` → `json_object` → disabled |
| declared context size | full history vs sliding window |

Two deliberate limits: the context window is **declared, not probed** (probing
means deliberately overflowing someone's server), and a missing profile never
blocks startup — you get conservative defaults and a warning in the banner.

## Reply length is a latency budget, not a prompt instruction

`CHAT_TARGET_REPLY_SECONDS=2.5` against a measured 29.7 tok/s decode yields
`reply_max_tokens: 74` — about 55 words, which is two or three text bubbles.

This is the useful accident of the whole project. The texting register isn't
coaxed out of the model by asking nicely; it's enforced by a token budget that
exists for latency reasons anyway. The prompt rules in `prompt.py` reinforce it,
but the budget is what actually does the work. `faaltoo-chat` defaults to 700
tokens and reads like an essay as a direct result.

## State is three stores, not one

- **affect** — mood, energy, closeness. Changes every turn. Cheap.
- **threads + promises** — unresolved topics and commitments. Event-driven.
  Survives sessions.
- **traits** — durable facts about the human. Changes rarely, high confidence.

They are separate because they change at different rates. Folding them together
is what lets a noisy per-turn extractor overwrite a fact it should have kept —
`faaltoo-chat`'s `_extract_scene_state` does a full replace every 2 turns and
loses things for exactly this reason.

State reaches the model as **behavioural directives**, never as a data dump.
"Right now they seem anxious, energy low" shapes tone; a serialised struct would
just get narrated back at the user. When the rendered block exceeds its token
budget, the oldest details are dropped first.

Nothing is emitted until the classifier has actually run once. An unmeasured
default would assert a mood and a closeness it has no basis for.

### Closeness is a band, not a number

`distant` / `warm` / `close`, moved slowly and only on evidence. A float like
`trust: 0.62` reads precise and isn't — early testing showed the model happily
assigning "close" to a single isolated message with nothing to go on.

## The classifier runs after the reply, never before

It is scheduled *after* generation and awaited by nobody. `faaltoo-chat` awaits
its extractors inline between the reply and the next prompt, which is why it
stalls every second turn.

It also **queues rather than drops**. The first version skipped the update if a
previous one was still in flight; in a fast conversation that meant updates were
skipped indefinitely and promises were silently never captured. Now a turn
arriving mid-flight sets a pending flag and the classifier immediately runs
again against the newer tail.

It fires as a task regardless of how many slots the server has. An earlier
version awaited it inline when the probe found only one slot, on the theory that
blocking honestly beats pretending — that was wrong, and measurably so: inline
cost **6.52s per turn against 3.04s**, because it stalls the *input prompt*.
With one slot the request just queues server-side instead, and the user's typing
pause absorbs most of it. Their keystrokes are the real parallelism in a
single-user chat.

`effective_slots` is still measured and recorded in the profile, but it no longer
gates anything.

Failures set `state_error` and surface in the UI. They are not swallowed — all
of `faaltoo-chat`'s background calls `except Exception: return` and degrade
invisibly.

## Promises

The classifier reports commitments with a `by` field naming the character who
made them, plus a coarse `when` (`later_today`/`tomorrow`/`this_week`/`someday`)
mapped to a timestamp. Asking a 12B model for real dates is unreliable; asking it
to pick from four buckets is not.

On session start, anything due is raised proactively by the character who owes
it, as a normal turn with an extra directive. This is the mechanism that makes
the thing feel like it has continuity rather than memory.

Both threads and promises are de-duplicated by keyword overlap (Jaccard ≥ 0.5),
not exact text. The classifier rephrases the same commitment every turn — "check
in on the human on Thursday" and "Priya will check in before the call on
Thursday" are the same promise and exact matching kept both.

## Vision: hydrate at send time, never store the bytes

`Engine.history` never holds raw image bytes — only a lightweight
`{"type": "image_ref", "path": ...}`, written once (`vision.save_attachment`)
to a file beside the session, never inside this repo. Every place history
feeds a real model call — the main reply in `Engine.turn()` *and* the
classifier's tail in `_classifier_tail()` — rebuilds a fresh outbound copy via
`vision.hydrate()`, which reads that file and swaps in a real
`image_url` data-URI. The stored reference itself is never rewritten; hydration
only touches the transient copy built for that one request.

Two things this buys:

- `session.json` stays small regardless of how many images accumulate —
  the base64 never gets serialized to disk, only regenerated on demand.
- It composes for free with append-only history: appending a reference is
  just another entry, so rule 2 (never rewrite anything already in
  `Engine.history`) holds without a special case for images.

The image is downscaled once, at ingestion, to a bounded longest edge
(`CHAT_VISION_MAX_DIMENSION`) — the same idea as `reply_max_tokens`, a
latency/context budget rather than a quality choice. Downscaling per-hydration
instead would mean re-deriving a *different* encoded string on every read,
which would quietly break the request-prefix stability the whole cache story
depends on.

No second, vision-only model. `probe.py` measures once whether the
*configured* model accepts image input at all (same shape as its other
capability checks) and `Policy.vision_capable` degrades the feature off
entirely rather than falling back to a second endpoint — a model swap
mid-session would evict the character model's cache exactly as costly as the
prefix change in the opening measurement. Character voice held up under this
in testing: two characters shown the same image gave two different, in-voice
reads of it in the same conversation, rather than one flattened description
repeated back.

## Turn selection

Five lines of logic in `selector.py`: a character named in the message speaks;
otherwise the one with the lowest weighted speaking debt, excluding whoever just
spoke. Debt increases by `1/weight` each time someone talks, so a 0.55-weight
character accrues debt fast and is picked less often, while still being
available when addressed.

This is a deliberately rule-based, non-LLM decision. It is instant, free, and
debuggable with `/who`.

## What is deliberately not built

- **Per-character system prompts.** Measurement showed three distinct prefixes
  *do* coexist in cache, so it's viable — but a character who hasn't spoken in
  ten turns would reprocess those ten turns on their next line. One shared
  prompt voicing everyone keeps a single always-hot cache.
- **Rut detection.** Needed, not built. Sibling project `chat-engine` shows the
  failure clearly: one character asked a rhetorical question in nearly every
  turn across a long transcript and nothing noticed. Planned as per-character
  ring buffers of reply shape — opening n-gram, ends-in-question, length band.
- **An eval harness.** The cheap metrics (length, assistant-voice blocklist) are
  live in `register.py`. A scripted user-side harness is not built. When it is,
  the simulated human must get a **neutral** system prompt — `faaltoo-chat`
  primes its auto-user with the bot's own persona, so both sides sound alike and
  the results are contaminated.
- **Voice.**
