"""Draw Things HTTP API client.

Draw Things (macOS app) exposes an Automatic1111-webui-compatible HTTP API
once "Enable API Server" is turned on in its Settings (gear icon). Unlike
ComfyUI, there's no workflow graph to inject into -- one JSON request per
image, using whatever checkpoint/sampler is currently selected in the app.
"""

from __future__ import annotations

import base64
from pathlib import Path

import requests


def generate_images(
    drawthings_url: str,
    prompt: str,
    negative_prompt: str,
    seed: int | None,
    steps: int | None,
    cfg_scale: float | None,
    width: int | None,
    height: int | None,
    timeout: float = 900.0,
) -> list[bytes]:
    # Only send what's explicitly requested; omitted fields fall back to
    # whatever's currently configured in the Draw Things UI (model-specific
    # steps/cfg/size presets -- e.g. a FLUX.2 Klein checkpoint tuned for
    # steps=4 -- shouldn't get silently clobbered by generic defaults here).
    payload = {
        "prompt": prompt,
        "negative_prompt": negative_prompt or "",
        "seed": seed if seed is not None else -1,
    }
    if steps is not None:
        payload["steps"] = steps
    if cfg_scale is not None:
        payload["cfg_scale"] = cfg_scale
    if width is not None:
        payload["width"] = width
    if height is not None:
        payload["height"] = height
    resp = requests.post(
        f"{drawthings_url.rstrip('/')}/sdapi/v1/txt2img",
        json=payload,
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    images = data.get("images")
    if not images:
        raise RuntimeError(f"Draw Things returned no images: {data}")
    return [base64.b64decode(img) for img in images]


def save_images(image_bytes_list: list[bytes], out_dir: Path, base_filename: str) -> list[Path]:
    saved = []
    for i, img_bytes in enumerate(image_bytes_list):
        suffix = "" if i == 0 else f"_{i}"
        out_path = out_dir / f"{base_filename}{suffix}.png"
        out_path.write_bytes(img_bytes)
        saved.append(out_path)
    return saved
