# Usage

## Running via .env (recommended)

Copy `.env.example` to `.env` in the repo root (or wherever you run the CLI
from) and fill in your endpoints. `python-dotenv` loads it automatically —
no flags needed. Every setting below has a CLI flag equivalent; an explicit
flag always overrides the `.env` value, which in turn overrides the CLI's
built-in default.

| `.env` var | CLI flag | Meaning |
|---|---|---|
| `IMAGER_LLM_URL` | `--llm-url` | OpenAI-compatible base URL (default `http://localhost:8080/v1`) |
| `IMAGER_LLM_MODEL` | `--llm-model` | Model name sent in LLM requests (default `local-model`) |
| `IMAGER_LMS_MODEL_KEY` | — | LM Studio's `lms load`/`lms unload` key, if it differs from `IMAGER_LLM_MODEL` (check with `lms ls`). Only used by `scripts/run_full_pipeline.sh`. |
| `IMAGER_BACKEND` | `--backend` | Image backend for the `images` stage: `comfy` \| `drawthings` (default `comfy`) |
| `IMAGER_COMFY_URL` | `--comfy-url` | ComfyUI server base URL (default `http://127.0.0.1:8188`), used when `--backend comfy` |
| `IMAGER_WORKFLOW_FILE` | `--workflow-file` | ComfyUI API-format workflow JSON, required when `--backend comfy` |
| `IMAGER_DRAWTHINGS_URL` | `--drawthings-url` | Draw Things HTTP API base URL (default `http://127.0.0.1:7860`), used when `--backend drawthings` |
| `IMAGER_WIDTH` / `IMAGER_HEIGHT` | `--width` / `--height` | Image size, `--backend drawthings` only; unset (default) uses whatever's currently configured in the Draw Things UI. comfy's size lives in the workflow file |
| `IMAGER_MODEL_FAMILY` | `--model-family` | Known checkpoint family (`flux2`, `zimage` → prose; `sdxl` → tags); sets `--prompt-style` |
| `IMAGER_PROMPT_STYLE` | `--prompt-style` | Overrides `--model-family` directly (`prose`\|`tags`); default `prose` if neither is set |
| `IMAGER_CHUNK_BUDGET_CHARS` | `--chunk-budget-chars` | Approx max chars per chunk for `bible`/`scenes` LLM passes (default `6000`) |
| `IMAGER_PARALLEL` | `--parallel` | Concurrent LLM calls during `bible`/`scenes`/`--enhance-prompts` (default `4`) |

With all of these set, the CLI invocation is just the story file:

```bash
cd src && python -m imager.cli ../story.txt --out-dir ../output
```

