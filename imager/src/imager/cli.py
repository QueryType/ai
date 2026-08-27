#!/usr/bin/env python3
"""
imager: story-to-images pipeline.

Reads a story/essay text file (of any length), builds a story bible
(characters, settings, global style) via chunked map-reduce LLM passes,
selects illustration points guided by the story's own structure, composes
consistent positive/negative prompts, and fires each prompt at a ComfyUI
instance, saving story-ordered images. Resumable at every stage, and at
per-image granularity during generation.

Usage:
    python -m imager.cli STORY.txt --workflow-file WORKFLOW_API.json \\
        --llm-url http://localhost:8080/v1 --llm-model my-local-model \\
        --comfy-url http://127.0.0.1:8188 --out-dir ./output

Requires: pip install requests
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv

from .config import STAGES, RunConfig
from .pipeline import run_pipeline
from .prompt_gen import MODEL_FAMILY_STYLES, PROMPT_STYLES

load_dotenv()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("story_file", type=Path, help="Path to the story/essay text file")
    ap.add_argument(
        "--backend", choices=["comfy", "drawthings"], default=os.environ.get("IMAGER_BACKEND", "comfy"),
        help="Image generation backend for the 'images' stage (env: IMAGER_BACKEND, default comfy)",
    )
    ap.add_argument(
        "--workflow-file", type=Path,
        default=Path(os.environ["IMAGER_WORKFLOW_FILE"]) if os.environ.get("IMAGER_WORKFLOW_FILE") else None,
        help="Path to ComfyUI API-format workflow JSON. Required for --backend comfy unless --only-stage stops before 'images' (env: IMAGER_WORKFLOW_FILE)",
    )

    ap.add_argument("--llm-url", default=os.environ.get("IMAGER_LLM_URL", "http://localhost:8080/v1"), help="OpenAI-compatible base URL (env: IMAGER_LLM_URL)")
    ap.add_argument("--llm-model", default=os.environ.get("IMAGER_LLM_MODEL", "local-model"), help="Model name to send in LLM requests (env: IMAGER_LLM_MODEL)")
    ap.add_argument("--llm-api-key", default=os.environ.get("IMAGER_LLM_API_KEY", "not-needed"), help="Bearer token for the LLM endpoint's Authorization header, for hosted/authenticated OpenAI-compatible APIs (env: IMAGER_LLM_API_KEY)")
    ap.add_argument("--comfy-url", default=os.environ.get("IMAGER_COMFY_URL", "http://127.0.0.1:8188"), help="ComfyUI server base URL, used when --backend comfy (env: IMAGER_COMFY_URL)")
    ap.add_argument("--drawthings-url", default=os.environ.get("IMAGER_DRAWTHINGS_URL", "http://127.0.0.1:7860"), help="Draw Things HTTP API base URL, used when --backend drawthings -- enable 'API Server' in Draw Things Settings first (env: IMAGER_DRAWTHINGS_URL)")
    ap.add_argument("--width", type=int, default=int(os.environ["IMAGER_WIDTH"]) if os.environ.get("IMAGER_WIDTH") else None, help="Force this width for every scene, either backend (overrides --auto-orientation). Must be paired with --height (env: IMAGER_WIDTH)")
    ap.add_argument("--height", type=int, default=int(os.environ["IMAGER_HEIGHT"]) if os.environ.get("IMAGER_HEIGHT") else None, help="Force this height for every scene, either backend (overrides --auto-orientation). Must be paired with --width (env: IMAGER_HEIGHT)")
    ap.add_argument(
        "--auto-orientation", dest="auto_orientation", action="store_true", default=True,
        help="Size each scene's image from its LLM-classified orientation (portrait/landscape/square, "
             f"see ORIENTATION_SIZES in config.py) -- either backend. On by default; ignored if "
             "--width/--height are set. Pass --no-auto-orientation to leave size unspecified instead "
             "(workflow default for comfy, current UI setting for drawthings).",
    )
    ap.add_argument("--no-auto-orientation", dest="auto_orientation", action="store_false", help="Disable per-scene orientation sizing.")

    ap.add_argument("--chunk-budget-chars", type=int, default=int(os.environ.get("IMAGER_CHUNK_BUDGET_CHARS", 6000)), help="Approx max chars per chunk for LLM passes over large stories (env: IMAGER_CHUNK_BUDGET_CHARS)")
    ap.add_argument("--parallel", type=int, default=int(os.environ.get("IMAGER_PARALLEL", 4)), help="Concurrent LLM calls during bible/scenes stages, match your LLM server's slot count (env: IMAGER_PARALLEL)")
    ap.add_argument("--num-scenes", type=int, default=None, help="Cap/target scene count; omit to let the LLM decide based on story structure")

    ap.add_argument(
        "--model-family", choices=sorted(MODEL_FAMILY_STYLES), default=None,
        help=f"Sets --prompt-style from a known checkpoint family (env: IMAGER_MODEL_FAMILY). "
             f"Mapping: {MODEL_FAMILY_STYLES}",
    )
    ap.add_argument(
        "--prompt-style", choices=PROMPT_STYLES, default=None,
        help="Overrides --model-family directly: 'prose' (natural-language sentences, no negative "
             "prompt -- FLUX.2/Z-Image) or 'tags' (comma-separated keyword formula + negative prompt "
             "-- SDXL-family). Default 'prose' if neither is given (env: IMAGER_PROMPT_STYLE).",
    )
    ap.add_argument("--negative-prompt", default="", help="Global negative prompt appended to every scene's negative prompt (tags style only; ignored for prose style)")
    ap.add_argument(
        "--enhance-prompts", dest="enhance_prompts", action="store_true", default=True,
        help="LLM-enhance each scene's action sentence (lighting, composition, atmosphere) before "
             "composing the final prompt, using --llm-url/--llm-model. Fixed character/setting "
             "descriptors and style suffix are never touched, so cross-image consistency is unaffected. "
             "On by default; pass --no-enhance-prompts to skip.",
    )
    ap.add_argument(
        "--no-enhance-prompts", dest="enhance_prompts", action="store_false",
        help="Skip LLM prompt enhancement; compose prompts from the raw scene description.",
    )
    ap.add_argument("--prompt-node-id", default=None, help="Workflow node id for positive prompt (auto-detected if omitted)")
    ap.add_argument("--neg-prompt-node-id", default=None, help="Workflow node id for negative prompt (auto-detected if omitted)")

    ap.add_argument("--seed", type=int, default=None, help="Seed applied to all scenes (best-effort node patch)")
    ap.add_argument("--steps", type=int, default=None, help="Sampling steps applied to all scenes (best-effort node patch)")
    ap.add_argument("--cfg-scale", type=float, default=None, help="CFG scale applied to all scenes (best-effort node patch)")

    ap.add_argument("--out-dir", type=Path, default=Path("./output"), help="Directory for manifest, stage artifacts, and images")
    ap.add_argument("--force", action="store_true", help="Ignore manifest state and rerun every stage")
    ap.add_argument("--force-from", choices=STAGES, default=None, help="Rerun from this stage forward")
    ap.add_argument("--only-stage", choices=STAGES, default=None, help="Run stages up to and including this one, then stop")

    args = ap.parse_args()

    if args.backend == "comfy" and (args.only_stage is None or STAGES.index(args.only_stage) >= STAGES.index("images")):
        if args.workflow_file is None:
            ap.error("--workflow-file is required for --backend comfy unless --only-stage stops before 'images'")

    if (args.width is None) != (args.height is None):
        ap.error("--width and --height must be given together")

    prompt_style = (
        args.prompt_style
        or os.environ.get("IMAGER_PROMPT_STYLE")
        or MODEL_FAMILY_STYLES.get(args.model_family or os.environ.get("IMAGER_MODEL_FAMILY", ""))
        or "prose"
    )
    if prompt_style not in PROMPT_STYLES:
        ap.error(f"resolved --prompt-style {prompt_style!r} is not one of {PROMPT_STYLES}")

    config = RunConfig(
        story_file=args.story_file,
        workflow_file=args.workflow_file,
        out_dir=args.out_dir,
        llm_url=args.llm_url,
        llm_model=args.llm_model,
        llm_api_key=args.llm_api_key,
        backend=args.backend,
        comfy_url=args.comfy_url,
        drawthings_url=args.drawthings_url,
        width=args.width,
        height=args.height,
        auto_orientation=args.auto_orientation,
        chunk_budget_chars=args.chunk_budget_chars,
        parallel_chunks=args.parallel,
        num_scenes=args.num_scenes,
        negative_prompt=args.negative_prompt,
        prompt_style=prompt_style,
        enhance_prompts=args.enhance_prompts,
        prompt_node_id=args.prompt_node_id,
        neg_prompt_node_id=args.neg_prompt_node_id,
        seed=args.seed,
        steps=args.steps,
        cfg_scale=args.cfg_scale,
        force=args.force,
        force_from=args.force_from,
        only_stage=args.only_stage,
    )
    run_pipeline(config)


if __name__ == "__main__":
    main()
