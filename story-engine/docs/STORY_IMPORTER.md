# Story Importer — User Guide

Converts any prose `.txt` file into a ready-to-run Story Engine scene `.md`.

Point it at a short story, a chapter excerpt, or a scene draft. The importer
reads the prose, calls your configured LLM to extract characters, world-building,
beats, and narrative structure, then writes a complete input file you can run
immediately or edit further with the Scene Builder.

---

## Quick Start

```bash
conda activate strandsagents
python -m my_code.story_importer my_story.txt
```

The importer extracts structure, shows you a summary, asks for confirmation,
and writes `output/<story-slug>.md`.

---

## Configuration

The importer uses the same `.env` as the rest of the engine, with its own
optional override variables. Fallback chain for each setting:

```
STORY_IMPORTER_*  →  SCENE_BUILDER_*  →  STORY_ENGINE_*
```

```env
# Which endpoint to use (defaults to SCENE_BUILDER_BASE_URL, then STORY_ENGINE_LOCAL_BASE_URL)
STORY_IMPORTER_BASE_URL=http://192.168.1.5:8081/v1

# Which model to use (defaults down the chain to STORY_ENGINE_NARRATOR_MODEL)
STORY_IMPORTER_MODEL=qwen3.5-9b-uncensored-hauhaucs-aggressive

# API key — "none" is fine for local servers
STORY_IMPORTER_API_KEY=none

# Hard word-count limit before refusing the file (default: 6000)
STORY_IMPORTER_MAX_WORDS=6000

# Warn-but-proceed threshold (default: 4000)
STORY_IMPORTER_WARN_WORDS=4000
```

**Model recommendation:** The importer makes one structured JSON extraction call —
a single-pass operation that does not require prose quality. Your fast 9B on
port 8081 is sufficient. The 31B narrator is unnecessary.

---

## Command Line Reference

```bash
python -m my_code.story_importer STORY.TXT [options]
```

