"""Job directories: one per processed video, holding all durable artifacts."""

import json
import re
import shutil
import time
from pathlib import Path

DEFAULT_JOBS_DIR = Path("jobs")


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", name).strip("-").lower()
    return slug or "job"


class Job:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.frames_dir = self.root / "frames"
        self.samples_dir = self.root / "samples"
        self.outputs_dir = self.root / "outputs"
        self.manifest_path = self.root / "manifest.json"
        self.transcript_path = self.root / "transcript.json"
        self.timeline_path = self.root / "timeline.json"

    @classmethod
    def create(cls, jobs_dir: Path, video: Path, name: str | None = None,
               force: bool = False) -> "Job":
        slug = slugify(name or video.stem)
        root = Path(jobs_dir) / slug
        if root.exists():
            if not force:
                raise FileExistsError(
                    f"job '{slug}' already exists at {root} (use --force to redo)")
            shutil.rmtree(root)
        job = cls(root)
        for d in (job.frames_dir, job.samples_dir, job.outputs_dir):
            d.mkdir(parents=True)
        job.save_manifest({
            "source": str(video.resolve()),
            "created": time.strftime("%Y-%m-%d %H:%M:%S"),
            "settings": {},
            "phases": {},
        })
        return job

    @classmethod
    def open(cls, jobs_dir: Path, name: str) -> "Job":
        root = Path(jobs_dir) / name
        if not (root / "manifest.json").exists():
            raise FileNotFoundError(f"no job named '{name}' under {jobs_dir}")
        return cls(root)

    def load_manifest(self) -> dict:
        return json.loads(self.manifest_path.read_text())

    def save_manifest(self, manifest: dict) -> None:
        self.manifest_path.write_text(json.dumps(manifest, indent=2))

    def update_manifest(self, **updates) -> dict:
        manifest = self.load_manifest()
        for key, value in updates.items():
            if isinstance(value, dict) and isinstance(manifest.get(key), dict):
                manifest[key].update(value)
            else:
                manifest[key] = value
        self.save_manifest(manifest)
        return manifest

    def write_transcript(self, source: str, segments: list[dict]) -> None:
        self.transcript_path.write_text(json.dumps(
            {"source": source, "segments": segments}, indent=2, ensure_ascii=False))

    def drop_samples(self) -> None:
        shutil.rmtree(self.samples_dir, ignore_errors=True)
