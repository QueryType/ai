"""Phase 1a: sample frames from a video and keep only perceptually distinct ones."""

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

import imagehash
from PIL import Image, ImageDraw

# Compare a candidate against this many recently-kept frames, so a brief
# cut back to a previous shot (A -> B -> A) doesn't re-admit near-duplicates.
COMPARE_LAST = 3


@dataclass
class Sample:
    t: float          # seconds into the video
    path: Path


def probe(video: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json",
         "-show_format", "-show_streams", str(video)],
        capture_output=True, text=True, check=True).stdout
    info = json.loads(out)
    vstream = next(s for s in info["streams"] if s["codec_type"] == "video")
    return {
        "duration": float(info["format"]["duration"]),
        "width": int(vstream["width"]),
        "height": int(vstream["height"]),
        "has_audio": any(s["codec_type"] == "audio" for s in info["streams"]),
    }


def extract_samples(video: Path, samples_dir: Path, fps: float,
                    long_edge: int) -> list[Sample]:
    """Sample at `fps`, downscaled so the long edge is at most `long_edge`."""
    scale = (f"scale=if(gt(iw\\,ih)\\,min({long_edge}\\,iw)\\,-2)"
             f":if(gt(iw\\,ih)\\,-2\\,min({long_edge}\\,ih))")
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(video),
         "-vf", f"fps={fps},{scale}", "-qscale:v", "3",
         str(samples_dir / "%06d.jpg")],
        check=True)
    samples = []
    for p in sorted(samples_dir.glob("*.jpg")):
        idx = int(p.stem)  # 1-based frame counter from ffmpeg
        samples.append(Sample(t=(idx - 1) / fps, path=p))
    return samples


# colorhash distance at/above which a frame counts as new even when the
# structural phash barely moved (catches color-only scene changes, since
# phash works on grayscale structure).
COLOR_THRESHOLD = 5


def masked_hashes(image: Image.Image, band: tuple[float, float] | None):
    """Structural phash + colorhash; if a caption band is given, black it out
    first so caption changes don't make identical scenes look different."""
    if band is not None:
        image = image.copy()
        top = int(band[0] * image.height)
        bottom = int(band[1] * image.height)
        ImageDraw.Draw(image).rectangle([0, top, image.width, bottom], fill="black")
    return imagehash.phash(image), imagehash.colorhash(image)


def dedup(samples: list[Sample], frames_dir: Path, threshold: int,
          band: tuple[float, float] | None = None,
          color_threshold: int = COLOR_THRESHOLD) -> list[dict]:
    """Copy perceptually distinct samples into frames_dir, named by timestamp.

    A sample is a duplicate only if it's close to a recent kept frame on BOTH
    hashes: structurally (phash) and in color distribution (colorhash).
    """
    kept: list[dict] = []
    recent: list[tuple] = []
    for sample in samples:
        with Image.open(sample.path) as img:
            h, ch = masked_hashes(img, band)
        if any(h - ph <= threshold and ch - pch < color_threshold
               for ph, pch in recent):
            continue
        dest = frames_dir / f"{sample.t:09.2f}.jpg"
        dest.write_bytes(sample.path.read_bytes())
        kept.append({"t": sample.t, "frame": dest.name, "phash": str(h)})
        recent.append((h, ch))
        recent = recent[-COMPARE_LAST:]
    return kept
