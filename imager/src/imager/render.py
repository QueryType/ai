"""Renders a completed run's artifacts (chunks/scenes/prompts/images) into a
single standalone HTML page: the full story text with each scene's image
placed inline at the point in the text it illustrates.

Reads only what's already on disk in --out-dir -- no LLM/image-backend calls,
so it's cheap to rerun any time after the images stage has produced at least
some images (scenes without a matching image file are rendered as text only).
"""

from __future__ import annotations

import argparse
import base64
import difflib
import html
import json
import mimetypes
import re
from pathlib import Path

_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _find_paragraph_index(anchor: str, paragraphs: list[str]) -> int:
    anchor_norm = _normalize(anchor)
    if not anchor_norm or not paragraphs:
        return max(0, len(paragraphs) - 1)

    for i, p in enumerate(paragraphs):
        if anchor_norm in _normalize(p):
            return i

    best_i, best_ratio = len(paragraphs) - 1, 0.0
    for i, p in enumerate(paragraphs):
        ratio = difflib.SequenceMatcher(None, _normalize(p), anchor_norm).ratio()
        if ratio > best_ratio:
            best_ratio, best_i = ratio, i
    return best_i if best_ratio > 0.12 else len(paragraphs) - 1


def _find_scene_image(out_dir: Path, scene_id: str) -> Path | None:
    # images/ is the standard location; out_dir itself is a fallback for
    # runs generated before images moved into their own subfolder.
    for d in (out_dir / "images", out_dir):
        if not d.is_dir():
            continue
        for ext in _IMAGE_EXTS:
            matches = sorted(d.glob(f"{scene_id}_*{ext}"))
            if matches:
                return matches[0]
    return None


def _humanize_title(out_dir: Path) -> str:
    return out_dir.resolve().name.replace("_", " ").replace("-", " ").title()


# Base64-inlining every image makes a single portable file, but for a long
# story with many scenes it balloons into something no browser/email client
# handles gracefully -- past this total, --embed-images is silently declined
# in favor of relative links instead (still works, just not single-file).
_EMBED_SIZE_LIMIT_BYTES = 20 * 1024 * 1024


def _total_image_bytes(out_dir: Path, scenes: list[dict]) -> int:
    total = 0
    for scene in scenes:
        img_path = _find_scene_image(out_dir, scene["id"])
        if img_path is not None:
            total += img_path.stat().st_size
    return total


