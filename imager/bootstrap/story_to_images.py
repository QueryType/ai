#!/usr/bin/env python3
"""
story_to_images.py

Reads a story/essay text file, uses a local (OpenAI-compatible) LLM in two
passes to pick good illustration points and generate image prompts, dumps
those prompts to JSON, then fires each prompt at a ComfyUI instance over its
REST API and saves the resulting images with story-ordered filenames.

Usage:
    python story_to_images.py STORY.txt WORKFLOW_API.json \
        --llm-url http://localhost:8080/v1 \
        --llm-model my-local-model \
        --comfy-url http://127.0.0.1:8188 \
        --num-scenes 6 \
        --prompt-node-id 6 \
        --out-dir ./output

If --prompt-node-id is omitted, the script tries to auto-detect the positive
CLIPTextEncode node in the workflow (see find_positive_prompt_node).

Requires: pip install requests --break-system-packages
"""

import argparse
import copy
import json
import re
import sys
import time
import uuid
from pathlib import Path

import requests

# --------------------------------------------------------------------------
# LLM (two-pass story -> prompts)
# --------------------------------------------------------------------------

UNDERSTAND_SYSTEM_PROMPT = """You are a careful literary reader. You will be \
given a story or essay. Read it closely and produce a compact internal \
understanding of it: main characters/subjects, setting(s), tone, arc/structure, \
and any recurring visual motifs. Be concise. This summary will be used by you \
in a later step to choose illustration points, so favor concrete, visual \
detail over abstract commentary."""

SCENES_SYSTEM_PROMPT = """You are an art director choosing illustration points \
for a story. You already understand the story (summary provided). Now select \
{num_scenes} moments that would make strong standalone illustrations: visually \
distinct, spread across the story (not clustered), and each recognizable \
without needing the surrounding text.

Return ONLY a JSON array, no prose, no markdown fences. Each element:
{{
  "anchor": "a short (<15 word) quote or paraphrase marking where in the story this scene occurs",
  "prompt": "a self-contained, vivid text-to-image prompt: subject, setting, lighting, mood, composition. No character names the model won't know how to draw consistently -- describe appearance instead."
}}
"""


