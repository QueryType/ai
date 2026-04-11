# Story Engine Context Usage and Endpoint Routing

This document is the canonical reference for how context is created, retained, and routed across agents.

It focuses on two things:
- Which agent calls are stateful vs stateless (and why that matters for token growth and KV cache reuse)
- How the two-endpoint design prevents cache thrashing

## 1. Context Model at a Glance

Pipeline per beat:

1. Lore context built via Python tools (no LLM context)
2. Narrator generates prose (stateful conversation context)
3. Evaluator checks prose (stateless, single-shot context)
4. BeatSummariser extracts continuity bullets (stateless, single-shot context)

Only the Narrator intentionally carries context across beats.

## 2. Agent-by-Agent Context Tracking

| Component | File | LLM Call | Conversation Manager | Instance Lifetime | Context Payload |
|---|---|---|---|---|---|
| Lore Injection | `my_code/agents/orchestrator.py` (`_call_lore_injector`) + `my_code/tools/lore_tools.py` | No | N/A | Per beat, pure Python | Beat text, character triggers, character cards, world info |
| Narrator | `my_code/agents/narrator.py` | Yes | `SummarizingConversationManager(summary_ratio=0.3, preserve_recent_messages=6)` | **Once per run** | System prompt + rolling conversation turns + summaries |
| Evaluator | `my_code/agents/evaluator.py` | Yes | `NullConversationManager()` | **Recreated each beat** | Beat instruction + prose + writing style + trimmed prior summary |
| BeatSummariser | `my_code/agents/summariser.py` | Yes | `NullConversationManager()` | **Recreated each beat** | Accepted prose for one beat |
| Orchestrator | `my_code/agents/orchestrator.py` | Control flow only | N/A | Full run | Checkpoint beats + accumulated `prior_summary` |

## 3. Narrator Context Composition

Narrator context has two layers:

1. Static system context (set once in `create_narrator`):
- narrator prompt
- writing style
- world info
- scene setup (if present)
- scenario
- writing instructions (if present)
- POV rule
- NSFW policy text
- per-beat length target
- player-character agency guardrail

2. Dynamic per-beat context (sent each call in `_call_narrator`):
- current beat instruction
- lore block generated for that beat
- optional author note (depth-triggered)
- optional redirect instruction

Cross-beat continuity is carried by the Narrator conversation manager, including automatic summarization behavior.

## 4. Evaluator Context Composition

Evaluator prompt is assembled in `_call_evaluator` and includes:
- beat instruction
- prose output
- writing style
- prior beat summaries

Important limiter:
- `_trim_prior_summary` keeps only the most recent `10` summary blocks (`_EVALUATOR_PRIOR_SUMMARY_WINDOW = 10`) to cap context growth.
- `_cap_prior_summary_chars` applies a hard character budget after window trim (`_EVALUATOR_PRIOR_SUMMARY_MAX_CHARS = 4500`).

Fallback behavior:
- if evaluator call errors or output parsing fails, orchestration falls back to pass and continues.

## 5. Continuity Memory Flow

Continuity memory is not maintained inside Evaluator or Summariser state.
It is externalized by Orchestrator in `prior_summary`:

1. Accepted beat prose -> BeatSummariser -> 3-5 bullet summary
2. Summary appended to `prior_summary`
3. Next evaluator call receives trimmed recent `prior_summary`
4. `prior_summary` is checkpointed after each accepted beat

This design keeps continuity data explicit and restart-safe.

Summary budget controls:
- Beat summary output is normalized and capped to reduce drift over long runs.
- Current limits in orchestrator:
	- `_SUMMARY_MAX_BULLETS = 5`
	- `_SUMMARY_MAX_BULLET_CHARS = 220`
	- `_SUMMARY_MAX_TOTAL_CHARS = 1000`

## 6. Checkpoint Context on Resume

Checkpoint file:
- `output/.<stem>.checkpoint.json`

Stored context:
- completed beat prose (`beats` map)
- `prior_summary`

Resume behavior:
- completed beats are skipped for generation
- completed beat instruction/output pairs are replayed into Narrator conversation to restore narrative memory

## 7. Two-Endpoint Concept (Core Performance Design)

