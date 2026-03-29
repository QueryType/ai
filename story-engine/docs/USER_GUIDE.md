# Story Engine — User Guide

A multi-agent story generation engine that reads structured scene files and produces narrative prose using local or cloud LLMs.

---

## Table of Contents

1. [Quick Start](#1-quick-start)
2. [Configuration](#2-configuration)
3. [Writing Scene Files](#3-writing-scene-files)
4. [Scene File Reference](#4-scene-file-reference)
5. [Execution Modes](#5-execution-modes)
6. [Interactive Commands](#6-interactive-commands)
7. [Output Formats](#7-output-formats)
8. [Stitching a Full Story](#8-stitching-a-full-story)
9. [Resume & Checkpoints](#9-resume--checkpoints)
10. [Troubleshooting](#10-troubleshooting)

---

## 1. Quick Start

```bash
# 1. Activate the conda environment
conda activate strandsagents

# 2. Copy and edit the config
cp .env.example .env
# Edit .env with your model URL and model name (see §2)

# 3. Run a scene
python -m my_code examples/ashenveil_scene1.md

# 4. Find your output
cat output/ashenveil_scene1.md
```

---

## 2. Configuration

All configuration lives in a single `.env` file at the project root.

### 2.1 The `.env` File

Copy `.env.example` to `.env` and edit:

```env
# Provider: local | openrouter | anthropic | bedrock
STORY_ENGINE_PROVIDER=local

# Local backend URL (LM Studio / llama.cpp / Ollama)
STORY_ENGINE_LOCAL_BASE_URL=http://192.168.1.5:7890/v1

# Model IDs — set to whatever you have loaded
STORY_ENGINE_NARRATOR_MODEL=qwen3.5-9b-uncensored-hauhaucs-aggressive
STORY_ENGINE_EVALUATOR_MODEL=qwen3.5-9b-uncensored-hauhaucs-aggressive
STORY_ENGINE_ORCHESTRATOR_MODEL=qwen3.5-9b-uncensored-hauhaucs-aggressive
STORY_ENGINE_LORE_INJECTOR_MODEL=qwen3.5-9b-uncensored-hauhaucs-aggressive

# Cloud keys (only needed if STORY_ENGINE_PROVIDER != local)
# OPENROUTER_API_KEY=sk-or-...
# ANTHROPIC_API_KEY=sk-ant-...
```

### 2.2 Provider Options

| Provider | `STORY_ENGINE_PROVIDER` | `BASE_URL` | Notes |
|----------|------------------------|------------|-------|
| **LM Studio** | `local` | `http://<ip>:<port>/v1` | Default port 1234 |
| **llama.cpp** | `local` | `http://<ip>:<port>/v1` | Use `--api-key` if set |
| **Ollama** | `local` | `http://localhost:11434/v1` | Models like `llama3.1:8b` |
| **OpenRouter** | `openrouter` | (automatic) | Needs `OPENROUTER_API_KEY` |
| **Anthropic** | `anthropic` | (automatic) | Needs `ANTHROPIC_API_KEY` |
| **AWS Bedrock** | `bedrock` | (automatic) | Uses AWS credentials |

### 2.3 Per-Role Models

The engine uses 4 agents, each configurable independently:

| Env Var | Agent | Job | Can use cheaper model? |
|---------|-------|-----|------------------------|
| `STORY_ENGINE_NARRATOR_MODEL` | Narrator | Writes prose | No — use your best model |
| `STORY_ENGINE_EVALUATOR_MODEL` | Evaluator | Quality checks | Yes — lighter model works |
| `STORY_ENGINE_ORCHESTRATOR_MODEL` | Orchestrator | Coordinates | Yes — lighter model works |
| `STORY_ENGINE_LORE_INJECTOR_MODEL` | Lore Injector | Context assembly | Yes — lighter model works |

When using a single local model, set all four to the same value.

### 2.4 Command Line Options

```
python -m my_code <scene_file>
python -m my_code --file <scene_file>
python -m my_code <scene_file> --verbose    # debug logging
```

---

## 3. Writing Scene Files

A scene file is a single `.md` file that describes one scene of your story. It contains everything the engine needs: narrator identity, characters, world, plot beats, and style.

### 3.1 Minimal Scene File

The smallest valid scene file:

```markdown
[meta]
title: My Scene
mode: autonomous
output_file: output/my_scene.md
output_format: prose
pov: third-person

[narrator-prompt]
You are the narrator of a fantasy story.

[writing-style]
Third person past tense. Show don't tell.

[world-info]
A medieval fantasy world with magic.

[character-1]
name: Elena
role: player-character
triggers: Elena, she
description: A young warrior.
personality: Brave and stubborn.

[scenario]
Elena enters a dark forest for the first time.

[scene-beats]
1. Elena arrives at the forest edge. Establish atmosphere.
2. She ventures inside. Something watches her from the trees.
```

### 3.2 Recommended File Naming

```
[world-name]_scene[N]_[short-descriptor].md

Examples:
  ashenveil_scene1_ruins_approach.md
  thornwood_scene3_the_ambush.md
  ironport_scene1_arrival.md
```

### 3.3 Tips for Good Beat Instructions

**Do this:**
```
1. Elena spots the creature in the canopy. She freezes.
   Establish her fear through physical reaction, not narration.
```

**Not this:**
```
1. Write a paragraph about Elena being scared of a monster.
```

Beat instructions should be **directional** (what happens) not **prescriptive** (how to write it). Tell the narrator *what*, let it figure out *how*.

---

## 4. Scene File Reference

### `[meta]` — Required

Controls execution and output.

| Field | Required | Options | Default | Description |
|-------|----------|---------|---------|-------------|
| `title` | yes | any string | — | Scene title, used in output header |
| `mode` | yes | `autonomous` \| `interactive` \| `semi-interactive` | — | Execution mode (see §5) |
| `output_file` | yes | file path | — | Where to write the output |
| `output_format` | yes | `prose` \| `adventure` \| `script` | — | Output formatting (see §7) |
| `pov` | yes | `third-person` \| `first-person` \| `second-person` | — | Point of view |
| `version` | no | string | `1.0` | Schema version |
| `pause_at` | no | `beat` | `beat` | Where semi-interactive pauses |
| `target_length` | no | integer | `1500` | Target total word count |
| `language` | no | ISO code | `en` | Language code |
| `nsfw` | no | `true` \| `false` | `false` | Content guidance for narrator |

### `[narrator-prompt]` — Required

Free text. The narrator's identity and core rules. This becomes the system prompt.

```markdown
[narrator-prompt]
You are the narrator of a dark fantasy world.
Write in third-person past tense.
Never break character. Never summarize — show through scene.
Do not make decisions for the player character.
```

### `[writing-style]` — Required

Free text. *How* the narrator writes — separate from *who* it is. Can be swapped between scenes without changing the narrator.

```markdown
[writing-style]
Literary fiction. Show don't tell. Paragraph breaks for pacing.
Dialogue in quotes. Internal thoughts in italics.
Avoid purple prose. Use sensory detail — not just visuals.
```

### `[author-note]` — Optional

A persistent reminder injected every N beats.

```markdown
[author-note]
depth: 4
content: Maintain tension. Don't resolve conflicts prematurely.
```

| Field | Description |
|-------|-------------|
| `depth` | Inject every N beats (e.g., `4` = every 4th beat) |
| `content` | Free text reminder to the narrator |

### `[world-info]` — Required

Global world lore. **Always** included in every beat — keep it concise (~300 words max). Not keyword-triggered.

```markdown
[world-info]
Ashenveil is a crumbling empire. Magic is rare and feared.
The ruling Conclave hoards all written knowledge.
```

### `[character-N]` — At least one required

One block per character. `N` is any integer (1, 2, 3...).

| Field | Required | Description |
|-------|----------|-------------|
| `name` | yes | Character's full name |
| `role` | yes | `player-character` \| `npc` \| `antagonist` \| `neutral` |
| `triggers` | yes | Comma-separated keywords that activate this card |
| `description` | yes | Physical appearance, age, key details |
| `personality` | yes | Core traits, how they behave |
| `backstory` | no | Relevant history |
| `speech_style` | no | How they talk (strongly recommended) |

**Roles explained:**

| Role | Narrator behaviour |
|------|-------------------|
| `player-character` | Describes reactions/perceptions but **never** makes decisions for them |
| `npc` | Full creative control |
| `antagonist` | Full creative control, treated as opposition |
| `neutral` | Full creative control, background/environmental |

**Triggers:** The lore injector scans each beat's text for these keywords. If a trigger matches, that character's card is injected into the narrator's context. Use the character's name, pronouns, titles, or descriptions.

```markdown
triggers: Lyra, she, Voss, the scout, the woman
```

### `[scene-setup]` — Required (fields optional)

Physical and sensory context.

```markdown
[scene-setup]
location: A forest clearing at twilight.
time: Late evening, summer. Stars visible.
atmosphere: Peaceful but with an undercurrent of unease.
```

### `[scenario]` — Required

The backstory/situation leading into this scene. Included once at scene start, not repeated every beat.

```markdown
[scenario]
Elena has been travelling for three days. She heard rumours
of a shrine in the forest that grants visions of the future.
```

### `[scene-beats]` — Required

Numbered list of plot beats. Each beat = one generation cycle.

```markdown
[scene-beats]
1. Elena arrives at the clearing. Establish atmosphere.

2. She finds the shrine. It's not what she expected.
   [pause]

3. A voice speaks from inside the shrine.
```

**`[pause]` marker:** In `semi-interactive` mode, the engine pauses here for human input. In `autonomous` mode, `[pause]` is ignored. In `interactive` mode, every beat pauses regardless.

### `[writing-instructions]` — Optional but Recommended

Scene-specific creative direction. Injected once at scene start.

```markdown
[writing-instructions]
Start mid-action, not with Elena arriving. The shrine should
feel alive, not just a stone structure. Build dread slowly.
```

---

## 5. Execution Modes

Set via `mode:` in `[meta]`.

### `autonomous`

Runs all beats to completion with no human involvement.

```
Parse → Beat 1: Lore → Narrate → Evaluate → Beat 2: ... → Save
```

Best for: batch generation, overnight runs, first drafts.

### `interactive`

Pauses after **every** beat for human input.

```
Parse → Beat 1: Lore → Narrate → Evaluate → PAUSE → Beat 2: ...
```

Best for: collaborative writing, steering the narrative in real-time.

### `semi-interactive`

Pauses only at beats marked with `[pause]`.

```
Parse → Beat 1 (auto) → Beat 2 [pause] → PAUSE → Beat 3 (auto) → ...
```

Best for: reviewing key moments while letting routine beats auto-generate.

---

## 6. Interactive Commands

When the engine pauses, you see:

```
============================================================
  Beat 2/5 complete
============================================================

[prose output here]

────────────────────────────────────────────────────────────
Commands: Enter=continue | /skip | /stop | /retry | free text=redirect
>
```

| Input | What happens |
|-------|-------------|
| **Enter** (empty) | Accept prose, continue to next beat |
| **`/skip`** | Discard this beat, move to next |
| **`/stop`** | Save what's done so far, exit |
| **`/retry`** | Regenerate this beat from scratch |
| **Any other text** | Redirect — your text is fed back to the narrator as a new instruction, beat is regenerated |

**Redirect example:**
```
> Make the dialogue more confrontational. Lyra should threaten him.
```

The narrator receives your redirect and rewrites the beat accordingly.

---

## 7. Output Formats

Set via `output_format:` in `[meta]`.

### `prose` (default)

Seamless narrative with no beat markers. Reads like a continuous story.

```markdown
# The Ruins of Ashenveil

The fog didn't roll in; it exhaled...

Lyra stepped from the shadows...
```

### `adventure`

Beat headers included. Useful for reviewing structure.

```markdown
# The Ruins of Ashenveil

## Beat 1

The fog didn't roll in; it exhaled...

## Beat 2

Lyra stepped from the shadows...
```

### `script`

Screenplay-style formatting with beat markers.

```markdown
# The Ruins of Ashenveil

---
**BEAT 1**

The fog didn't roll in; it exhaled...

---
**BEAT 2**

Lyra stepped from the shadows...
```

---

## 8. Stitching a Full Story

Each scene file produces one output file. For multi-scene stories:

### 8.1 Organise by Folder

```
stories/
  ashenveil/
    ashenveil_scene1_ruins_approach.md
    ashenveil_scene2_the_descent.md
    ashenveil_scene3_the_revelation.md
```

### 8.2 Run Each Scene

```bash
python -m my_code stories/ashenveil/ashenveil_scene1_ruins_approach.md
python -m my_code stories/ashenveil/ashenveil_scene2_the_descent.md
python -m my_code stories/ashenveil/ashenveil_scene3_the_revelation.md
```

### 8.3 Stitch Outputs Together

Use a simple concatenation:

```bash
cat output/ashenveil_scene1.md \
    output/ashenveil_scene2.md \
    output/ashenveil_scene3.md > output/ashenveil_full_story.md
```

Or for cleaner results with chapter breaks:

```bash
for f in output/ashenveil_scene*.md; do
    cat "$f"
    echo -e "\n\n---\n"
done > output/ashenveil_full_story.md
```

### 8.4 Continuity Between Scenes

The engine does **not** carry state between scene files (by design — each scene is self-contained). To maintain continuity:

1. **Reuse character cards** — copy `[character-N]` blocks between scene files, or keep a shared character library and paste from it.

2. **Update the scenario** — each scene's `[scenario]` should summarise what happened in previous scenes:

   ```markdown
   [scenario]
   In the previous scene, Lyra and Aldric entered the ruins and
   discovered a glowing bookshelf. Aldric touched one of the volumes.
   Now they are deeper inside, and the door has sealed behind them.
   ```

3. **Update world-info** — if the world state changed (e.g., a city was destroyed), update `[world-info]` in subsequent scenes.

4. **Consistent writing style** — reuse the same `[narrator-prompt]` and `[writing-style]` across all scenes in a story for voice consistency.

### 8.5 Example: Multi-Scene Project Structure

```
stories/ashenveil/
├── shared/
│   ├── characters.md        ← copy character blocks from here
│   ├── world_info.md        ← shared world-info text
│   └── narrator_style.md    ← shared narrator + writing style
├── scene1_ruins_approach.md
├── scene2_the_descent.md
├── scene3_the_revelation.md
output/
├── ashenveil_scene1.md
├── ashenveil_scene2.md
├── ashenveil_scene3.md
└── ashenveil_full_story.md  ← stitched final
```

---

## 9. Resume & Checkpoints

If a run is interrupted (crash, `/stop`, Ctrl+C), you can resume from where it left off.

### How It Works

- After each beat completes, the engine writes a checkpoint file:
  `output/.ashenveil_scene1.checkpoint.json`
- On the next run of the same scene file, it detects the checkpoint, skips completed beats, and continues from the next one.
- On successful completion, the checkpoint is automatically deleted.

### Resuming

Just run the same command again:

```bash
# First run — interrupted after beat 2
python -m my_code examples/ashenveil_scene1.md
# ^C or crash

# Resume — picks up at beat 3
python -m my_code examples/ashenveil_scene1.md
# Logs: "Resuming from checkpoint: 2/5 beats already done"
```

### Starting Fresh

To discard a checkpoint and start over, delete it:

```bash
rm output/.ashenveil_scene1.checkpoint.json
```

---

## 10. Troubleshooting

### Connection refused / model not responding

```
ConnectionError: ... http://192.168.1.5:7890/v1
```

- Check your LM Studio / llama.cpp is running and the URL in `.env` is correct.
- Verify with: `curl http://192.168.1.5:7890/v1/models`

### Model not found

```
NotFoundError: model 'xyz' not found
```

- The model ID in `.env` must match exactly what's loaded in LM Studio.
- Check available models: `curl http://192.168.1.5:7890/v1/models`

### Tool calling errors

Some local models don't support function/tool calling. The Orchestrator, Evaluator, and Lore Injector agents require it. The Narrator does not.

Models known to support tool calling well:
- Qwen 2.5/3.x series
- Llama 3.1+ (with proper chat template)
- Mistral/Mixtral (function calling variants)

### Evaluator always passes

This is normal for capable models. The evaluator checks beat coverage, style compliance, and coherence. If the narrator does a good job, everything passes. You'll see retries when the model drifts off-topic or misses the beat instruction.

### Output is too long / too short

Adjust `target_length` in `[meta]`. The engine calculates a per-beat word target:

```
words_per_beat = target_length / number_of_beats
```

The narrator uses this as guidance, not a hard limit.

### Slow generation

Local models take time. A 9B model typically does ~3-4 minutes per beat (lore + narrate + evaluate = 3 LLM calls per beat, plus tool calls). Tips:

- Use `autonomous` mode to avoid pause overhead
- Reduce number of beats for testing
- Use a faster model for evaluator/orchestrator/lore roles
