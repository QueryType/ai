# Performance Analysis — llama.cpp Server Slowness

**Date:** 2026-04-10  
**Model:** Gemma-4-31B-IT (UD-Q5_K_XL, 20.37 GiB) on Apple M4 Pro via Metal  
**Server config observed:** `n_ctx=32768`, `n_slots=1`, `--cache-prompt-size 8192 MiB`

---

## Implementation Status (updated 2026-04-11)

All high-value fixes from this analysis have been implemented. Measured outcome on a 5-beat scene:

| Metric | Before | After |
|--------|--------|-------|
| Evaluator per beat | ~185s | ~25s |
| Total 5-beat runtime | 28m 24s | 15m 43s |
| Peak memory (M4 Pro 64GB) | 58.7 GB + 2.3 GB swap | 51.2 GB, no swap |

**Fix A — Separate endpoints:** Done. Narrator on port 8080 (31B), Evaluator+Summariser on port 8081 (9B). Narrator KV cache is never evicted.

**Fix B (partial) — n_ctx reduced:** Narrator at 12288 (was 32768). Stateless endpoint at 4096.

**Fix C — Narrator context management:** `_trim_narrator_context()` added to orchestrator.py. Calls `reduce_context()` proactively after each beat when message count exceeds `preserve_recent_messages=6`. `SummarizingConversationManager` is reactive-only (summarizes on server overflow, not proactively) — without this function, input grows ~1800 tokens/beat and ctx=12288 is exceeded at beat ~7.

**Fix D — Remove LLM from LoreInjector:** Done. Lore injection is pure Python (regex + dict lookup). Zero LLM calls, zero cache impact per beat.

**Additional fix (discovered 2026-04-11) — Eval tool parameters:** The evaluator tool functions (`check_beat_coverage`, `check_style_compliance`, `check_coherence`) were accepting full `prose_output` and `beat_instruction` as parameters. This caused ~5600 tokens of output per evaluation, exceeding ctx=4096 on every beat. The `MaxTokensReachedException` fallback silently returned pass — the evaluator had never evaluated anything. Removed large parameters from tool signatures; tools now accept only booleans and reason strings.

**Fix E (n_keep / system prompt pinning):** Not implemented. Unnecessary given the dedicated narrator endpoint.

**Fix F (pipeline reordering):** Not needed. With separate endpoints, agent switching has no cache cost.

---

---

## Symptom

Response latency grows with each beat: ~15s early in a run, growing to 350–475s per beat by beat 30+. Prompt eval time dominates and scales super-linearly with conversation length.

---

## Root Causes

### 1. Multi-agent context thrashing (primary cause)

All four agents — Narrator, Evaluator, LoreInjector, BeatSummariser — are configured to use the **same model endpoint**. Each has a completely different system prompt. Every time the pipeline switches agents the server must evict the current KV cache and reprocess the new agent's full context from scratch.

The server logs confirm this pattern on nearly every turn:

```
forcing full prompt re-processing due to lack of cache data
(likely due to SWA or hybrid/recurrent memory)
```

Followed by erasing every single checkpoint and reprocessing from token 0.

### 2. SWA (Sliding Window Attention) makes cache invalidation total

Gemma-4 uses Sliding Window Attention on 50 of 60 layers (`n_swa = 1024`). When a new conversation starts at position 0 with a different system prompt, none of the existing sliding-window KV checkpoints are valid — the SWA window positions no longer align. The server correctly erases all prior checkpoints.

This turns every "cache miss" into a "full reprocess from scratch" rather than a partial reuse.

### 3. Narrator context grows unboundedly

The `SummarizingConversationManager(summary_ratio=0.3, preserve_recent_messages=10)` is not keeping context small enough. Each beat adds ~600–1000 tokens, and summarisation only triggers when the budget is already exhausted.

Observed growth:

| Approx beat | Prompt tokens | Prompt eval time |
|-------------|--------------|-----------------|
| 1           | ~1,385       | 14.8s           |
| 5           | ~4,832       | 18.0s           |
| 10          | ~6,393       | 85.3s           |
| 20          | ~16,500      | 232.5s          |
| 30          | ~22,989      | 335.9s          |

By beat 30 the Narrator is sending 23k-token prompts on every turn, and the full reprocess on every agent switch means this cost is paid repeatedly.

### 4. Cache save/restore overhead

Every agent switch triggers a cache serialisation cycle. As conversation state grows, so does the blob:

```
srv: prompt cache update took 14292.71 ms
srv: prompt cache update took  9647.92 ms
srv: prompt cache update took  6934.81 ms
```

This overhead is paid on top of prompt eval time and scales with conversation size.

### 5. Cache size limit too small to hold multiple conversations

The server's `--cache-prompt-size` is 8 GiB but mid-run conversation state reaches 14–17 GiB per conversation. The server can only hold one conversation in cache at a time:

```
srv: cache size limit reached, removing oldest entry (size = 14019.311 MiB)
srv: cache state: 1 prompts, ...
```

Every agent switch is a guaranteed full eviction + reload cycle.

### 6. Stateless agents waste reprocessing work

LoreInjector, Evaluator, and BeatSummariser use `NullConversationManager` — they are stateless and each call discards the KV state immediately. Despite this, they still interrupt the Narrator's cache slot, triggering a full round-trip for what amounts to a single-shot call.

### 7. Sequential blocking pipeline, no parallelism

Each beat executes this fully sequentially:

1. LoreInjector call → evicts Narrator cache, reprocesses LoreInjector prompt
2. Narrator call → evicts LoreInjector cache, reprocesses Narrator's growing history
3. Evaluator call → evicts Narrator cache, reprocesses Evaluator prompt
4. BeatSummariser call → evicts Evaluator cache, reprocesses Summariser prompt
5. (On retry: steps 3 + 2 again, up to 3× each)

Minimum 4 full context-switch cycles per beat; up to 9+ with retries.

---

## Directions for Improvement

### A. Separate endpoints per agent class

Route stateless agents (Evaluator, LoreInjector, BeatSummariser) to a different server instance or a smaller/faster model. Reserve the 31B endpoint exclusively for the Narrator so its KV cache is never evicted mid-beat.

Options:
- Second llama.cpp instance on a different port running a smaller model (e.g. 7B–9B)
- `STORY_ENGINE_EVALUATOR_MODEL` etc. pointed at a different `base_url`

### B. Increase server cache or use `n_slots > 1`

If hardware allows, run the server with `--n-slots 2` so Narrator and at least one stateless agent each have a dedicated slot with no eviction. Alternatively raise `--cache-prompt-size` above the peak conversation size (~3 GiB at beat 30 for a well-managed context).

### C. Tighten Narrator context management

The `SummarizingConversationManager` needs more aggressive settings, or the beat replay on resume needs to cap the history depth. Options:
- Lower `preserve_recent_messages` (e.g. 6)
- Add a hard token budget check before each Narrator call and pre-summarise if needed
- Compress completed beats more aggressively in the replay path

### D. Collapse stateless agent calls where possible

LoreInjector's keyword scan doesn't necessarily need an LLM call — it is a deterministic regex operation. Removing the LLM call for lore injection entirely would eliminate one cache-switch per beat.

Evaluator and BeatSummariser could potentially share a single system-prompt prefix to improve cache reuse between them.

### E. Use `--keep` / `n_keep` for system prompt pinning

Pass `n_keep = <system_prompt_token_count>` in requests so the server never evicts the system prompt portion of the KV cache, even when context pressure forces rolling. This would help the Narrator's large static system prompt stay cached.

### F. Reorder pipeline to minimise switches

If stateless agents must share the same endpoint, batching them together (LoreInjector → Evaluator → BeatSummariser in sequence, with Narrator called last/first) reduces the number of Narrator↔stateless round-trips per beat from 4 to 2.

---

## Key Metric to Watch

**Prompt eval tokens per beat** (visible in server timing lines). A healthy run should stay flat or grow slowly. Once this exceeds ~4k tokens per Narrator call, the compounding reprocess cost starts dominating total wall time.

---

## Prognosis

### What's actually broken vs. what's architectural

The SWA cache invalidation sounds alarming but it is almost entirely a symptom of the multi-agent thrashing. If the Narrator's slot is never evicted, SWA stops mattering — the server just extends the existing sliding window incrementally on each beat, processing only the new tokens (~100–300 per turn). That is the difference between 232s and ~3s for a beat-20 Narrator call.

### High-value fixes, in order of impact

**1. Separate endpoints — biggest win, easiest change**

It is literally a few lines in `.env`:
```
STORY_ENGINE_EVALUATOR_BASE_URL=http://192.168.1.5:8081/v1
STORY_ENGINE_LORE_INJECTOR_BASE_URL=http://192.168.1.5:8081/v1
STORY_ENGINE_SUMMARISER_BASE_URL=http://192.168.1.5:8081/v1
```
Run a second llama.cpp instance on port 8081 with a smaller model (Qwen3 9B or similar). The Narrator's 31B cache becomes untouchable. The stateless agents get a fast cheap model. This alone would cut per-beat time by ~80% at beat 20+.

**2. Remove the LLM from LoreInjector — free speedup**

LoreInjector is already doing keyword-triggered character card retrieval via deterministic regex (`re.search(r"\b" + trigger + r"\b", beat_text)`). That does not need an LLM at all. Removing that call eliminates one full cache-switch per beat with zero quality loss.

**3. Tighten the Narrator's context**

`preserve_recent_messages=10` is too generous given how verbose each beat exchange is. Dropping it to 4–6 messages and tightening `summary_ratio` would keep the Narrator's prompt under ~6k tokens even at beat 30, keeping prompt eval fast regardless of other factors.

### What cannot be fixed easily