def call_llm(llm_url: str, model: str, system: str, user: str, api_key: str = "not-needed") -> str:
    resp = requests.post(
        f"{llm_url.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.7,
        },
        timeout=600,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def extract_json_array(text: str) -> list:
    """LLMs sometimes wrap JSON in prose or fences despite instructions."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    else:
        start, end = text.find("["), text.rfind("]")
        if start != -1 and end != -1:
            text = text[start:end + 1]
    return json.loads(text)


def generate_prompts(story_text: str, llm_url: str, model: str, num_scenes: int) -> list:
    print(f"[1/4] Pass 1: reading and understanding the story ({len(story_text)} chars)...")
    understanding = call_llm(llm_url, model, UNDERSTAND_SYSTEM_PROMPT, story_text)

    print(f"[2/4] Pass 2: selecting {num_scenes} illustration points...")
    scenes_user_msg = (
        f"Story summary you produced:\n{understanding}\n\n"
        f"Full story (for reference):\n{story_text}"
    )
    raw = call_llm(
        llm_url, model,
        SCENES_SYSTEM_PROMPT.format(num_scenes=num_scenes),
        scenes_user_msg,
    )
    try:
        scenes = extract_json_array(raw)
    except (json.JSONDecodeError, ValueError) as e:
        print("ERROR: could not parse LLM output as JSON. Raw output was:\n", raw, file=sys.stderr)
        raise SystemExit(1) from e

    for i, s in enumerate(scenes):
        if "prompt" not in s:
            raise SystemExit(f"Scene {i} missing 'prompt' field: {s}")
    return scenes


# --------------------------------------------------------------------------
# ComfyUI REST client
# --------------------------------------------------------------------------

def find_positive_prompt_node(workflow: dict) -> str:
    """Best-effort: find a CLIPTextEncode node that looks like the positive
    prompt (title contains 'positive', or -- failing that -- the first
    CLIPTextEncode node encountered). Raises if none found."""
    candidates = [
        (node_id, node) for node_id, node in workflow.items()
        if node.get("class_type") in ("CLIPTextEncode", "CLIPTextEncodeSDXL")
    ]
    if not candidates:
        raise SystemExit(
            "Could not auto-detect a prompt node (no CLIPTextEncode found). "
            "Pass --prompt-node-id explicitly."
        )
    for node_id, node in candidates:
        title = node.get("_meta", {}).get("title", "").lower()
        if "positive" in title or "pos" in title:
            return node_id
    if len(candidates) > 1:
        print(
            f"WARNING: multiple CLIPTextEncode nodes found ({[c[0] for c in candidates]}) "
            f"and none titled 'positive'. Using node {candidates[0][0]}. "
            f"Pass --prompt-node-id to override.",
            file=sys.stderr,
        )
    return candidates[0][0]


def submit_workflow(comfy_url: str, workflow: dict, client_id: str) -> str:
    resp = requests.post(
        f"{comfy_url.rstrip('/')}/prompt",
        json={"prompt": workflow, "client_id": client_id},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"ComfyUI rejected workflow: {data['error']}")
    return data["prompt_id"]


def wait_for_result(comfy_url: str, prompt_id: str, poll_interval: float = 2.0, timeout: float = 900.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = requests.get(f"{comfy_url.rstrip('/')}/history/{prompt_id}", timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if prompt_id in data:
            return data[prompt_id]
        time.sleep(poll_interval)
    raise TimeoutError(f"Timed out waiting for prompt {prompt_id}")


def download_outputs(comfy_url: str, history_entry: dict, out_dir: Path, base_filename: str) -> list:
    saved = []
    outputs = history_entry.get("outputs", {})
    img_index = 0
    for node_id, node_output in outputs.items():
        for img in node_output.get("images", []):
            params = {
                "filename": img["filename"],
                "subfolder": img.get("subfolder", ""),
                "type": img.get("type", "output"),
            }
            resp = requests.get(f"{comfy_url.rstrip('/')}/view", params=params, timeout=60)
            resp.raise_for_status()
            ext = Path(img["filename"]).suffix or ".png"
            suffix = "" if img_index == 0 else f"_{img_index}"
            out_path = out_dir / f"{base_filename}{suffix}{ext}"
            out_path.write_bytes(resp.content)
            saved.append(out_path)
            img_index += 1
    return saved


def slugify(text: str, max_words: int = 6) -> str:
    words = re.findall(r"[a-zA-Z0-9]+", text.lower())[:max_words]
    return "-".join(words) or "scene"


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("story_file", type=Path, help="Path to the story/essay text file")
    ap.add_argument("workflow_file", type=Path, help="Path to ComfyUI API-format workflow JSON")
    ap.add_argument("--llm-url", default="http://localhost:8080/v1", help="OpenAI-compatible base URL (default: local llama-server)")
    ap.add_argument("--llm-model", default="local-model", help="Model name to send in the LLM request")
    ap.add_argument("--comfy-url", default="http://127.0.0.1:8188", help="ComfyUI server base URL")
    ap.add_argument("--num-scenes", type=int, default=6, help="Number of illustration points to generate")
    ap.add_argument("--prompt-node-id", default=None, help="Workflow node id to inject the prompt into (auto-detected if omitted)")
    ap.add_argument("--out-dir", type=Path, default=Path("./output"), help="Directory to save prompts.json and images")
    ap.add_argument("--prompts-only", action="store_true", help="Only run the two LLM passes and dump prompts.json, skip image generation")
    args = ap.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    story_text = args.story_file.read_text(encoding="utf-8")

    scenes = generate_prompts(story_text, args.llm_url, args.llm_model, args.num_scenes)

    prompts_path = args.out_dir / "prompts.json"
    prompts_path.write_text(json.dumps(scenes, indent=2), encoding="utf-8")
    print(f"[3/4] Wrote {len(scenes)} prompts to {prompts_path}")

    if args.prompts_only:
        print("--prompts-only set, skipping image generation.")
        return

    workflow_template = json.loads(args.workflow_file.read_text(encoding="utf-8"))
    prompt_node_id = args.prompt_node_id or find_positive_prompt_node(workflow_template)
    print(f"Using prompt node id: {prompt_node_id}")

    print(f"[4/4] Generating {len(scenes)} images via {args.comfy_url} ...")
    client_id = str(uuid.uuid4())
    for i, scene in enumerate(scenes, start=1):
        workflow = copy.deepcopy(workflow_template)
        workflow[prompt_node_id]["inputs"]["text"] = scene["prompt"]

        base_filename = f"{i:03d}_{slugify(scene.get('anchor', scene['prompt']))}"
        print(f"  ({i}/{len(scenes)}) {base_filename} :: {scene['prompt'][:70]}...")

        try:
            prompt_id = submit_workflow(args.comfy_url, workflow, client_id)
            history_entry = wait_for_result(args.comfy_url, prompt_id)
            saved = download_outputs(args.comfy_url, history_entry, args.out_dir, base_filename)
            for p in saved:
                print(f"      saved -> {p}")
        except Exception as e:
            print(f"      FAILED: {e}", file=sys.stderr)
            continue

    print("Done.")


if __name__ == "__main__":
    main()
