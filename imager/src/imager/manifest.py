"""Resumable run state: tracks per-stage (and per-scene, for images) completion."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Optional

from .config import RunConfig, STAGES

MANIFEST_FILENAME = "manifest.json"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_json(obj: dict) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode("utf-8")).hexdigest()


class RunManifest:
    def __init__(self, path: Path):
        self.path = path
        if path.exists():
            self.data = json.loads(path.read_text(encoding="utf-8"))
        else:
            self.data = {"story_hash": None, "stages": {s: {"status": "pending"} for s in STAGES}}

    def save(self) -> None:
        self.path.write_text(json.dumps(self.data, indent=2), encoding="utf-8")

    def stage(self, name: str) -> dict:
        return self.data["stages"].setdefault(name, {"status": "pending"})

    def is_stage_fresh(self, name: str, input_hash: str) -> bool:
        st = self.stage(name)
        return st.get("status") == "done" and st.get("input_hash") == input_hash

    def mark_stage_done(self, name: str, input_hash: str, output: str) -> None:
        self.data["stages"][name] = {"status": "done", "input_hash": input_hash, "output": output}
        self.save()

    def invalidate_from(self, stage: str) -> None:
        idx = STAGES.index(stage)
        for s in STAGES[idx:]:
            self.data["stages"][s] = {"status": "pending"}
        self.save()

    def set_story_hash(self, h: str) -> None:
        if self.data.get("story_hash") != h:
            # story changed entirely: nuke everything
            self.data["story_hash"] = h
            self.data["stages"] = {s: {"status": "pending"} for s in STAGES}
            self.save()

    # -- per-scene image tracking --------------------------------------

    def image_status(self, scene_id: str) -> str:
        return self.stage("images").setdefault("scenes", {}).get(scene_id, "pending")

    def set_image_status(self, scene_id: str, status: str) -> None:
        self.stage("images").setdefault("scenes", {})[scene_id] = status
        self.save()

    def should_run_stage(self, config: RunConfig, stage: str, extra_input: str = "") -> bool:
        if config.force:
            return True
        if config.force_from and STAGES.index(stage) >= STAGES.index(config.force_from):
            return True
        input_hash = sha256_json({**config.stage_relevant_fields(stage), "extra": extra_input})
        return not self.is_stage_fresh(stage, input_hash)

    def stage_input_hash(self, config: RunConfig, stage: str, extra_input: str = "") -> str:
        return sha256_json({**config.stage_relevant_fields(stage), "extra": extra_input})
