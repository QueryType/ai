"""Batch story runner — runs the engine on multiple scene files in sequence.

Usage:
    python -m my_code.batch scenes/story_00.md scenes/story_01.md scenes/story_02.md
    python -m my_code.batch scenes/          # all .md files in directory, sorted
    python -m my_code.batch scenes/*.md

Files are processed in the order given (or alphabetical order for directories).
A failed scene is logged and skipped — the batch continues with the next file.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from my_code.agents.orchestrator import (
    derive_story_coords,
    run_scene,
    skip_eval_env_default,
    skip_memory_env_default,
)


def _collect_files(paths: list[str]) -> list[Path]:
    """Expand directories to sorted .md files; keep explicit file paths as-is."""
    result: list[Path] = []
    for p in paths:
        path = Path(p)
        if path.is_dir():
            result.extend(sorted(path.glob("*.md")))
        else:
            result.append(path)
    return result


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Run the story engine on multiple scene files in sequence."
    )
    parser.add_argument(
        "files",
        nargs="+",
        help="Scene .md files or directories containing them (sorted alphabetically)",
    )
    parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="Stop the batch if any scene fails (default: skip and continue)",
    )
    parser.add_argument(
        "--skip-eval",
        action="store_true",
        default=skip_eval_env_default(),
        help="Bypass the evaluator for all scenes — no quality checks or retries "
        "(default from STORY_ENGINE_SKIP_EVAL env var)",
    )
    parser.add_argument(
        "--skip-memory",
        action="store_true",
        default=skip_memory_env_default(),
        help="Bypass Story Memory for all scenes — no cross-file fact extraction or "
        "retrieval (default from STORY_ENGINE_SKIP_MEMORY env var)",
    )
    args = parser.parse_args(argv)

    files = _collect_files(args.files)
    if not files:
        print("No .md files found.", file=sys.stderr)
        sys.exit(1)

    # Cross-file continuity memory (docs/STORY_MEMORY_SPEC.md): all files in
    # this batch share one story_id, keyed off the first file's name, so
    # facts extracted from file 0 are retrievable while generating file 2.
    # scene_index is the file's position in the sequence as given/sorted here
    # (not re-derived per file), so batch order is authoritative even if a
    # file's own [meta] output_file doesn't follow the story_NN convention.
    batch_story_id, _ = derive_story_coords(files[0].name)

    print(f"Batch: {len(files)} scene(s) queued (story_id={batch_story_id})")
    for i, f in enumerate(files, 1):
        print(f"  {i}. {f}")
    print()

    results: list[tuple[Path, str, float]] = []  # (path, status, elapsed_s)

    for i, scene_path in enumerate(files, 1):
        print(f"[{i}/{len(files)}] Starting: {scene_path}")
        if not scene_path.exists():
            print(f"  SKIP — file not found: {scene_path}")
            results.append((scene_path, "not_found", 0.0))
            continue

        t0 = time.time()
        try:
            output = run_scene(
                str(scene_path),
                skip_eval=args.skip_eval,
                skip_memory=args.skip_memory,
                story_id=batch_story_id,
                scene_index=i - 1,
            )
            elapsed = time.time() - t0
            print(f"  DONE in {elapsed:.0f}s → {output}")
            results.append((scene_path, "ok", elapsed))
        except Exception as exc:
            elapsed = time.time() - t0
            print(f"  FAILED in {elapsed:.0f}s: {type(exc).__name__}: {exc}")
            results.append((scene_path, f"error: {type(exc).__name__}", elapsed))
            if args.stop_on_error:
                print("Stopping batch (--stop-on-error).")
                break

    # Summary
    print(f"\n{'='*60}")
    print("Batch complete")
    print(f"{'='*60}")
    ok = sum(1 for _, s, _ in results if s == "ok")
    total_time = sum(e for _, _, e in results)
    print(f"  {ok}/{len(results)} succeeded  |  total time: {total_time:.0f}s")
    for path, status, elapsed in results:
        mark = "✓" if status == "ok" else "✗"
        print(f"  {mark} {path.name:<40} {status}  ({elapsed:.0f}s)")


if __name__ == "__main__":
    main()