| Option | Default | Description |
|--------|---------|-------------|
| `STORY.TXT` | *(required)* | Path to the prose `.txt` file to import |
| `--out PATH` | `output/<slug>.md` | Output path for the generated scene file |
| `--imagination 0-100` | `50` | Invention level — see [Imagination Level](#imagination-level) |
| `--beats N` | auto | Number of scene beats to produce (3–10) |
| `--pov POV` | inferred | Override point of view (`third-person`, `first-person`, `second-person`, `third-person-limited`) |
| `--mode MODE` | `autonomous` | Execution mode (`autonomous`, `semi-interactive`, `interactive`) |
| `--nsfw` | off | Mark the generated scene as NSFW |
| `--theme THEME` | env | Terminal colour theme (`dark`, `light`, `system`) |
| `--yes` / `-y` | off | Skip the confirmation prompt and write immediately |

**Examples:**

```bash
# Import with defaults — balanced extraction, auto beat count
python -m my_code.story_importer drafts/chapter_one.txt

# Strict extraction only — nothing invented beyond what's in the text
python -m my_code.story_importer drafts/chapter_one.txt --imagination 0

# Free invention — use the story as a springboard, fill everything else
python -m my_code.story_importer drafts/chapter_one.txt --imagination 100 --beats 8

# Specify output and skip confirmation
python -m my_code.story_importer scene_draft.txt --out output/scene_v1.md --yes

# Override POV inferred from the prose
python -m my_code.story_importer story.txt --pov first-person
```

---

## Imagination Level

The `--imagination` flag (0–100) controls how much the LLM invents versus
extracting strictly from the source text.

| Range | Label | Behaviour |
|-------|-------|-----------|
| 0–20 | **strict** | Extract only what is explicitly in the prose. Missing fields get minimal placeholders — nothing is invented. |
| 21–79 | **balanced** *(default: 50)* | Extract explicit details and infer strongly implied ones. Fills gaps where context supports a credible inference. |
| 80–100 | **free** | Extract explicit, infer implied, and freely invent the rest. Treats the source as a creative springboard. |

**What the level affects:**

- **Characters** — strict: only traits stated in the text. Free: full backstory, speech patterns, and motivation invented from tone and context.
- **World-info** — strict: only setting details that appear. Free: builds out a coherent world from hints in the prose.
- **Beats** — strict: maps directly to events in the story. Free: may create beats for implied or anticipated story moments.
- **Writing style / narrator prompt** — strict: mirrors the source prose's actual voice. Free: fully articulated and potentially enhanced.

**When to use each:**

- **strict** — adapting finished prose; you want the engine to re-tell the story faithfully.
- **balanced** — adapting a draft or outline; some gaps are fine to fill intelligently.
- **free** — using a story as inspiration; you want the engine to take it somewhere new.

---

## Beat Count

`--beats N` sets the target number of scene beats (3–10).

If not specified, the beat count is chosen automatically from the source word count:

| Source length | Auto beats |
|--------------|-----------|
| < 1,000 words | 3 |
| 1,000–2,499 words | 4 |
| 2,500–3,999 words | 5 |
| 4,000+ words | min(10, word_count ÷ 1000) |

---

## What Gets Extracted

The importer produces the full set of sections required by the Story Engine:

| Section | What the LLM produces |
|---------|----------------------|
| `[meta]` | title (inferred/invented), pov (inferred), target_length (estimated) |
| `[narrator-prompt]` | narrator identity, tense, POV control rules |
| `[writing-style]` | sentence rhythm, dialogue format, sensory emphasis |
| `[author-note]` | one persistent thematic reminder |
| `[world-info]` | ≤ 300 words of setting and lore |
| `[character-N]` | one block per named/distinct character — name, role, triggers, description, personality, backstory, speech_style |
| `[scene-setup]` | location, time, atmosphere |
| `[scenario]` | 2–4 paragraphs orienting the narrator to the scene opening |
| `[scene-beats]` | N beats with evocative all-caps titles and directional instructions |
| `[writing-instructions]` | scene-specific creative direction |

`[meta]` fields not inferred from the prose (`mode`, `nsfw`, `output_file`) are
set from CLI arguments.

---

## Output Summary

Before writing, the importer prints a summary for review:

```
════════════════════════════════════════════════════════════════
  EXTRACTION RESULT
════════════════════════════════════════════════════════════════
  Title        The Ruins of Ashenveil
  POV          third-person
  Target len   3500 words
  Characters   Lyra Voss (player-character), Brother Aldric (npc)
  Beats        5
  World-info   187 words
  Imagination  50 (balanced)
  Source words 1,842
  Output       output/ashenveil_scene1.md

  Beats:
    1. THE APPROACH
       Lyra watches Aldric from her cover in the treeline. Establish the
       atmosphere — fog, smell, the wrongness of this place.
    2. THE CONFRONTATION
       ...
```

If validation finds problems (e.g. character triggers too short, world-info over
300 words), they are printed before the confirmation prompt. You can choose to
write anyway or abort and adjust with `--imagination` or a different model.

---

## File Size Limits

The importer uses a **single-pass** extraction strategy: the full story text is
sent in one LLM call. This works well for stories up to ~6,000 words.

| Threshold | Behaviour |
|-----------|-----------|
| ≤ `STORY_IMPORTER_WARN_WORDS` (4,000) | Normal run |
| > 4,000 words | Warning printed, run proceeds |
| > `STORY_IMPORTER_MAX_WORDS` (6,000) | Error printed, run aborted |

```
  ERROR: Story is 14,200 words — long-story mode is not yet implemented.
  Single-pass limit: 6,000 words (STORY_IMPORTER_MAX_WORDS).
  Tip: trim the input to a single chapter or scene and re-run.
```

To import a long story today, split it into scenes and run the importer on each.
Multi-pass chunked extraction is on the roadmap — see the design spec in
`my_code/importers/chunked.py`.

---

## Workflow: Import → Edit → Run

The importer and Scene Builder are designed to work together:

```bash
# 1. Import the prose — get a first-pass scene file
python -m my_code.story_importer my_story.txt --out output/scene_draft.md

# 2. (Optional) Open in Scene Builder to refine beats, triggers, and voice
python my_code/scene_builder.py --load output/scene_draft.md

# 3. Run the scene
python -m my_code output/scene_draft.md
```

The Scene Builder's `--load` mode accepts any file the importer has written,
giving you the full beat-editing and trigger-review workflow on top of the
extracted structure.

---

## Troubleshooting

**Model returned invalid JSON**

The LLM failed to produce parseable output. Try:
- A more capable model: set `STORY_IMPORTER_MODEL` to your 31B narrator
- Simplify the input: very long or stylistically unusual prose can confuse smaller models
- Adjust `--imagination`: extreme values (0 or 100) sometimes destabilise JSON output

**World-info over 300 words**

The LLM generated too much lore. Load the file in Scene Builder (`--load`) and
trim the `[world-info]` section manually, or re-run with `--imagination 0` to
force a more conservative extraction.

**Character triggers too short**

A character has fewer than 2 trigger keywords. The importer will warn you at
the confirmation prompt. Either write anyway and fix in the file, or load in
Scene Builder → Step 3 (trigger review) to add them interactively.

**Beat instructions too short**

Beats need at least 10 words. This usually means the LLM treated a beat title
as the whole instruction. Re-run with a stronger model, or load the file in
Scene Builder and use `edit N <text>` to expand short beats.