The sequential pipeline is the one structural limitation. Narrator and Evaluator cannot run in parallel because Evaluator needs Narrator's output — that ordering is correct by design. But once the cache thrashing is gone, sequential stops being a problem: 3s Narrator + 2s Evaluator + 1s Summariser is a perfectly reasonable per-beat budget.

### Realistic outcome

With fix #1 (separate endpoints) and fix #2 (drop LoreInjector LLM call), a 30-beat run that currently takes hours should complete in 20–35 minutes. Per-beat time would stay roughly flat across the whole run instead of growing without bound.

---

## Context Size Recommendations

### How the KV cache breaks down (Gemma-4-31B)

```
Non-SWA (global, 10 layers):  32768 cells = 2560 MiB  ← scales with n_ctx
SWA     (sliding, 50 layers):  1536 cells = 1200 MiB  ← FIXED regardless of n_ctx
```

The SWA cache is fixed — it only ever needs 1024 tokens. Only the 10 global layers scale with `n_ctx`. The model weights dominate at ~22 GiB, so context size changes yield modest memory savings.

| n_ctx | Global KV | SWA KV | Total KV | Total incl. model |
|-------|-----------|--------|----------|-------------------|
| 32768 | 2560 MiB  | 1200 MiB | 3760 MiB | ~26.3 GiB |
| 16384 | 1280 MiB  | 1200 MiB | 2480 MiB | ~25.0 GiB |
| 12288 |  960 MiB  | 1200 MiB | 2160 MiB | ~24.7 GiB |
|  8192 |  640 MiB  | 1200 MiB | 1840 MiB | ~24.4 GiB |

### What the story-engine actually needs (Narrator endpoint)

With tighter context management:
- System prompt: ~1500–2500 tokens
- Active conversation (6 recent messages): ~3000–5000 tokens
- Running summary of older beats: ~500–1000 tokens
- **Realistic peak: ~8000–9000 tokens**

**Recommendation: `n_ctx = 12288` for the Narrator (31B) endpoint.** Covers the realistic workload with a safety margin. 32768 is overkill once context is managed well. The smaller blob also directly reduces the cache save/restore overhead seen in the logs.

**Recommendation: `n_ctx = 4096` for the stateless agents endpoint.** Single-shot calls never exceed ~3k tokens.

---

## Second Endpoint — Model Selection

The 31B model uses ~26 GiB, leaving ~23 GiB free on the M4 Pro. Available GGUFs already on disk and their suitability:

| Model | Size | Active params | Notes |
|-------|------|--------------|-------|
| `HauhauCS/Qwen3.5-9B-Uncensored-Q8_0.gguf` | ~10 GiB | 9B | **Recommended** |
| `lmstudio-community/Qwen3.5-9B-Q6_K.gguf` | ~7 GiB | 9B | Clean variant, good fallback |
| `unsloth/gemma-4-E4B-it-UD-Q8_K_XL.gguf` | ~6 GiB | ~4B active (MoE) | Same arch as main model |
| `TheDrummer/Rocinante-X-12B-v1b-Q6_K.gguf` | ~10 GiB | 12B | Creative-writing tuned |
| `mistral/Mistral-Nemo-Instruct-2407.Q6_K.gguf` | ~9 GiB | 12B | Older, less competitive |
| `unsloth/GLM-4.7-Flash-Q4_K_S.gguf` | ~3 GiB | 4.7B | Fast but possibly too small for evaluation |

### Recommended: `Qwen3.5-9B-Uncensored-Q8_0`

**Path:** `/Volumes/d/aimodels/HauhauCS/Qwen3.5-9B-Uncensored-HauhauCS-Aggressive/Qwen3.5-9B-Uncensored-HauhauCS-Aggressive-Q8_0.gguf`

Reasons:
- **Uncensored matters** — the Evaluator scores potentially explicit story content; a censored model will hedge or refuse adult beat evaluation
- **Qwen3.5 excels at structured output** — the Evaluator emits JSON with specific fields; Qwen handles this better than most architectures
- **Q8_0 is near-lossless** — at 9B, high quantisation quality compensates for smaller parameter count
- **Fits comfortably** — ~10 GiB leaves ~13 GiB free alongside the 31B model

### Runner-up: `gemma-4-E4B-it-UD-Q8_K_XL`

Same tokenizer and chat template as the main model — no configuration changes needed beyond the model path. MoE architecture means only ~4B params activate per token, making it extremely fast. The uncensored `kamjin` variant is also available on disk.

### Start command for the second instance

```bash
./llama-server \
  -m /Volumes/d/aimodels/HauhauCS/Qwen3.5-9B-Uncensored-HauhauCS-Aggressive/Qwen3.5-9B-Uncensored-HauhauCS-Aggressive-Q8_0.gguf \
  --port 8081 \
  --ctx-size 4096 \
  --n-gpu-layers 99 \
  --host 0.0.0.0
```
