# Design Decisions

Running log of architectural choices, what was considered, and why.

---

## 2026-05-20 — Keep stateless GM agent; no KV cache optimisation via stateful agent

### Decision

Retain the current architecture: a fresh Strands `Agent` is created per GM turn.
Do NOT implement the stateful-agent approach described in `PLAN_STATEFUL_AGENT.md`.

### Context

Each GM turn currently creates a new `Agent(system_prompt, model)` and makes a single
two-message call: `[system_prompt] → [user: history + directive] → [assistant: reply]`.
This means the local inference server re-prefills the system prompt and full history
on every turn (~1000–1200 tokens per turn at turn 15).

A stateful approach — keeping one Agent alive, letting its `messages` list carry history,
sending only the per-turn directive as the new user message — would let the local server
reuse its KV cache across turns. Estimated saving: ~15–18× less prefill per turn after
turn 1 in ideal conditions.

### Why we chose NOT to do it

**The cache benefit is mostly undermined by trim + summary churn.**
history_window is typically 12–20. Once the session exceeds the window, the oldest
message pair is trimmed every turn. Each trim shifts the token sequence, invalidating
the server's cached prefix from that point. At the same time the rolling summary
(injected as a prefix on the new user message) updates every turn after the window
fills. Both events happen at the same rate: one per turn, indefinitely. The net result
is that the cache stays warm for the recent unmodified turns but the prefix break point
moves every turn anyway.

**Strands `agent.messages` is an internal, not a public contract.**
Trimming it directly (`agent.messages = agent.messages[-n:]`) couples the code to
SDK internals. A Strands release could rename, restructure, or validate the field in
a way that breaks trimming silently or with a hard error.

**Human injections require a second place to track turns.**
`[as Lyra]` lines are currently logged in `ChatLogger` and flow into the next turn
prompt via `get_history()`. With a stateful agent they would also have to be pushed
into `agent.messages` as a user/assistant pair — two sources of truth with a sync
requirement.

**Retry handling becomes fragile.**
On a malformed GM response, the current code calls again with a fresh agent. With a
stateful agent, Strands likely appends the bad assistant response to `messages` before
the caller can parse it. A retry would require popping that bad entry first — coupling
to the SDK's internal append behaviour.

**KV cache reuse is server-dependent and not guaranteed.**
llama.cpp caches by slot. If the server assigns a different slot between calls (e.g.
under load, or with multi-slot configuration), the prefix match fails and every call
is a full re-prefill anyway. LM Studio and Ollama have their own behaviours. The plan
assumes a cooperative server; the gain is not portable.

**The simpler fix covers most of the practical cost.**
The real waste is token count per call, not cache misses specifically. Controlling
`CHAT_ENGINE_MAX_TOKENS` (done) bounds generation cost. Controlling
`CHAT_ENGINE_HISTORY_WINDOW` via env var (done) lets you dial down prefill cost for
local runs without any architectural change. For a local 8K-context model with
history_window=12 and max_tokens=200, per-turn prefill is roughly 700–800 tokens —
manageable and predictable.

### What was implemented instead (the middle path)

- `CHAT_ENGINE_MAX_TOKENS` (default 200) — hard generation cap at API level.
- `CHAT_ENGINE_TEMPERATURE` (default 0.85) — sampling control.
- `CHAT_ENGINE_HISTORY_WINDOW` — env var override for history_window without editing
  the scenario `.md` file. Recommended value for local: 10–12.
- `CHAT_ENGINE_CONTEXT_LIMIT` — startup warning if estimated prompt size exceeds the
  threshold. Helps catch oversized configs before the first API call.
- Local and remote profiles documented in `.env.example`.

### When to revisit

If sessions routinely run 60+ turns on a local model with a stable, long-context server
(e.g. llama.cpp with `--ctx-size 32768` and single-slot mode), the stateful approach
becomes more attractive because:
- The trim/churn problem shrinks relative to the total session length.
- The system prompt saving (~600 tokens × 60 turns = 36,000 tokens) is meaningful.
- Single-slot mode guarantees the same slot across calls.

The full plan is in `PLAN_STATEFUL_AGENT.md` and remains valid if that use case arises.

---
