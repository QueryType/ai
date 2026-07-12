"""Screen capture source: grab a region of the screen as a timed image sequence.

The captured samples feed the exact same dedup + CC pipeline as video samples.
Transcript source is CC-only (there's no audio channel to fall back to).
"""

import time
from pathlib import Path

from PIL import Image

from .snapshot import Sample


def parse_region(spec: str) -> dict:
    """'X,Y,W,H' in screen points -> mss monitor dict."""
    try:
        x, y, w, h = (int(v) for v in spec.split(","))
    except ValueError:
        raise ValueError(f"bad region '{spec}' — expected X,Y,W,H, e.g. 100,200,1280,720")
    if w <= 0 or h <= 0:
        raise ValueError(f"bad region '{spec}' — width/height must be positive")
    return {"left": x, "top": y, "width": w, "height": h}


def record(samples_dir: Path, region: dict | None = None, interval: float = 1.0,
           duration: float | None = None, long_edge: int = 1024) -> list[Sample]:
    """Capture until `duration` seconds elapse or the user hits Ctrl-C."""
    import mss

    samples: list[Sample] = []
    with mss.mss() as sct:
        monitor = region or sct.monitors[1]  # 1 = primary display
        start = time.monotonic()
        idx = 0
        try:
            while True:
                t = time.monotonic() - start
                if duration is not None and t >= duration:
                    break
                raw = sct.grab(monitor)
                img = Image.frombytes("RGB", raw.size, raw.rgb)
                if idx == 0 and img.getextrema() == ((0, 0), (0, 0), (0, 0)):
                    print("  warning: capture is all black — grant Screen Recording "
                          "permission to your terminal (System Settings → Privacy)")
                if max(img.size) > long_edge:
                    img.thumbnail((long_edge, long_edge))
                path = samples_dir / f"{idx:06d}.jpg"
                img.save(path, format="JPEG", quality=85)
                samples.append(Sample(t=round(t, 2), path=path))
                idx += 1
                if idx % 10 == 0:
                    print(f"  {idx} captures ({t:.0f}s) ...")
                delay = start + idx * interval - time.monotonic()
                if delay > 0:
                    time.sleep(delay)
        except KeyboardInterrupt:
            print(f"\n  stopped by user after {len(samples)} captures")
    return samples
