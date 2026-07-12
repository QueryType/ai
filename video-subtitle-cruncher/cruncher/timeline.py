"""Phase 2: build timeline.json — kept frames + vision descriptions + transcript windows.

Descriptions are cached by phash (descriptions.json in the job dir), so
re-running is free for frames the model has already seen.
"""

import json
from pathlib import Path

from .manifest import Job
from .provider import VisionProvider

TRANSCRIPT_WINDOW = 15.0  # seconds either side of the frame

DESCRIBE_PROMPT = (
    "Describe this video frame densely and factually so it can be found and "
    "understood later without seeing the image.\n"
    "- Transcribe important on-screen text exactly: headings, bullet points, "
    "labels, code, table/chart values.\n"
    "- Describe diagrams, charts, UI elements, and people (role, not identity).\n"
    "- Note the overall layout in one clause.\n"
    "Do not speculate beyond what is visible. Keep it under 150 words.\n"
    "{context}"
)


def transcript_window(segments: list[dict], t: float,
                      window: float = TRANSCRIPT_WINDOW) -> str:
    parts = [s["text"] for s in segments
             if s["end"] >= t - window and s["start"] <= t + window]
    return " ".join(parts)


def build_timeline(job: Job, provider: VisionProvider,
                   window: float = TRANSCRIPT_WINDOW) -> list[dict]:
    manifest = job.load_manifest()
    frames = manifest.get("frames", [])
    if not frames:
        raise RuntimeError("no frames in manifest — run `crunch snapshot`/`record` first")
    transcript = json.loads(job.transcript_path.read_text()) \
        if job.transcript_path.exists() else {"segments": []}
    segments = transcript["segments"]

    cache_path = job.root / "descriptions.json"
    cache: dict = json.loads(cache_path.read_text()) if cache_path.exists() else {}

    timeline = []
    calls = 0
    for i, entry in enumerate(frames):
        t, phash = entry["t"], entry["phash"]
        ctx = transcript_window(segments, t, window)
        if phash in cache:
            desc = cache[phash]
        else:
            context_line = (f"Spoken around this moment (context only, don't "
                            f"repeat verbatim): \"{ctx}\"") if ctx else ""
            desc = provider.ask_image(job.frames_dir / entry["frame"],
                                      DESCRIBE_PROMPT.format(context=context_line),
                                      max_tokens=400)
            cache[phash] = desc
            cache_path.write_text(json.dumps(cache, indent=2, ensure_ascii=False))
            calls += 1
            print(f"  [{i + 1}/{len(frames)}] t={t:.0f}s described")
        timeline.append({
            "t": t,
            "frame": entry["frame"],
            "phash": phash,
            "description": desc,
            "transcript_window": ctx,
        })

    job.timeline_path.write_text(
        json.dumps(timeline, indent=2, ensure_ascii=False))
    print(f"  {len(timeline)} timeline entries ({calls} new descriptions, "
          f"{len(timeline) - calls} cached)")
    return timeline
