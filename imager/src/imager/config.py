"""Run configuration shared across all pipeline stages."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

# Per-scene orientation (LLM-classified in the scenes stage, see
# scene_selection.py) maps to one of these resolutions when --auto-orientation
# is on. Chosen as common FLUX/SDXL-friendly buckets (divisible by 64, similar
# total pixel budget across orientations). An explicit --width/--height
# overrides this entirely, for every scene.
ORIENTATION_SIZES = {
    "square": (1024, 1024),
    "portrait": (832, 1216),
    "landscape": (1216, 832),
}


@dataclass
class RunConfig:
    story_file: Path
    workflow_file: Optional[Path]
    out_dir: Path

    llm_url: str = "http://localhost:8080/v1"
    llm_model: str = "local-model"
    llm_api_key: str = "not-needed"

    backend: str = "comfy"  # "comfy" or "drawthings"
    comfy_url: str = "http://127.0.0.1:8188"
    drawthings_url: str = "http://127.0.0.1:7860"
    width: Optional[int] = None  # explicit override: forces this size for every scene, either backend
    height: Optional[int] = None
    auto_orientation: bool = True  # size each scene from its LLM-classified orientation (see ORIENTATION_SIZES); ignored if width/height are set

    chunk_budget_chars: int = 6000
    parallel_chunks: int = 4  # concurrent LLM calls during bible/scenes stages

    num_scenes: Optional[int] = None  # None = let the LLM decide

    negative_prompt: str = ""
    prompt_node_id: Optional[str] = None
    neg_prompt_node_id: Optional[str] = None

    prompt_style: str = "prose"  # "prose" (FLUX.2/Z-Image) or "tags" (SDXL-family)
    enhance_prompts: bool = True  # LLM-enhance each scene's action sentence before composition; --no-enhance-prompts to skip

    seed: Optional[int] = None
    steps: Optional[int] = None
    cfg_scale: Optional[float] = None

    force: bool = False
    force_from: Optional[str] = None
    only_stage: Optional[str] = None

    def to_json(self) -> dict:
        d = asdict(self)
        d["story_file"] = str(self.story_file)
        d["workflow_file"] = str(self.workflow_file) if self.workflow_file else None
        d["out_dir"] = str(self.out_dir)
        return d

    def stage_relevant_fields(self, stage: str) -> dict:
        """Subset of config that should invalidate a stage's cached output when changed."""
        base = self.to_json()
        relevant = {
            "chunk": ["chunk_budget_chars"],
            "bible": ["chunk_budget_chars", "llm_url", "llm_model"],
            "scenes": ["chunk_budget_chars", "llm_url", "llm_model", "num_scenes"],
            "prompts": ["num_scenes", "negative_prompt", "seed", "prompt_style", "enhance_prompts", "llm_url", "llm_model"],
            "images": [
                "backend",
                "prompt_node_id", "neg_prompt_node_id", "comfy_url", "workflow_file",
                "drawthings_url", "width", "height", "auto_orientation",
                "seed", "steps", "cfg_scale",
            ],
        }
        keys = relevant.get(stage, [])
        return {k: base[k] for k in keys}

    def resolve_scene_size(self, scene: dict) -> tuple[Optional[int], Optional[int]]:
        """Width/height to request for a given scene's image, or (None, None)
        to leave size unspecified (workflow default for comfy, current UI
        setting for drawthings)."""
        if self.width is not None and self.height is not None:
            return self.width, self.height
        if not self.auto_orientation:
            return None, None
        orientation = scene.get("orientation", "square")
        return ORIENTATION_SIZES.get(orientation, ORIENTATION_SIZES["square"])


STAGES = ["chunk", "bible", "scenes", "prompts", "images"]
