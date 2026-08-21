"""Backfill facts db — populate cross-file continuity memory from an existing
story output sequence that predates the fact-store feature.

Usage:
    python -m my_code.backfill_facts output/story_00.md output/story_01.md
    python -m my_code.backfill_facts output/          # all .md in dir, alphabetical

Each file must already have <!-- beat:N --> markers (embedded automatically by
new runs; add them to older files with `python -m my_code.rewrite <file> --map`
first — that's a one-time, no-LLM, interactive step this tool does not run for
you). Beats are walked in file order, then beat order within each file, and fed
through the same extractor used for live runs — so a backfilled db is
indistinguishable from one built by actually running the scenes.

Design: docs/STORY_MEMORY_SPEC.md (Phase 6).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from my_code.agents.fact_extractor import call_fact_extractor
from my_code.agents.orchestrator import _parse_output_beats, derive_story_coords
from my_code.batch import _collect_files
from my_code.tools import fact_store


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Populate the facts db from an existing story output sequence."
    )
    parser.add_argument(
        "files",
        nargs="+",
        help="Story output .md files or directories containing them (sorted alphabetically)",
    )
    args = parser.parse_args(argv)

    files = _collect_files(args.files)
    if not files:
        print("No .md files found.", file=sys.stderr)
        sys.exit(1)

    missing_markers = []
    for f in files:
        try:
            _parse_output_beats(str(f))
        except ValueError:
            missing_markers.append(f)
    if missing_markers:
        print("These files have no beat markers — run --map on each first:", file=sys.stderr)
        for f in missing_markers:
            print(f"  python -m my_code.rewrite {f} --map", file=sys.stderr)
        sys.exit(1)

    story_id, _ = derive_story_coords(files[0].name)
    db_path = fact_store.db_path_for_output(str(files[0]), story_id)
    fact_store.init_db(db_path)
    print(f"Backfilling story_id={story_id} → {db_path}")

    total_facts = 0
    for i, f in enumerate(files):
        # scene_index is this file's position in the sequence as given/sorted
        # here (not re-derived per file from its own name) — same reasoning
        # as batch.py: file order is authoritative even if a filename doesn't
        # follow the story_NN convention.
        scene_index = i
        beats = _parse_output_beats(str(f))
        print(f"[{i + 1}/{len(files)}] {f} (scene_index={scene_index}, {len(beats)} beats)")

        for beat_index in sorted(beats):
            prose = beats[beat_index]
            facts = call_fact_extractor(prose)
            if facts:
                fact_store.insert_facts(db_path, story_id, scene_index, beat_index, facts)
            total_facts += len(facts)
            print(f"    beat {beat_index}: {len(facts)} facts")

    print(f"Done. {total_facts} facts written to {db_path}")


if __name__ == "__main__":
    main()
