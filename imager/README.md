# imager

A pipeline that turns a story or essay into a set of illustrations: it reads
the text, builds a "story bible" of characters/settings/style, picks
illustration points guided by the story's own structure, composes
consistent image prompts, and generates images via ComfyUI or Draw Things.

Replaces the single-file proof-of-concept in `bootstrap/story_to_images.py`,
which only worked on short stories, had no resumability, and no
character/style consistency across scenes.

## Why

- **Large files**: stories are chunked and processed map-reduce style, so
  the pipeline isn't limited by one LLM context window.
- **Story-driven scene count**: the LLM decides how many illustration points
  make sense per section, instead of a fixed count forced across the whole
  story. `--num-scenes` is an optional cap/target, not the default driver.
- **Resumable**: every stage's output is cached and hash-invalidated; image
  generation (the expensive step) resumes per-scene after a crash or Ctrl-C.
- **Consistency**: a story bible fixes each character's/setting's visual
  description and the overall art style once; every scene prompt injects
  that exact text, so the same character reads the same way across images.
- **Prompt enhancement**: an LLM pass (on by default, `--no-enhance-prompts`
  to skip) enriches each scene's action sentence with cinematic
  lighting/composition detail before it's composed into the final prompt,
  without touching the fixed character/setting text.
- **Readable output**: `python -m imager.render OUT_DIR` turns a completed
  run into a single illustrated HTML page, images placed inline at the
  point in the text they illustrate.

## Layout

```
imager/
  bootstrap/story_to_images.py   # original single-pass proof-of-concept (kept for reference)
  src/imager/                    # the pipeline package
    cli.py               # argparse entrypoint
    config.py             # RunConfig
    manifest.py           # resumable run state
    chunking.py           # large-text splitting
    llm.py                # OpenAI-compatible chat calls, retry, JSON extraction
    story_bible.py        # map-reduce character/setting/style extraction
    scene_selection.py    # illustration-point selection
    prompt_gen.py          # consistent prompt composition (no LLM call)
    prompt_enhance.py      # optional LLM enrichment of a scene's action sentence
    comfy_client.py        # ComfyUI REST client
    drawthings_client.py   # Draw Things HTTP API client (alt. image backend)
    pipeline.py             # stage orchestration
    render.py               # renders a completed run into one illustrated HTML page
  workflows/               # ComfyUI API-format workflow JSONs
  scripts/run_full_pipeline.sh  # single-GPU LLM/ComfyUI VRAM handoff
```

## Requirements

- Python 3.9+
- `pip install -r requirements.txt` (`requests`, `python-dotenv`)
- An OpenAI-compatible LLM endpoint (e.g. `llama-server`, vLLM, LM Studio)
- A running ComfyUI or Draw Things instance with an API-format workflow
  JSON (ComfyUI) or the app's API Server enabled (Draw Things), if you're
  generating images (not required for `--only-stage` runs that stop earlier)

## Quick start

```bash
cd imager
pip install -r requirements.txt
cp .env.example .env   # fill in your LLM/ComfyUI/Draw Things endpoints
cd src && python -m imager.cli ../path/to/story.txt --out-dir ../output
```

See [USAGE.md](USAGE.md) for the `.env` reference, the full stage-by-stage
walkthrough, all CLI flags, resume/force semantics, and output file formats.
