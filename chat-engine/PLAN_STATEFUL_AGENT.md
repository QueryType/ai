# Plan — Stateful Agent for KV Cache Reuse

## Problem

Every turn, `GMAgent._call()` creates a brand-new `Agent` instance:

```python
agent = Agent(system_prompt=self._system_prompt, model=self._model, tools=[], ...)
response = agent(prompt)
```

This means each call is a single two-message exchange:
```
[system_prompt]  →  [user: full turn_prompt (history + speaker + card)]  →  [assistant: reply]
```

The local inference server (llama.cpp, LM Studio, etc.) has no message history to cache.
It must re-prefill the entire system prompt + embedded history on every turn.

At turn 15 that's ~1100 tokens of prefill per call — most of it repeated from the previous turn.
At turn 30 (after history_window kicks in) it's roughly the same per-call cost indefinitely,
but also triggering a second summarizer call on every turn.


## Goal

Turn N should cost only the tokens in the new user message (~50–100 tokens for a directive),
not the full history re-prefill. The system prompt should be prefilled exactly once.


## How local KV cache works (llama.cpp / LM Studio)

llama.cpp caches the KV state for any prompt prefix it has seen before.
If call N sends: `[system] [T1_user] [T1_asst] [T2_user] [T2_asst] [T3_user]`
and call N+1 sends: `[system] [T1_user] [T1_asst] [T2_user] [T2_asst] [T3_user] [T3_asst] [T4_user]`
— the server recognises the shared prefix and only processes `[T3_asst] [T4_user]` fresh.

This only works if:
1. The Agent sends a growing conversation (messages list), not a single flat prompt.
2. The prefix tokens are byte-for-byte identical to a previous call in the same server slot.
   (Reassigning the same slot each call helps; most local servers do this automatically
   when you reuse a persistent client connection.)

Currently the history is **embedded as text inside the user message** rather than as
separate message objects. This breaks prefix reuse because each user message is different.


## Proposed Architecture Change

### Core idea

Keep one `Agent` instance alive for the full session instead of creating one per turn.
Stop embedding history in the turn prompt — the Agent's `messages` list IS the history.
Each turn only sends the directive: who speaks, their card, phase context, director note.

### Message shape per turn

```
System  : [system_prompt — unchanged from today]

Turn 1 call:
  messages: []
  user    : "NEXT SPEAKER: Lyra\n[card]\n..."
  asst    : "Lyra: \"dialogue\""

Turn 2 call:
  messages: [T1_user, T1_asst]
  user    : "NEXT SPEAKER: Aldric\n[card]\n..."
  asst    : "Aldric: \"dialogue\""

Turn 21 call (window=20, first trim):
  Before trim: 40 messages (20 user/assistant pairs)
  Action     : drop oldest pair → 38 messages remain
  Prepend summary to new user message:
    "[EARLIER CONTEXT:\n<summary>\n\n]NEXT SPEAKER: ..."
```

The model always has its full recent conversation as structured message objects —
the same information it has today, just delivered correctly for caching.

### What changes

#### `GMAgent` (gm_agent.py)

- Add `self._agent: Agent | None = None` — persistent across turns.
- `_call()` no longer creates a new Agent. It initialises `self._agent` once, then
  calls `self._agent(prompt)` on every subsequent turn.
- `build_turn_prompt()` and `build_selected_turn_prompt()` drop the
  `history` parameter — callers no longer pass history into these builders.
- Add `_trim_if_needed(history_window)` — called inside `_call()` before each invoke:
  trims `self._agent.messages` to the last `history_window * 2` items
  (each turn = one user message + one assistant message).
- Summary injection: `_call()` accepts an optional `summary_prefix: str`.
  When set, it prepends `[EARLIER CONTEXT:\n<summary>]\n\n` to the user message
  before invoking the agent, so the model sees the summary without it being
  part of the permanent messages list.

#### `main_chat.py` / `ChatSession`

- `_build_history_context()` is no longer called for GM turns — remove it from
  `_gm_turn()`.
