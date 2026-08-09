# Rewrite Tool — Implementation Plan

## What it is

`my_code/rewrite.py` — a CLI tool for post-run story editing.
Lets the user rewrite a specific beat, validate coherence across all beats, or cascade-rewrite from a beat onward.

## Usage

```bash
# One-time: mark beat boundaries in an existing output file (no LLM)
python -m my_code.rewrite scene.md --map

# Coherence-only pass on all beats (no narrator, just evaluator)
python -m my_code.rewrite scene.md --validate
python -m my_code.rewrite scene.md --validate --from-beat 3

# Rewrite one beat, then coherence-check subsequent beats (report only)
python -m my_code.rewrite scene.md --beat 3

# Rewrite beat 3 and re-narrate everything after it
python -m my_code.rewrite scene.md --beat 3 --from-here
```

## Beat markers

HTML comments embedded in the output `.md` file — invisible in any markdown renderer, parseable as plain text.

```
<!-- beat:1 -->
Beat 1 prose...

<!-- beat:2 -->
Beat 2 prose...
```

New runs: `_save_final_output` in `orchestrator.py` embeds markers automatically.
Old files: `--map` adds them interactively (user provides line numbers, no LLM).

Detection: if `<!-- beat:1 -->` not found in output file → tell user to run `--map` first.

## Phase 1 — Beat marker support (orchestrator.py)

- Modify `_save_final_output` to embed `<!-- beat:N -->` before each beat in all three output formats
- Add `_parse_output_beats(path) -> dict[int, str]` helper (reads markers, returns `{1: prose, 2: prose, ...}`)
- Shared by all CLI modes

## Phase 2 — `--map` (no LLM)

- Display output prose paginated with line numbers
- Prompt: "Beat 1 ends at line: _" × (N-1) beats
- Validate ordering and range
- Insert `<!-- beat:N -->` markers into existing file

## Phase 3 — `--validate` (coherence pass, 9B only)

- Parse beats from output file
- Re-summarise each beat via BeatSummariser → rebuild `prior_summary`
- Run coherence-only single-pass evaluator on each beat
  - New `create_coherence_checker()` in `evaluator.py`
  - Stripped system prompt: coherence dimension only, no beat coverage, no style
  - No tools, returns JSON `{coherent, issues, reason}`
- Print report: which beats flagged and why
- No file changes

## Phase 4 — `--beat N` (single beat rewrite)

- Parse beats from output file
- Re-summarise beats 1..N-1 → rebuild `prior_summary`
- Inject beats 1..N-1 directly into narrator.messages (fake conversation turns, no LLM calls)
  - User message: reconstructed beat prompt (same format as `_call_narrator`)
  - Assistant message: existing prose
- Re-narrate beat N → full evaluate (coverage + style + coherence) → retry loop
- Auto-run coherence-only pass on beats N+1..end → report flags
- Splice new beat N into output file, keep N+1..end untouched

## Phase 5 — `--from-here` (cascade rewrite)

- Same as Phase 4 up to re-narrating beat N
- Then continue narrating N+1..end with full beat loop (same logic as orchestrator.run_scene)
- Checkpointing applies — can resume if interrupted
- Full output file rewritten from beat N onward

## Files to create/modify

| File | Change |
|---|---|
| `my_code/agents/orchestrator.py` | Embed markers in `_save_final_output`; add `_parse_output_beats` |
| `my_code/agents/evaluator.py` | Add `create_coherence_checker()` |
| `my_code/rewrite.py` | New — CLI entry point + all four modes |

## Constraints / decisions made

- No new models. 9B (port 8081) handles validate + summarise. 31B (port 8080) handles narration.
- No new servers, no new dependencies.
- Narrator history injection is direct message-list manipulation — zero LLM calls for prior beats.
- KV cache will NOT be warm on the server for the rewrite (different process) — beat N will be a full re-process. Acceptable for a one-off rewrite.
- `--validate` coherence check is report-only. User must explicitly `--beat N` to rewrite flagged beats.
- TTS pipeline: strip markers with `sed '/^<!--.*-->$/d' story.md > story_tts.md` or add `--export` flag later.
- User's typical workload: 4 beats, 3500-4000 words. Well within all model context limits.