_HTML_HEAD = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,500;0,9..144,600;1,9..144,500&family=Newsreader:ital,wght@0,400;0,500;1,400;1,500&display=swap" rel="stylesheet">
<style>
:root {{
  --bg: #efe9dc;
  --ink: #221f1a;
  --muted: #6e6558;
  --rule: #d9cfb8;
  --accent: #3f5d46;
  --frame: rgba(34, 31, 26, 0.12);
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    --bg: #1b1a17;
    --ink: #ece6d8;
    --muted: #a89f8c;
    --rule: #3a362c;
    --accent: #86b795;
    --frame: rgba(236, 230, 216, 0.14);
  }}
}}
:root[data-theme="dark"] {{
  --bg: #1b1a17;
  --ink: #ece6d8;
  --muted: #a89f8c;
  --rule: #3a362c;
  --accent: #86b795;
  --frame: rgba(236, 230, 216, 0.14);
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font-family: 'Newsreader', Georgia, 'Iowan Old Style', serif;
  font-size: 19px;
  line-height: 1.75;
  -webkit-font-smoothing: antialiased;
}}
.page {{
  max-width: 660px;
  margin: 0 auto;
  padding: 8vw 24px 12vw;
}}
header.title-block {{
  text-align: center;
  margin-bottom: 4.5rem;
}}
header.title-block h1 {{
  font-family: 'Fraunces', Georgia, serif;
  font-optical-sizing: auto;
  font-weight: 600;
  font-size: clamp(2.1rem, 6vw, 3rem);
  letter-spacing: 0.005em;
  text-wrap: balance;
  margin: 0 0 1.1rem;
}}
header.title-block .rule {{
  width: 68px;
  height: 5px;
  margin: 0 auto 1.1rem;
  border-top: 1px solid var(--accent);
  border-bottom: 1px solid var(--accent);
}}
header.title-block .tone {{
  font-style: italic;
  color: var(--muted);
  font-size: 1.05rem;
  margin: 0;
}}
p {{
  margin: 0;
  text-align: left;
  text-indent: 1.5em;
  hyphens: auto;
}}
p.opening,
figure + p {{
  text-indent: 0;
}}
p.opening::first-letter {{
  font-family: 'Fraunces', Georgia, serif;
  font-weight: 600;
  font-size: 3.6em;
  line-height: 0.82;
  float: left;
  color: var(--accent);
  padding: 0.04em 0.09em 0 0;
}}
figure {{
  margin: 3.4rem auto;
  text-align: center;
}}
figure img {{
  display: block;
  width: 100%;
  height: auto;
  border: 1px solid var(--frame);
  padding: 10px;
  background: var(--bg);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.08);
}}
figure.portrait img {{
  max-width: 56%;
  margin: 0 auto;
}}
figure.square img {{
  max-width: 74%;
  margin: 0 auto;
}}
figcaption {{
  margin-top: 1rem;
}}
figcaption .plate-label {{
  display: block;
  font-family: 'Newsreader', serif;
  font-variant: small-caps;
  letter-spacing: 0.09em;
  font-size: 0.8rem;
  color: var(--accent);
  margin-bottom: 0.4rem;
}}
figcaption .plate-caption {{
  font-style: italic;
  color: var(--muted);
  font-size: 0.94rem;
  line-height: 1.55;
}}
footer.colophon {{
  margin-top: 5rem;
  padding-top: 1.6rem;
  border-top: 1px solid var(--rule);
  text-align: center;
  color: var(--muted);
  font-variant: small-caps;
  letter-spacing: 0.07em;
  font-size: 0.9rem;
}}
</style>
</head>
<body>
<div class="page">
"""

_HTML_TAIL = """</div>
</body>
</html>
"""


def _image_src(img_path: Path, out_dir: Path, embed_images: bool) -> str:
    if not embed_images:
        return img_path.relative_to(out_dir).as_posix()
    mime = mimetypes.guess_type(img_path.name)[0] or "image/png"
    data = base64.b64encode(img_path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{data}"


def render_html(out_dir: Path, title: str | None = None, embed_images: bool = False) -> str:
    chunks = _read_json(out_dir / "chunks.json")
    scenes = _read_json(out_dir / "scenes.json")
    bible = {}
    bible_path = out_dir / "story_bible.json"
    if bible_path.exists():
        bible = _read_json(bible_path)

    chunks.sort(key=lambda c: c["index"])
    scenes_by_chunk: dict[str, list[dict]] = {}
    for s in scenes:
        scenes_by_chunk.setdefault(s.get("chunk_id"), []).append(s)

    image_count = 0
    body_parts: list[str] = []
    is_first_paragraph = True

    for chunk in chunks:
        paragraphs = [p for p in chunk["text"].split("\n\n") if p.strip()]
        chunk_scenes = scenes_by_chunk.get(chunk["id"], [])

        attached: dict[int, list[dict]] = {}
        last_idx = 0
        for scene in chunk_scenes:
            idx = _find_paragraph_index(scene.get("anchor", ""), paragraphs)
            idx = max(idx, last_idx)  # keep image order consistent with story order
            idx = min(idx, len(paragraphs) - 1)
            attached.setdefault(idx, []).append(scene)
            last_idx = idx

        for i, para in enumerate(paragraphs):
            p_class = ' class="opening"' if is_first_paragraph else ""
            is_first_paragraph = False
            body_parts.append(f"<p{p_class}>{html.escape(para).replace(chr(10), '<br>')}</p>")
            for scene in attached.get(i, []):
                img_path = _find_scene_image(out_dir, scene["id"])
                if img_path is None:
                    continue
                image_count += 1
                orientation = scene.get("orientation", "square")
                caption = scene.get("description", "").strip()
                cap_html = (
                    f'<figcaption><span class="plate-label">Plate {image_count}</span>'
                    f'<span class="plate-caption">{html.escape(caption)}</span></figcaption>'
                    if caption else
                    f'<figcaption><span class="plate-label">Plate {image_count}</span></figcaption>'
                )
                src = _image_src(img_path, out_dir, embed_images)
                body_parts.append(
                    f'<figure class="{html.escape(orientation)}">'
                    f'<img src="{html.escape(src)}" alt="{html.escape(caption)}" loading="lazy">'
                    f"{cap_html}</figure>"
                )

    resolved_title = title or _humanize_title(out_dir)
    tone = bible.get("tone", "").strip()
    tone_html = f'<p class="tone">{html.escape(tone)}</p>' if tone else ""

    header = (
        f'<header class="title-block"><h1>{html.escape(resolved_title)}</h1>'
        f'<div class="rule"></div>{tone_html}</header>'
    )
    total_scenes = len(scenes)
    footer = (
        f'<footer class="colophon">{image_count} of {total_scenes} scenes illustrated'
        f" &middot; rendered with imager</footer>"
    )

    return (
        _HTML_HEAD.format(title=html.escape(resolved_title))
        + header
        + "\n".join(body_parts)
        + footer
        + _HTML_TAIL
    )


def main():
    ap = argparse.ArgumentParser(description="Render a completed imager run into a single illustrated HTML page.")
    ap.add_argument("out_dir", type=Path, help="Run's output directory (containing chunks.json, scenes.json, and images)")
    ap.add_argument("-o", "--output", type=Path, default=None, help="Output HTML path (default: <out-dir>/story.html)")
    ap.add_argument("--title", default=None, help="Story title (default: derived from the out-dir name)")
    ap.add_argument(
        "--embed-images", action="store_true",
        help="Base64-inline images into the HTML (fully portable single file, larger output) "
             "instead of relative <img src> paths (default: relative, keep the HTML next to the images)",
    )
    args = ap.parse_args()

    embed_images = args.embed_images
    if embed_images:
        scenes = _read_json(args.out_dir / "scenes.json")
        total_bytes = _total_image_bytes(args.out_dir, scenes)
        if total_bytes > _EMBED_SIZE_LIMIT_BYTES:
            print(
                f"NOTE: {total_bytes / 1e6:.0f}MB of images is too large to embed "
                f"(> {_EMBED_SIZE_LIMIT_BYTES / 1e6:.0f}MB) -- using relative image links instead.",
            )
            embed_images = False

    out_html = args.output or (args.out_dir / "story.html")
    out_html.write_text(render_html(args.out_dir, args.title, embed_images), encoding="utf-8")
    print(f"Wrote {out_html}")


if __name__ == "__main__":
    main()