- Still call `_refresh_history_summary()` for the `HistorySummarizer` (which reads
  from `logger.turns`, not the agent). Pass the resulting `self.history_summary`
  to `gm.generate()` / `gm.generate_selected_turn()` so it can inject as summary_prefix.

#### `HistorySummarizer` (history_summarizer.py)

- No changes. Still operates on `logger.turns` independently.
- The summary it produces is passed through to the GM as a summary_prefix, not
  embedded in the messages list (so it doesn't get KV-cached — it changes each time
  old turns are summarised).

### What stays the same

- `ChatLogger` — unchanged. Source of truth for the transcript and run log.
- `parser.py`, `orchestrator.py`, `planner.py` — unchanged.
- The `history_window` and `history_summary_chars` config fields — same semantics.
- `HistorySummarizer` — same logic, same extra call per turn when window overflows.
- `llm` / `rules` mode distinction — still works the same way; only the history
  delivery mechanism changes.


## Trim and summary injection detail

```
history_window = 20

len(agent.messages) before trim:
  turn 1–20:  0–38  →  no trim needed
  turn 21:    40    →  drop oldest pair → 38
  turn 22:    40    →  drop oldest pair → 38
  (steady state: always 38 messages = 19 live pairs + new call)

Summary injection (when summary is non-empty):
  user_message = f"[EARLIER CONTEXT:\n{summary}\n\n]{directive}"
  This is sent as the user message for this turn.
  The agent records it in messages as-is.
  On the next turn it is part of the cached prefix — the summary won't change
  unless another trim happens, so the prefix stays valid.

  Alternative (slightly cleaner): inject as a system message prepended to
  agent.messages before the call, then remove it after. This keeps the
  summary out of the permanent message list.
  Downside: modifying messages around the call is brittle.
  Recommendation: keep it in the user message prefix — simpler.
```


## KV cache savings (estimate)

Session: 40 turns, history_window 20, system_prompt ~600 tokens, avg turn ~60 tokens.

| Approach | Tokens prefilled per turn | Total prefill (40 turns) |
|---|---|---|
| Current (stateless, text history) | ~1100 (system + 20 turns) | ~44,000 |
| Stateful (this plan) | ~60 (directive only) | ~2,400 + one-time system prefill of 600 |

Rough speedup on local inference: **~15–18× less prefill work per turn** after turn 1.
Actual wall-clock speedup depends on server (llama.cpp with slot reuse is best case).


## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Strands `agent.messages` is internal API — may change | Wrap access in `GMAgent._trim_if_needed()`; one place to fix if SDK changes |
| Local server doesn't reuse slots between calls | Use a persistent connection (same model client across calls — already done via `self._model`) |
| Summary injection in user message slightly changes cached prefix each summarisation | Acceptable — trim happens at most once per turn; the rest of the prefix (previous turns) stays intact |
| `llm` mode — agent now picks speaker from context, not from explicit history block | The messages list gives it the full history; it works the same or better |
| `max_retries` retry path | On retry, don't append to `agent.messages` — call the agent again with the same directive. If agent recorded the bad response in messages, pop it before retry. |


## Implementation order

1. Add `_trim_if_needed()` to `GMAgent` and wire the persistent agent. Keep
   `build_turn_prompt()` / `build_selected_turn_prompt()` accepting `history`
   as an optional param with default `""` — so callers can migrate one at a time
   without breaking.

2. Update `_gm_turn()` in `ChatSession` to stop passing history to the GM prompt
   builders; pass `summary` instead.

3. Handle the retry case: on a retry, pop the last assistant message from
   `agent.messages` if the GM recorded a bad response before the parse failed.
   (Check whether Strands auto-appends the response to messages — it likely does.)

4. Run a full session against the local endpoint and compare run log token counts
   to the current baseline. Token counts should drop sharply after turn 1.


## Config / opt-out

Add `CHAT_ENGINE_STATEFUL_AGENT=true` (default) to `.env.example`.
When set to `false`, fall back to the current stateless one-Agent-per-call path.
This lets us A/B on remote providers or revert if a server has issues with long sessions.