### Goal

Protect Narrator's long-lived KV cache from eviction by stateless agent calls.

### Endpoint roles

- Endpoint A (port 8080): Narrator only (stateful, cache-sensitive)
- Endpoint B (port 8081): Evaluator + BeatSummariser (stateless, cache-insensitive)

### Why it matters

If stateful and stateless agents share one endpoint, agent switching can force full prompt reprocessing, especially as Narrator context grows. Separating endpoints isolates the expensive context from one-shot calls.

## 8. Current Routing

Routing logic comes from `my_code/models/provider.py` (`get_model(role)`) and agent factories.

Configured environment variables support:
- `STORY_ENGINE_NARRATOR_BASE_URL`
- `STORY_ENGINE_EVALUATOR_BASE_URL`
- `STORY_ENGINE_SUMMARISER_BASE_URL`
- fallback: `STORY_ENGINE_LOCAL_BASE_URL`

Current code wiring:
- Narrator uses `get_model("narrator")` -> honors narrator endpoint/model vars
- Evaluator uses `get_model("evaluator")` -> honors evaluator endpoint/model vars
- BeatSummariser uses `get_model("summariser")` -> honors summariser endpoint/model vars

Result:
- `STORY_ENGINE_SUMMARISER_BASE_URL` and `STORY_ENGINE_SUMMARISER_MODEL` are active controls for summariser traffic.
- Evaluator and Summariser can be pinned to the fast stateless endpoint independently of Narrator.

## 9. Context Growth Risk Points

Primary growth vector:
- Narrator conversation history across many beats (~1800 tokens/beat without intervention)

Secondary growth vector:
- `prior_summary` accumulation (mitigated by evaluator trimming window and char cap)

Operational controls:
- **`_trim_narrator_context(narrator)`** in orchestrator.py — called after each beat. Proactively
  triggers `reduce_context()` when `len(narrator.messages) > preserve_recent_messages`. This is
  necessary because `SummarizingConversationManager` is reactive-only: `apply_management()` is a
  no-op and summarization only fires on `ContextWindowOverflowException` from the server. Without
  proactive trimming, a 10-beat scene hits ctx=12288 at beat ~7.
- Evaluator prior-summary window trim (`_EVALUATOR_PRIOR_SUMMARY_WINDOW = 10`) + hard char cap
  (`_EVALUATOR_PRIOR_SUMMARY_MAX_CHARS = 4500`)
- Pure-Python lore injection (no extra LLM turn, no context cost)

## 11. Debugging Prompt Growth

Runtime INFO logs include per-beat token counts and message history depth:

```
Beat 3/5: narrator tokens in=5200 out=920 stop=end_turn (history=6 msgs)
Evaluator tokens in=16200 out=415 stop=end_turn
Narrator context trimmed: 8 → 4 messages
```

**Narrator `in` tokens** are per-beat deltas (the agent is reused, so the code snapshots
`agent.event_loop_metrics.accumulated_usage` before the call and logs the diff). `history=N msgs`
shows the live message count after the call, before trimming. Watch for this growing monotonically
without a "context trimmed" line — it means `_trim_narrator_context` is not firing.

**Evaluator `in` tokens** (~15–17k) represent the **sum of 4–5 sequential LLM calls** within
one evaluation (one call per tool in the tool-calling loop). This is normal. Each successive call
sees a slightly larger context as tool results accumulate. The modest per-beat growth reflects
`prior_summary` expanding.

**Evaluator `out` tokens** should be small (300–500). If they approach 4096, the evaluator is
hitting its context limit and tool calls likely aren't completing. Check for `EVALUATOR FALLBACK`
WARNING lines.

Debug-level logs also emit character-count breakdowns for narrator prompt fields and evaluator
prior-summary windowing/capping, useful for diagnosing runaway prompt growth.

## 10. Practical Operating Guidance

For stable long runs:

1. Keep Narrator on a dedicated endpoint/model.
2. Keep stateless agents on a fast separate endpoint/model.
3. Monitor narrator prompt size and latency growth over beats.
4. Keep lore injection LLM-free unless deterministic behavior changes.
5. Ensure summariser routing matches desired endpoint split.
