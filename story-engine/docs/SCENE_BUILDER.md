# Scene Builder — User Guide

An interactive CLI that interviews you about your story and generates a complete,
ready-to-run scene input file (`.md`) for the Story Engine.

---

## Quick Start

```bash
conda activate strandsagents
cd /Volumes/d/code/aiml/story-engine
python my_code/scene_builder.py
```

The builder walks you through 8 questions, calls your configured model once to
generate the scene structure, lets you review and edit the result, then writes
the `.md` file.

---

## Configuration

Add these to your `.env` (all optional — the builder falls back to existing
story engine variables if they're not set):

```env
# Which endpoint to use for generation (defaults to STORY_ENGINE_LOCAL_BASE_URL)
SCENE_BUILDER_BASE_URL=http://192.168.1.5:8081/v1

# Which model to use (defaults to STORY_ENGINE_EVALUATOR_MODEL, then NARRATOR_MODEL)
SCENE_BUILDER_MODEL=qwen3.5-9b-uncensored-hauhaucs-aggressive

# API key — "none" is fine for local servers
SCENE_BUILDER_API_KEY=none

# Color theme: dark | light | system  (system = no ANSI colors)
SCENE_BUILDER_THEME=dark
```

**Model recommendation:** Use your fast 9B on port 8081 — the generation call is
a single structured JSON request, not prose writing. No need for the 31B narrator.

---

## Command Line Options

```bash
# Fresh build — walks through interview, generates structure from scratch
python my_code/scene_builder.py

# Pre-specify the output path (skips that prompt)
python my_code/scene_builder.py --out output/my_scene.md

# Load and edit an existing scene file (skips the interview entirely)
python my_code/scene_builder.py --load path/to/existing_scene.md
python my_code/scene_builder.py --load path/to/existing_scene.md --out path/to/new_output.md

# Write a blank template with hints for manual authoring (no LLM, no interview)
python my_code/scene_builder.py --template                        # saves to output/blank_scene.md
python my_code/scene_builder.py --template path/to/my_scene.md   # saves to specified path

# Set color theme (dark / light / system)
python my_code/scene_builder.py --theme dark
python my_code/scene_builder.py --theme light
python my_code/scene_builder.py --theme system   # no ANSI colors
```

---

## The Interview (8 Questions)

The builder asks one question at a time. Press **Enter** to accept any default
shown in `[brackets]`.

| # | What it asks | What to provide |
|---|---|---|
| Q1 | Scene title and output path | Any title; path defaults to `output/<title_slug>.md` |
| Q2 | Genre, tone, themes | Genre, emotional register, core themes, stylistic references |
| Q3 | World — where, when, rules | Location, time/season, 2-3 constraints, cultural details |
| Q4 | Characters | One per prompt — name, age, role, appearance, personality, backstory. Type `done` when finished |
| Q5 | Scenario | What's happening as the scene opens, what tension is already active |
| Q6 | Target length | `short` (~1500w) / `medium` (~3500w) / `long` (~6000w) / `epic` (~9000w) |
| Q7 | Point of view | `third-person` / `third-person-limited` / `first-person` / `second-person` |
| Q8 | Execution mode | `autonomous` / `semi-interactive` / `interactive` (see Mode Reference below) |

**Character roles** (Q4): when describing each character, mention their role —
`player-character`, `npc`, `antagonist`, or `neutral`. The builder infers it if
you don't say it explicitly, but being explicit helps.

---

## Review Steps

After the interview (fresh build) or after loading a file (`--load`), the builder
walks you through three review steps before writing anything. In fresh-build mode,
the LLM generates the full structure first; in load mode the existing content is used.

### Step 1 — Beat Arc Review

The proposed beats are shown as a numbered list. You can edit freely:

| Command | What it does |
|---|---|
| `ok` | Accept beats as-is and continue |
| `rewrite N <description>` | **LLM rewrites beat N** based on your direction — shows result for confirm/discard |
| `extend <description>` | **LLM generates more beats** continuing the story — you choose how many, then confirm/discard |
| `edit N <new text>` | Manually replace beat N's instruction (no LLM) |
| `title N <new title>` | Rename beat N |
| `pause N` | Toggle a `[pause]` marker on beat N |
| `add <instruction>` | Append a beat manually |
| `remove N` | Delete beat N |
| `swap N M` | Swap the positions of beats N and M |

Beat count limits: **minimum 3, maximum 10** (the `extend` command enforces this).

**`rewrite` example:**
```
> rewrite 2 The confrontation should have more dark humour — Lyra should be sarcastic
  Rewriting beat — please wait...
  Rewritten beat 2:
    Title: THE THRESHOLD
    ...
  Accept? [yes] / 'no' to discard:
```

**`extend` example:**
```
> extend After they enter the ruins, they find evidence of a recent camp — someone else was here
  How many beats to add? (max 7)  [2]
> 2
  Generating 2 new beat(s) — please wait...
  6. THE COLD CAMP — ...
  7. SIGNS OF FLIGHT — ...
  Append these? [yes] / 'no' to discard:
```

If mode is `semi-interactive` and you haven't set any `[pause]` markers, the
builder will remind you and offer to add them.

### Step 2 — Narrator Voice & Style

Shows the generated narrator prompt and writing style. Press **Enter** to keep
them, or describe what to change and then type the replacement text.

### Step 3 — Character Triggers

Shows the trigger keyword list for each character. These are the keywords the
lore injector scans for in beat text — if a keyword matches, that character's
full card is injected into the narrator's context for that beat.

Review them carefully: **if a trigger is missing, the character card won't fire
and the narrator writes without knowing who they are.**

Examples of what good triggers look like:
```
Kavi, father, the old man, shepherd, weathered hands, he, him, Thapa
Maya, daughter, the girl, student, she, her, Maya Thapa
```

Press **Enter** to keep, or type a new comma-separated list to replace.

---

## Blank Template (Manual Authoring)

If you prefer to write a scene file by hand rather than through the interview,
use `--template` to get a pre-structured file with hints in every field:

```bash
python my_code/scene_builder.py --template output/my_scene.md
```

The file contains every required section with `<<PLACEHOLDER>>` text showing
exactly what to put there, including examples drawn from the Ashenveil scene.
Top-level `#` comment lines explain valid options for enum fields (mode, pov, etc.).

**Workflow:**
1. Run `--template` to generate the file
2. Open it in your editor, replace every `<<...>>` field
3. Run directly: `python -m my_code output/my_scene.md`
4. Or load it back into the builder for LLM-assisted beat editing:
   `python my_code/scene_builder.py --load output/my_scene.md`

---

## Loading an Existing Scene File

Use `--load` to open an existing scene file for editing instead of starting from
scratch. The builder parses and validates the file, then drops you directly into
the beat arc review. The interview is skipped entirely.

```bash
python my_code/scene_builder.py --load /Volumes/d/code/aiml/ai/strs/sidh/journey_scene1.md
```

**What gets validated on load:**

The file must be a valid Story Engine scene file with all required sections:
`[meta]`, `[narrator-prompt]`, `[writing-style]`, `[world-info]`, `[scenario]`,
`[scene-beats]`, and at least one `[character-N]`.

If any required section or field is missing, the builder prints the specific
error and exits — the file is never silently accepted in a broken state.

**What happens after loading:**

The same three review steps run as in a fresh build:
1. **Beat arc review** — edit, rewrite, extend beats as needed
2. **Narrator voice & style** — review and optionally update
3. **Character triggers** — review and optionally update

**Output path on load:**

By default the builder asks whether to overwrite the source file or save to a
new path. Use `--out` to pre-specify:
```bash
# Save edits to a new file, leave the original untouched
python my_code/scene_builder.py --load journey_scene1.md --out journey_scene1_v2.md
```

---

## Validation

Before writing the file, the builder runs a validation check. If anything is
wrong, **all errors are printed and the file is not written.**

What it checks:

| Check | Rule |
|---|---|
| Title, output path, scenario | Must not be empty |
| Genre/tone, world description | Must not be empty |
| Characters | At least one required |
| `pov` | Must be a valid value |
| `mode` | Must be a valid value |
| Generated JSON completeness | All 8 sections must be present and non-empty |
| `scene_setup` | Must have location, time, atmosphere |
| Each character | Must have name, role, triggers, description, personality |
| Character role | Must be `player-character`, `npc`, `antagonist`, or `neutral` |
| Character triggers | Must have at least 2 entries |
| Beat count | 3–10 beats |
| Each beat | Must have a title and a non-trivial instruction (≥ 10 words) |
| `world_info` length | Must be under 300 words |

If validation fails, fix the reported issues and re-run. The most common cause
of generated-JSON failures is a weaker model not following the JSON schema —
set `SCENE_BUILDER_MODEL` to a more capable model if this happens.

---

## Output File Format

The written `.md` file contains all the sections the Story Engine requires:

```
[meta]            — title, mode, output path, pov, target length, etc.
[narrator-prompt] — narrator identity and control rules
[writing-style]   — prose rhythm, dialogue format, sensory focus
[author-note]     — thematic reminder injected every N beats
[world-info]      — lore injected into every beat
[character-N]     — one block per character (name, triggers, description, etc.)
[scene-setup]     — location, time, atmosphere
[scenario]        — inciting situation, read once at scene start
[scene-beats]     — numbered beat instructions, with optional [pause] markers
[writing-instructions] — scene-specific creative direction for the narrator
```

See `docs/USER_GUIDE.md` → §4 for the full field reference.

---

## Mode Reference

| Mode | Behaviour |
|---|---|
| `autonomous` | Runs all beats to completion with no pauses |
| `semi-interactive` | Pauses only at beats marked with `[pause]` |
| `interactive` | Pauses after every beat for human input |

At a pause, you can: press **Enter** to continue, type `/retry` to regenerate
the beat, type `/skip` to skip it, type `/stop` to save and exit, or type any
free text to redirect the narrator and regenerate.

---

## Running the Generated Scene

```bash
conda activate strandsagents
python -m my_code output/your_scene.md
```

Make sure your `.env` has the narrator and evaluator endpoints configured. See
`docs/USER_GUIDE.md` → §2 for the full `.env` reference.