Flags with no `.env` equivalent (`--num-scenes`, `--negative-prompt`,
`--enhance-prompts`, `--seed`, `--force`, ...) are per-run choices — see
[CLI reference](#cli-reference) below.

## Running

The package lives under `src/imager/` and isn't installed, so either run
from `src/` or put `src/` on `PYTHONPATH`:

```bash
cd src
python -m imager.cli STORY.txt --out-dir ./output
```

or

```bash
PYTHONPATH=src python -m imager.cli STORY.txt --out-dir ./output
```

If `IMAGER_WORKFLOW_FILE` isn't set in `.env`, pass `--workflow-file
WORKFLOW_API.json` explicitly — a ComfyUI workflow exported in **API
format** (ComfyUI menu → "Save (API Format)"). Required for `--backend comfy`
(the default) unless `--only-stage` stops before the `images` stage.

### Using Draw Things instead of ComfyUI

Pass `--backend drawthings` (or set `IMAGER_BACKEND=drawthings`). Draw
Things (the macOS app) needs its HTTP API turned on first: open Draw
Things → Settings (gear icon) → enable **"API Server"** (default port
`7860`, matching `IMAGER_DRAWTHINGS_URL`'s default). No workflow file is
needed — Draw Things uses whichever checkpoint/sampler/LoRA is currently
selected in the app's UI, so set those there before running. `--width`/
`--height` control output size (`--workflow-file`, `--prompt-node-id`,
`--neg-prompt-node-id` are ComfyUI-only and ignored).

## Running with one GPU service at a time (LLM + ComfyUI)

If your hardware can only comfortably hold one model's worth of VRAM,
`scripts/run_full_pipeline.sh` automates the handoff instead of requiring
you to manually stop/start LM Studio and ComfyUI between phases. Both
server *processes* stay running throughout — only which one is actually
holding VRAM gets toggled, via two APIs that don't require a restart:

- **LM Studio**: `lms load <key>` / `lms unload --all` (the local `lms` CLI
  — works even when LM Studio is on a LAN IP rather than localhost, since
  it's still the same machine). The `lms load` key can differ from the
  OpenAI-API model name; check with `lms ls` and set `IMAGER_LMS_MODEL_KEY`
  in `.env` accordingly.
- **ComfyUI**: `POST /free` with body
  `{"unload_models": true, "free_memory": true}` moves the model back to
  RAM without touching the server process.

```bash
./scripts/run_full_pipeline.sh STORY.txt --out-dir ./output [other imager.cli flags...]
```

Sequence: free ComfyUI VRAM (in case it's holding anything) → `lms load`
→ run chunk/bible/scenes/prompts → `lms unload --all` → run the images
stage (ComfyUI loads its own model on the first submitted workflow, no
explicit load call needed) → free ComfyUI VRAM again.

## The pipeline stages

Running the CLI executes five stages in order. Each stage writes an artifact
to `--out-dir` and records its status in `manifest.json`. On any rerun,
a stage is skipped and its artifact reused if its inputs haven't changed;
otherwise it (and everything after it) reruns automatically.

| Stage    | Output            | What happens |
|----------|-------------------|--------------|
| `chunk`  | `chunks.json`     | Story text is split into ordered, budget-sized chunks on paragraph boundaries. |
| `bible`  | `story_bible.json`| Each chunk is summarized (characters seen, settings, visual motifs), then merged into one story bible: synopsis, tone, a fixed appearance sentence per character, a fixed description per setting, one global art-style suffix, and default negative-prompt terms. |
| `scenes` | `scenes.json`     | Each chunk is re-examined (with the bible as context) for strong illustration moments. Candidates are merged in story order and, only if `--num-scenes` was given, trimmed to that count by importance. |
| `prompts`| `prompts.json`    | For each scene, the final positive prompt (scene description + fixed character/setting descriptors + style suffix) and negative prompt (bible defaults + `--negative-prompt`) are composed. Pure string assembly, so a character/setting reads identically every time it recurs — the scene description itself is LLM-enhanced first by default, see below. |
| `images` | `<id>_<slug>.png` | Each prompt is injected into a copy of the ComfyUI workflow and submitted; results are downloaded with story-ordered filenames. Tracked per-scene in the manifest so a rerun only retries scenes that aren't done. |

Use `--only-stage STAGE` to run up through a given stage and stop — e.g.
`--only-stage prompts` generates and inspects `prompts.json` without
touching ComfyUI at all (no `--workflow-file` needed in that case).

### `--enhance-prompts` (on by default; `--no-enhance-prompts` to skip)

Before composing each scene's prompt, sends *only* the scene's action/mood
sentence — never the story bible's fixed character/setting descriptors or
style suffix — through an LLM call (`--llm-url`/`--llm-model`, the same
endpoint as `bible`/`scenes`) to enrich it with cinematic lighting,
composition, and atmosphere detail, style-aware (`prose` vs `tags`).

This exists because a bare scene description with no framing/lighting
direction tends to produce flatter, more generic renders; asking the LLM to
add cinematographic detail measurably improves output quality (validated by
A/B image comparison against the un-enhanced prompt on identical
generation settings). Scoping the rewrite to just the action sentence keeps
the fixed character/setting text byte-identical across every scene it
appears in, so cross-image consistency is unaffected — only the
scene-specific framing changes.

If a scene has 2+ named characters, the enhancement is additionally told to
keep all of them visibly in frame; without this, the push toward tight
cinematic close-ups tends to crop a second character out of the shot.

On by default; pass `--no-enhance-prompts` to compose from the raw scene
description instead. Runs scenes concurrently (`--parallel`). Toggling it,
or changing `--llm-url`/`--llm-model`, invalidates the cached `prompts` stage.

Negative prompts are never enhanced — they're a no-op on `prose`-style
models (cfg=1/guidance=0), and `tags`-style (SDXL) negative defaults are
left as-is.

## CLI reference

```
python -m imager.cli STORY_FILE [options]
```

**Required**
- `STORY_FILE` — path to the story/essay text file.
- `--workflow-file PATH` (env `IMAGER_WORKFLOW_FILE`) — ComfyUI API-format
  workflow JSON. Required unless `--only-stage` stops before the `images`
  stage.

**LLM / ComfyUI endpoints** — see the [`.env` table](#running-via-env-recommended) above.
- `--llm-url URL`, `--llm-model NAME`, `--comfy-url URL`

**Chunking & scene selection**
- `--chunk-budget-chars N` (env `IMAGER_CHUNK_BUDGET_CHARS`, default `6000`)
  — lower for small-context local models; raise to reduce LLM calls on long
  stories.
- `--parallel N` (env `IMAGER_PARALLEL`, default `4`) — concurrent LLM calls
  during `bible`/`scenes`/`--enhance-prompts`. Match your LLM server's
  parallel slot count — e.g. a `llama-server` running with 1 slot needs
  `--parallel 1` here too, or requests just queue with no speedup.
- `--num-scenes N` (default: unset) — cap/target scene count. If omitted,
  the LLM decides how many illustration points make sense per section,
  based on how visually rich that section is. If set and more grounded
  candidates exist than `N`, the lowest-importance ones are dropped. The
  pipeline never invents ungrounded scenes to pad up to `N` — if fewer than
  `N` grounded moments exist, you'll get fewer and a note is printed.

**Prompts**
- `--model-family {flux2,zimage,sdxl}` (env `IMAGER_MODEL_FAMILY`) — sets
  `--prompt-style` from a known checkpoint family.
- `--prompt-style {prose,tags}` (env `IMAGER_PROMPT_STYLE`) — overrides
  `--model-family` directly. `prose`: natural-language sentences, no
  negative prompt (FLUX.2/Z-Image). `tags`: comma-separated keyword formula
  plus negative prompt (SDXL-family). Default `prose` if neither is given.
- `--negative-prompt TEXT` — appended to every scene's negative prompt,
  after the story bible's own negative defaults. `tags` style only.
- `--enhance-prompts` / `--no-enhance-prompts` — see [above](#--enhance-prompts-on-by-default---no-enhance-prompts-to-skip).
- `--prompt-node-id ID` / `--neg-prompt-node-id ID` — override auto-detection
  of the ComfyUI `CLIPTextEncode` nodes to inject the positive/negative text
  into. Auto-detection looks for a node titled "positive"/"pos" (or
  "negative"/"neg" for the negative node); if it can't confidently pick one,
  it warns and falls back to a best guess (or skips negative injection
  entirely if there's genuine ambiguity).

**Generation params** (best-effort: applied to any workflow node whose
`inputs` has a matching key; silently skipped if no such node exists)
- `--seed N`
- `--steps N`
- `--cfg-scale F`

**Output & resume control**
- `--out-dir PATH` (default `./output`) — where `manifest.json` and all
  stage artifacts/images are written.
- `--force` — ignore all cached stage state and rerun everything.
- `--force-from {chunk,bible,scenes,prompts,images}` — rerun from this
  stage forward, keeping earlier stages' cached output.
- `--only-stage {chunk,bible,scenes,prompts,images}` — run through this
  stage and stop.

## Resuming after a crash or Ctrl-C

Just rerun the exact same command. The manifest remembers what's done:

- If `chunk`/`bible`/`scenes`/`prompts` already completed with the same
  relevant config, they're skipped and their JSON artifacts reloaded from
  disk.
- If you were partway through `images`, only scenes not marked `done` in
  the manifest are retried — already-downloaded images are left alone.
- If a scene's image generation failed (ComfyUI error, timeout), it's
  marked `failed` and retried on the next run automatically.

To force specific stages to rerun instead of relying on auto-invalidation,
use `--force-from`. For example, after hand-editing `story_bible.json` to
fix a character description, rerun with `--force-from scenes` to regenerate
scene selection, prompts, and images using your edits — `chunk` and `bible`
stay untouched.

Changing a flag that affects a given stage (e.g. `--chunk-budget-chars`,
`--num-scenes`, `--negative-prompt`, `--enhance-prompts`, `--seed`)
automatically invalidates that stage and everything downstream of it — no
`--force` needed.

## Editing intermediate artifacts by hand

Every stage artifact is plain JSON in `--out-dir` and is safe to hand-edit
between runs, as long as you follow it with `--force-from` at that stage (so
the pipeline doesn't overwrite your edit on the next run because the config
hash still matched):

- `story_bible.json` — fix a character's `fixed_appearance` or the
  `global_style.descriptor_suffix`, then `--force-from scenes`.
- `scenes.json` — remove/reorder/hand-add scene entries (each needs `id`,
  `description`, `characters_present`, `settings_present`, `anchor`), then
  `--force-from prompts`.
- `prompts.json` — hand-tune a specific `prompt`/`negative_prompt`/`seed`,
  then `--force-from images` (or just rerun as-is — `images` reads
  `prompts.json` directly and only regenerates scenes not yet `done`).

## Output files

```
output/
  manifest.json       # stage status, input hashes, per-scene image status
  chunks.json          # ordered story chunks
  story_bible.json     # characters, settings, global style, negative defaults
  scenes.json          # selected illustration points, story-ordered
  prompts.json         # final positive/negative prompts per scene
  images/
    001_<slug>.png       # generated images, story-ordered filenames
    002_<slug>.png
    ...
  story.html            # optional, see "Rendering a readable HTML page" below
```

## Rendering a readable HTML page

Once a run has some images, turn it into a single illustrated page --
the full story text with each scene's image placed inline at the point it
illustrates -- with:

```bash
python -m imager.render OUT_DIR [--title "Story Title"] [-o output.html] [--embed-images]
```

This only reads what's already in `OUT_DIR` (`chunks.json`, `scenes.json`,
`story_bible.json`, `images/`) -- no LLM or image-backend calls, so it's
cheap to rerun any time, including partway through a run (scenes without a
matching image yet are just rendered as text). Default output is
`OUT_DIR/story.html`, referencing images at their relative `images/...`
path so the HTML stays lightweight next to them. `--embed-images` inlines
every image as base64 instead, for a single portable file -- declined
automatically (falling back to relative links, with a note printed) if the
images add up to more than 20MB, since embedding a long story's worth of
images produces an unwieldy file.
