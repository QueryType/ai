# Story Rewrite & Validation Tool

Post-run tool for editing a completed story. Lets you rewrite individual beats, validate coherence across all beats without changing anything, or cascade-regenerate everything from a given beat onward.

---

## Quick Start

```bash
conda activate strandsagents
cd /Volumes/d/code/aiml/story-engine

# Step 1 — for stories generated before this tool existed:
# add beat markers interactively (no LLM, takes ~30 seconds)
python -m my_code.rewrite scene.md --map

# Step 2 — check the whole story for coherence issues
python -m my_code.rewrite scene.md --validate

# Step 3 — rewrite a specific beat
python -m my_code.rewrite scene.md --beat 2
```

Stories generated from now on have beat markers embedded automatically — skip `--map`.

---

## How It Works

### Beat Markers

Every output `.md` file contains invisible HTML comment markers before each beat's prose:

```markdown
# My Story

<!-- beat:1 -->
The rain hadn't stopped in three days...

<!-- beat:2 -->
She found the letter beneath the floorboards...
```

HTML comments are **invisible in all markdown renderers** (VS Code, Obsidian, GitHub, etc.) and in TTS pipelines that parse markdown. They are visible only if you open the raw file in a text editor. See [TTS Export](#tts-export) for how to strip them cleanly.

These markers let the tool locate and splice individual beats without touching the rest of the file.

### Pipeline

```
Scene file (.md)          Output story (.md)
      │                          │
      │  beat instructions       │  existing prose (beat 1..N)
      │  characters, style       │  beat markers
      └──────────────────────────┘
                   │
          ┌────────┴────────┐
          │   rewrite.py    │
          └────────┬────────┘
                   │
      ┌────────────┼────────────┐
      │            │            │
   --map       --validate    --beat N
   (no LLM)   (9B only)     (31B + 9B)
```

---

## Modes

### `--show` — View Current Beat Markers

Print the current beat marker positions and a short excerpt from each beat. Useful for checking where beats are before deciding to remap or rewrite.

```bash
python -m my_code.rewrite scene.md --show
```

Example output:

```
Beat markers in output/ashenveil.md:
  Beat 1  →  line 3     The rain hadn't stopped in three days. Mira pulled...
  Beat 2  →  line 44    She found the letter beneath the floorboards. The ink...
  Beat 3  →  line 89    Aldric was waiting at the bridge, exactly where she...
  Beat 4  →  line 125   The archive smelled of dust and old ambition...
```

If no markers are found, it tells you to run `--map` first.

---

### `--map` — Mark Beat Boundaries (no LLM)

Use this once for stories generated before beat markers were added. New stories have markers embedded automatically.

```bash
python -m my_code.rewrite scene.md --map
```

The tool displays the story with line numbers, paginated:

```
Story: output/ashenveil.md  (4 beats, 3847 words)
────────────────────────────────────────────────────────────
  L1     The rain hadn't stopped in three days. Mira pulled...
  L2     her coat tighter as she stepped off the carriage...
  ...
  L80    She didn't look back.
  ...
  [Lines 1-30 of 142] Enter=next page | q=done:
```

Then for each beat boundary (last beat ends at EOF automatically):

```
Beat 1 ends at line: 80
Beat 2 ends at line: 112
Beat 3 ends at line: 128
(Beat 4 ends at EOF)

Markers written.
```

If markers already exist, the tool will ask before re-mapping.

---

### `--validate` — Coherence Pass (no rewrite)

Check every beat for contradictions against the beats before it. Nothing is rewritten — this is a report only.

```bash
# Check all beats
python -m my_code.rewrite scene.md --validate

# Check from beat 3 onward (beats 1 and 2 treated as ground truth)
python -m my_code.rewrite scene.md --validate --from-beat 3
```

**What it does:**
1. Re-summarises beats 1..N via the 9B summariser to rebuild continuity context.
2. Runs a coherence-only check on each beat in sequence.
3. Prints a report.

**Example output:**

```
════════════════════════════════════════════════════════════
  COHERENCE REPORT  (4 beat(s) checked)
════════════════════════════════════════════════════════════

  Beat 3: FLAGGED
    Aldric is described entering from the east gate, but in
    beat 2 he sealed it behind him and moved west.

  1 beat(s) flagged.
  To rewrite a flagged beat: python -m my_code.rewrite scene.md --beat N
```

The coherence checker only flags **factual contradictions** (wrong location, impossible timeline, inconsistent facts). It does not flag style or quality issues.

---

### `--beat N` — Rewrite One Beat

Re-narrate a single beat, then coherence-check all subsequent beats (report only — no automatic rewrite of them).

```bash
python -m my_code.rewrite scene.md --beat 2
```

**What it does:**
1. Re-summarises beats 1..N-1 (9B, cheap) to rebuild continuity context.
2. Injects beats 1..N-1 into the narrator's conversation history — no LLM calls, just replaying the message turns so the narrator has the right context.
3. Re-narrates beat N using the 31B narrator with the full retry/evaluate loop (same as a normal run).
4. Re-summarises beat N, then coherence-checks beats N+1..end.
5. Prints a coherence report for subsequent beats.
6. Splices the new beat N into the output file. Beats N+1..end are unchanged.

**Note on KV cache:** The narrator server's KV cache will not be warm at the start of a rewrite run (different process). Beat N will be a full context re-process — typically 15–30s longer than during the original run. This is unavoidable and only happens once.

---

### `--beat N --from-here` — Cascade Rewrite

Re-narrate beat N and everything after it. Use this when the change to beat N makes subsequent beats need to be regenerated.

```bash
python -m my_code.rewrite scene.md --beat 2 --from-here
```

**What it does:**
1–3. Same as `--beat N`.
4. Continues narrating beats N+1..end exactly like the main engine — narrator agent persists, KV cache builds normally from beat N+1 onward.
5. Overwrites the full output file from beat N onward.

The narrator state is maintained across beats N, N+1, N+2... so the cascade benefits from normal KV cache continuity after the first beat.

---

## CLI Reference

```
python -m my_code.rewrite SCENE.MD [options]
```

| Argument | Description |
|----------|-------------|
| `SCENE.MD` | The scene file used to generate the story (required) |
| `--show` | Print current beat marker positions and a short excerpt from each beat |
| `--map` | Interactive beat boundary marking (no LLM) |
| `--validate` | Coherence-check all beats, report only |
| `--from-beat N` | With `--validate`: start checking from beat N (default: 1) |
| `--beat N` | Rewrite beat N |
| `--from-here` | With `--beat N`: also re-narrate beats N+1..end |
| `--story PATH` | Override story output path (default: from scene meta `output_file`) |

---

## Model Configuration

No new environment variables. The rewrite tool uses the same `.env` configuration as the main engine:

| Task | Model used | Env var |
|------|-----------|---------|
| Re-narrate beat N | Narrator (31B) | `STORY_ENGINE_NARRATOR_BASE_URL` / `STORY_ENGINE_NARRATOR_MODEL` |
| Coherence check | Evaluator (9B) | `STORY_ENGINE_EVALUATOR_BASE_URL` / `STORY_ENGINE_EVALUATOR_MODEL` |
| Re-summarise beats | Summariser (9B) | `STORY_ENGINE_SUMMARISER_BASE_URL` / `STORY_ENGINE_SUMMARISER_MODEL` |

`--map` and `--validate` do not use the narrator at all — only the 9B server.

---

## TTS Export

Beat markers are invisible in markdown renderers but appear as raw text in some TTS pipelines. Strip them before feeding to your TTS tool:

```bash
# Strip markers, write clean copy
sed '/^<!--.*-->$/d' output/story.md > output/story_tts.md
```

Or as a one-liner before piping to your TTS:

```bash
sed '/^<!--.*-->$/d' output/story.md | your-tts-tool
```

The original file with markers is preserved — only the copy is stripped.

---

## Typical Workflow

### After a completed run

```bash
# New story — markers are already embedded. Skip --map.
python -m my_code.rewrite scene.md --validate

# Story looks good. You're done.
```

### Older story without markers

```bash
# Add markers once
python -m my_code.rewrite scene.md --map

# Then validate and rewrite as needed
python -m my_code.rewrite scene.md --validate
python -m my_code.rewrite scene.md --beat 3
```

### Beat 2 is wrong and invalidates everything after it

```bash
python -m my_code.rewrite scene.md --beat 2 --from-here
```

### Beat 3 feels off but beats 4+ are fine

```bash
python -m my_code.rewrite scene.md --beat 3
# Reads new beat 3, sees coherence report for beats 4+
# If beats 4+ are still coherent, done.
# If beat 4 is now flagged:
python -m my_code.rewrite scene.md --beat 4
```

---

## Troubleshooting

### `No beat markers found`

```
ERROR: No beat markers found in output/story.md.
Run: python -m my_code.rewrite scene.md --map
```

The story was generated before beat markers were added. Run `--map` once to add them.

### Coherence checker returns unparseable output

The 9B model occasionally wraps JSON in prose ("Based on my analysis..."). If the checker can't parse a response for a beat, it logs a warning and skips that beat. Re-run `--validate` — models are non-deterministic and a second pass usually succeeds.

### Rewrite takes longer than a normal beat

Expected. The narrator server's KV cache is cold at the start of a rewrite run. Beat N will re-process the full injected history (beats 1..N-1 as message turns) before generating. On a 31B model with 3 prior beats of ~1000 words each, expect an extra 20–40s for that first beat. Beats N+1 onward (in `--from-here` mode) will return to normal speed.

### `--from-here` is very slow on all beats

The narrator was likely swapping. Check that your two model servers together fit within your available RAM. On M4 64GB: 31B Q5_K_XL (≈20 GB) + 9B Q8_0 (≈9.5 GB) + system overhead (≈10–15 GB) ≈ 40–45 GB, well within limits.

### Scene file not found

The rewrite tool requires the original scene `.md` — it reads beat instructions, character cards, and narrator configuration from it. Make sure you pass the scene file, not the output file:

```bash
# Correct
python -m my_code.rewrite scene.md --beat 2

# Wrong — output file doesn't have beat instructions
python -m my_code.rewrite output/story.md --beat 2
```
