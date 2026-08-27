"""ComfyUI REST client: node auto-detection, param injection, submit/poll/download.

Generalized from bootstrap/story_to_images.py to also handle a negative prompt
node and best-effort seed/steps/cfg patching.
"""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path

import requests

_TEXT_ENCODE_CLASSES = ("CLIPTextEncode", "CLIPTextEncodeSDXL")


def _text_encode_candidates(workflow: dict) -> list[tuple[str, dict]]:
    return [
        (node_id, node) for node_id, node in workflow.items()
        if node.get("class_type") in _TEXT_ENCODE_CLASSES
    ]


def find_positive_prompt_node(workflow: dict) -> str:
    candidates = _text_encode_candidates(workflow)
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


def find_negative_prompt_node(workflow: dict, positive_node_id: str) -> str | None:
    candidates = _text_encode_candidates(workflow)
    for node_id, node in candidates:
        if node_id == positive_node_id:
            continue
        title = node.get("_meta", {}).get("title", "").lower()
        if "neg" in title:
            return node_id
    others = [node_id for node_id, _ in candidates if node_id != positive_node_id]
    if len(others) == 1:
        print(
            f"WARNING: no node titled 'negative' found; assuming the remaining "
            f"CLIPTextEncode node {others[0]} is negative. Pass --neg-prompt-node-id to override.",
            file=sys.stderr,
        )
        return others[0]
    if len(others) > 1:
        print(
            f"WARNING: could not auto-detect a negative prompt node among "
            f"{others}. Negative prompts will not be injected. Pass --neg-prompt-node-id to fix.",
            file=sys.stderr,
        )
    return None


def apply_generation_params(
    workflow: dict,
    seed: int | None,
    steps: int | None,
    cfg_scale: float | None,
    width: int | None = None,
    height: int | None = None,
) -> None:
    """Best-effort: patch matching input keys on any node that has them (e.g.
    width/height on an EmptyLatentImage-class node)."""
    for node in workflow.values():
        inputs = node.get("inputs", {})
        if seed is not None and "seed" in inputs:
            inputs["seed"] = seed
        if steps is not None and "steps" in inputs:
            inputs["steps"] = steps
        if cfg_scale is not None and "cfg" in inputs:
            inputs["cfg"] = cfg_scale
        if width is not None and "width" in inputs:
            inputs["width"] = width
        if height is not None and "height" in inputs:
            inputs["height"] = height


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
