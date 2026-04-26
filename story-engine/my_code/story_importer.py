#!/usr/bin/env python3
"""
story_importer.py — Convert any prose .txt file into a Story Engine scene .md.

Uses an LLM to extract characters, world-building, beats, and narrative structure
from existing prose. The --imagination flag controls how much the LLM invents
versus strictly extracting from the source text.

Config (via .env or environment variables):
  STORY_IMPORTER_BASE_URL   — LLM endpoint
                              (falls back to SCENE_BUILDER_BASE_URL, then STORY_ENGINE_LOCAL_BASE_URL)
  STORY_IMPORTER_MODEL      — model to use
                              (falls back to SCENE_BUILDER_MODEL, then STORY_ENGINE_NARRATOR_MODEL)
  STORY_IMPORTER_API_KEY    — API key (default: "none" for local servers)
  STORY_IMPORTER_MAX_WORDS  — hard word-count limit for single-pass extraction (default: 6000)
  STORY_IMPORTER_WARN_WORDS — warn-but-proceed threshold (default: 4000)

Usage:
  python my_code/story_importer.py story.txt
  python my_code/story_importer.py story.txt --out output/my_scene.md --imagination 80
  python my_code/story_importer.py story.txt --imagination 0 --beats 5 --nsfw --yes
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Display and assembly helpers — reuse from scene_builder unchanged
from my_code.scene_builder import (
    assemble,
    validate_generated,
    slugify,
    _c, hr, wrap, set_theme,
    _VALID_POVS, _VALID_MODES,
)

# Importer-specific config and routing
from my_code.importers.base import (
    BASE_URL, MODEL,
    MAX_WORDS, WARN_WORDS,
    word_count, get_analyser,
)


# ── Argument parsing ───────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Story Engine — Story Importer: prose .txt → scene .md",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "input", metavar="STORY.TXT",
        help="Path to the prose .txt file to import",
    )
    p.add_argument(
        "--out", metavar="PATH",
        help="Output .md path (default: output/<slug>.md)",
    )
    p.add_argument(
        "--imagination", type=int, default=50, metavar="0-100",
        help=(
            "Invention level: 0=strict extraction only, "
            "50=balanced (default), 100=free invention for missing details"
        ),
    )
    p.add_argument(
        "--beats", type=int, default=0, metavar="N",
        help="Number of scene beats to produce (3–10). Default: auto from source length.",
    )
    p.add_argument(
        "--pov", default=None, choices=sorted(_VALID_POVS),
        help="Point of view override (default: inferred from source prose).",
    )
    p.add_argument(
        "--mode", default="autonomous", choices=sorted(_VALID_MODES),
        help="Execution mode for the generated scene (default: autonomous).",
    )
    p.add_argument(
        "--nsfw", action="store_true",
        help="Mark the generated scene as NSFW.",
    )
    p.add_argument(
        "--theme", choices=["dark", "light", "system"], default=None,
        help="Terminal colour theme.",
    )
    p.add_argument(
        "--yes", "-y", action="store_true",
        help="Skip the confirmation prompt and write immediately.",
    )
    return p.parse_args()


# ── Helpers ────────────────────────────────────────────────────────────────────

def _imagination_label(n: int) -> str:
    if n <= 20:  return "strict"
    if n <= 79:  return "balanced"
    return "free"


def _auto_beats(wc: int) -> int:
    """Choose a sensible default beat count from the source word count."""
    if wc < 1000:  return 3
    if wc < 2500:  return 4
    if wc < 4000:  return 5
    return min(10, max(3, wc // 1000))


def _print_summary(result: dict, wc: int, imagination: int, out_path: str) -> None:
    hr("═")
    print(_c("  EXTRACTION RESULT", "header"))
    hr("═")

    chars = result.get("characters", [])
    char_summary = ", ".join(
        f"{c['name']} ({c.get('role', '?')})" for c in chars
    ) or "(none)"

    beats = result.get("beats", [])
    winfo_wc = word_count(result.get("world_info", ""))

    rows = [
        ("Title",        result.get("title", "?")),
        ("POV",          result.get("pov", "?")),
        ("Target len",   f"{result.get('target_length', '?')} words"),
        ("Characters",   char_summary),
        ("Beats",        str(len(beats))),
        ("World-info",   f"{winfo_wc} words"),
        ("Imagination",  f"{imagination} ({_imagination_label(imagination)})"),
        ("Source words", f"{wc:,}"),
        ("Output",       out_path),
    ]
    label_w = max(len(r[0]) for r in rows)
    for label, value in rows:
        print(f"  {_c(label.ljust(label_w), 'label')}  {value}")
    print()

    print("  Beats:")
    for i, b in enumerate(beats, 1):
        pause_tag = _c("  [pause]", "muted") if b.get("pause") else ""
        print(f"    {_c(str(i) + '.', 'beat_num')} {_c(b['title'], 'beat_title')}{pause_tag}")
        print(wrap(b.get("instruction", ""), indent="       "))
    print()


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    args = _parse_args()

    if args.theme:
        set_theme(args.theme)

    hr("═")
    print(_c("  STORY ENGINE — STORY IMPORTER", "header"))
    print(_c(f"  endpoint : {BASE_URL}", "muted"))
    print(_c(f"  model    : {MODEL}", "muted"))
    hr("═")

    # ── Read input ─────────────────────────────────────────────────────────────
    in_path = Path(args.input)
    if not in_path.exists():
        print(_c(f"\n  ERROR: File not found: {args.input}", "error"))
        sys.exit(1)

    story_text = in_path.read_text(encoding="utf-8").strip()
    if not story_text:
        print(_c("\n  ERROR: Input file is empty.", "error"))
        sys.exit(1)

    wc = word_count(story_text)
    print(f"\n  Input : {in_path.name}  ({wc:,} words)")

    # ── Size routing ───────────────────────────────────────────────────────────
    analyser = get_analyser(wc)

    if wc > MAX_WORDS:
        # get_analyser returned ChunkedAnalyser; let it emit the user-friendly error
        try:
            analyser.analyse(story_text, args.imagination, 3)
        except NotImplementedError as exc:
            print(_c(f"\n  ERROR: {exc}", "error"))
            sys.exit(1)

    if wc > WARN_WORDS:
        print(_c(
            f"  WARNING: {wc:,} words approaches the single-pass limit ({MAX_WORDS:,}). "
            "Extraction quality may degrade for very long inputs.",
            "muted",
        ))

    # ── Resolve params ─────────────────────────────────────────────────────────
    imagination = max(0, min(100, args.imagination))
    beat_count  = max(3, min(10, args.beats if args.beats else _auto_beats(wc)))
    out_path_str = args.out or f"output/{slugify(in_path.stem)}.md"

    print(f"  Output: {out_path_str}")
    print(f"  Imagination: {imagination} ({_imagination_label(imagination)})  |  "
          f"Beats: {beat_count}  |  Mode: {args.mode}  |  NSFW: {args.nsfw}")

    # ── Run extraction ─────────────────────────────────────────────────────────
    print()
    hr()
    print(_c("  Analysing story — please wait...", "waiting"))
    hr()

    try:
        result = analyser.analyse(story_text, imagination, beat_count)
    except NotImplementedError as exc:
        print(_c(f"\n  ERROR: {exc}", "error"))
        sys.exit(1)
    except json.JSONDecodeError as exc:
        print(_c(f"\n  ERROR: Model returned invalid JSON — {exc}", "error"))
        print("  Try a more capable model (STORY_IMPORTER_MODEL) or adjust --imagination.")
        sys.exit(1)
    except Exception as exc:
        print(_c(f"\n  ERROR: {exc}", "error"))
        sys.exit(1)

    # CLI --pov overrides the LLM's inference
    if args.pov:
        result["pov"] = args.pov

    # ── Split into user_data + generated ──────────────────────────────────────
    user_data = {
        "title":         result.get("title", in_path.stem),
        "output_file":   out_path_str,
        "pov":           result.get("pov", "third-person"),
        "mode":          args.mode,
        "target_length": result.get("target_length", 3500),
        "nsfw":          "true" if args.nsfw else "false",
        "scenario":      result.get("scenario", ""),
        # Sentinel so validate_user_data skips fields only relevant to fresh builds
        "_loaded":       True,
    }
    generated = {
        "narrator_prompt":      result.get("narrator_prompt", ""),
        "writing_style":        result.get("writing_style", ""),
        "author_note_content":  result.get("author_note_content", ""),
        "world_info":           result.get("world_info", ""),
        "scene_setup":          result.get("scene_setup", {}),
        "characters":           result.get("characters", []),
        "beats":                result.get("beats", []),
        "writing_instructions": result.get("writing_instructions", ""),
    }

    # ── Print summary ──────────────────────────────────────────────────────────
    _print_summary(result, wc, imagination, out_path_str)

    # ── Validate ───────────────────────────────────────────────────────────────
    errors = validate_generated(generated)
    if errors:
        hr("═")
        print(_c(f"  VALIDATION — {len(errors)} problem(s) found", "error"))
        hr("═")
        for err in errors:
            print(_c(f"  ✗  {err}", "error"))
        print()
        if not args.yes:
            try:
                raw = input(_c("  Write anyway? [no] / 'yes' to proceed: ", "prompt")).strip().lower()
            except (EOFError, KeyboardInterrupt):
                print("\n  Aborted.")
                sys.exit(0)
            if raw not in ("yes", "y"):
                print("  Aborted — file not written.")
                sys.exit(1)

    # ── Confirm (only when validation passed and --yes not set) ───────────────
    elif not args.yes:
        try:
            raw = input(_c("  Write scene file? [yes] / 'no' to abort: ", "prompt")).strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n  Aborted.")
            sys.exit(0)
        if raw in ("no", "n"):
            print("  Aborted — file not written.")
            sys.exit(0)

    # ── Write ──────────────────────────────────────────────────────────────────
    content = assemble(user_data, generated)
    out_path = Path(out_path_str)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")

    hr("═")
    print(_c(f"  Written: {out_path}", "success"))
    hr("═")
    print()
    print(_c("Run the scene:", "label"))
    print(f"  conda activate strandsagents")
    print(f"  python -m my_code {out_path}")
    print()


if __name__ == "__main__":
    main()
