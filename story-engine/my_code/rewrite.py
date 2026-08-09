"""rewrite.py — Post-run beat rewrite and coherence validation tool.

Modes:
  --map          Interactive: mark beat boundaries in an existing output file (no LLM).
  --validate     Coherence-only pass on all beats, report flagged beats (no rewrite).
  --beat N       Rewrite beat N, then coherence-check subsequent beats (report only).
  --from-here    Used with --beat N: also re-narrate beats N+1..end.

Usage:
  python -m my_code.rewrite scene.md --map
  python -m my_code.rewrite scene.md --validate
  python -m my_code.rewrite scene.md --validate --from-beat 3
  python -m my_code.rewrite scene.md --beat 3
  python -m my_code.rewrite scene.md --beat 3 --from-here
  python -m my_code.rewrite scene.md --beat 3 --story output/custom.md
"""

from __future__ import annotations

import argparse
import gc
import json
import logging
import re
import sys
from dataclasses import asdict
from pathlib import Path

from my_code.agents.evaluator import create_coherence_checker
from my_code.agents.narrator import create_narrator
from my_code.agents.summariser import create_summariser
from my_code.agents.orchestrator import (
    _narrate_and_evaluate,
    _normalize_summary_for_budget,
    _parse_output_beats,
    _summarise_beat,
    _trim_narrator_context,
    _trim_prior_summary,
    _cap_prior_summary_chars,
)
from my_code.models.data_models import NarratorContext, ParsedScene
from my_code.parser import parse_scene_file
from my_code.tools.lore_tools import build_lore_block, get_character_card, scan_for_triggers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

_PAGE_SIZE = 30  # lines per page in --map display


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Story Engine — Rewrite Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("scene", metavar="SCENE.MD", help="Scene file used to generate the story")
    p.add_argument("--map", action="store_true", help="Interactively add beat markers to output file")
    p.add_argument("--show", action="store_true", help="Show current beat marker positions and exit")
    p.add_argument("--validate", action="store_true", help="Coherence-check all beats, report issues")
    p.add_argument("--from-beat", type=int, default=1, metavar="N",
                   help="With --validate: start coherence check from beat N (default: 1)")
    p.add_argument("--beat", type=int, default=None, metavar="N",
                   help="Rewrite beat N")
    p.add_argument("--from-here", action="store_true",
                   help="With --beat N: also re-narrate beats N+1..end")
    p.add_argument("--story", metavar="PATH",
                   help="Override story output file path (default: from scene meta.output_file)")
    return p.parse_args()


# ---------------------------------------------------------------------------
# --map: interactive beat boundary marking
# ---------------------------------------------------------------------------

def cmd_map(scene: ParsedScene, story_path: str) -> None:
    """Display story with line numbers, collect beat boundaries, insert markers."""
    path = Path(story_path)
    if not path.exists():
        print(f"ERROR: Story file not found: {story_path}")
        sys.exit(1)

    lines = path.read_text(encoding="utf-8").splitlines()
    total_lines = len(lines)
    beat_count = len(scene.beats)

    # Check if markers already exist
    existing = any(re.search(r"<!--\s*beat:\d+\s*-->", l) for l in lines)
    if existing:
        print(f"Beat markers already present in {story_path}.")
        raw = input("Re-map anyway? [y/N] ").strip().lower()
        if raw not in ("y", "yes"):
            print("Aborted.")
            return
        # Strip existing markers before re-mapping
        lines = [l for l in lines if not re.match(r"^\s*<!--\s*beat:\d+\s*-->\s*$", l)]
        total_lines = len(lines)

    print(f"\nStory: {story_path}  ({total_lines} lines, {beat_count} beats)")
    print("─" * 60)

    # Display story paginated
    _display_paginated(lines)

    # Collect boundary line numbers (beat N ends at line X → beat N+1 starts at X+1)
    boundaries: list[int] = []
    for i in range(1, beat_count):
        while True:
            try:
                raw = input(f"\nBeat {i} ends at line: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nAborted.")
                return
            if not raw.isdigit():
                print("  Enter a line number.")
                continue
            ln = int(raw)
            if ln < 1 or ln >= total_lines:
                print(f"  Must be between 1 and {total_lines - 1}.")
                continue
            if boundaries and ln <= boundaries[-1]:
                print(f"  Must be after beat {i - 1} boundary (line {boundaries[-1]}).")
                continue
            boundaries.append(ln)
            break

    # boundaries[i] = last line of beat i+1 (1-based line numbers)
    # Beat 1 starts at line 1, beat 2 starts at boundaries[0]+1, etc.
    beat_starts = [0] + [b for b in boundaries]  # 0-indexed line positions

    # Insert markers working backwards to preserve line numbers
    new_lines = list(lines)
    for i, start in enumerate(beat_starts):
        beat_num = i + 1
        marker = f"<!-- beat:{beat_num} -->"
        new_lines.insert(start, marker)

    path.write_text("\n".join(new_lines), encoding="utf-8")
    print(f"\nMarkers written to {story_path}")
    print("You can now run: python -m my_code.rewrite scene.md --validate")


def _display_paginated(lines: list[str]) -> None:
    """Display lines with line numbers, paginated."""
    total = len(lines)
    page = 0
    while True:
        start = page * _PAGE_SIZE
        if start >= total:
            break
        end = min(start + _PAGE_SIZE, total)
        for i in range(start, end):
            print(f"  L{i + 1:<5} {lines[i]}")
        if end >= total:
            print("  (end of file)")
            break
        try:
            raw = input(f"\n  [Lines {start + 1}–{end} of {total}] Enter=next page | q=done: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            break
        if raw == "q":
            break
        page += 1


# ---------------------------------------------------------------------------
# Shared: rebuild prior_summary from existing beat prose
# ---------------------------------------------------------------------------

def _rebuild_prior_summary(beats: dict[int, str], up_to_beat: int) -> str:
    """Re-summarise beats 1..up_to_beat-1 to rebuild prior_summary.

    Uses the 9B summariser — cheap sequential calls, same as the main engine.
    """
    prior_summary = ""
    for idx in range(1, up_to_beat):
        if idx not in beats:
            continue
        prose = beats[idx]
        gc.collect()
        summariser = create_summariser()
        logger.info("Rebuilding summary for beat %d...", idx)
        capped = _summarise_beat(summariser, prose, idx)
        prior_summary += f"\n\n### Beat {idx} Summary\n{capped}"
    return prior_summary


# ---------------------------------------------------------------------------
# Shared: inject existing beat prose into narrator message history
# ---------------------------------------------------------------------------

def _build_narrator_prompt_for_beat(
    beat_index: int,
    beat_total: int,
    beat_instruction: str,
    lore_context: str,
    prior_story_summary: str | None,
) -> str:
    """Reconstruct the narrator user-turn prompt for an already-written beat."""
    parts = [f"Write prose for beat {beat_index}/{beat_total}.\n"]
    if prior_story_summary:
        parts.append(f"## Story So Far\n{prior_story_summary}\n")
    parts.append(f"## Beat Instruction\n{beat_instruction}\n")
    if lore_context:
        parts.append(f"## Lore Context\n{lore_context}\n")
    return "\n".join(parts)


def _inject_prior_beats(
    narrator,
    scene: ParsedScene,
    beats: dict[int, str],
    up_to_beat: int,
    prior_summary: str,
    characters_json: str,
) -> None:
    """Inject beats 1..up_to_beat-1 directly into narrator.messages.

    No LLM calls — we fake the conversation turns so the narrator has context
    for coherent continuation. KV cache won't be warm (different process) but
    the conversation history will be correct.
    """
    beat_total = len(scene.beats)
    running_summary: str | None = None

    for idx in range(1, up_to_beat):
        if idx not in beats:
            continue
        beat = next((b for b in scene.beats if b.index == idx), None)
        if beat is None:
            continue

        matched_names = json.loads(scan_for_triggers(beat.text, characters_json))
        cards = []
        for name in matched_names:
            card = get_character_card(name, characters_json)
            if not card.startswith("Character not found"):
                cards.append(card)
        lore_context = build_lore_block(json.dumps(cards))

        prompt = _build_narrator_prompt_for_beat(
            idx, beat_total, beat.text, lore_context, running_summary
        )
        prose = beats[idx]

        # Append as a user→assistant turn directly into the narrator's message list.
        # Strands internal format uses content as a list of typed blocks, not a plain string.
        narrator.messages.append({"role": "user", "content": [{"text": prompt}]})
        narrator.messages.append({"role": "assistant", "content": [{"text": prose}]})

        # Advance running summary so each injected beat sees prior context
        if idx < up_to_beat - 1:
            # Extract the beat's entry from the already-rebuilt prior_summary
            m = re.search(
                rf"### Beat {idx} Summary\n(.*?)(?=\n\n### Beat|\Z)",
                prior_summary,
                re.DOTALL,
            )
            if m:
                running_summary = (running_summary or "") + f"\n\n### Beat {idx} Summary\n{m.group(1).strip()}"

    logger.info(
        "Injected %d prior beat(s) into narrator history (%d messages)",
        up_to_beat - 1,
        len(narrator.messages),
    )


# ---------------------------------------------------------------------------
# Shared: coherence check on a range of beats
# ---------------------------------------------------------------------------

def _run_coherence_pass(
    beats: dict[int, str],
    from_beat: int,
    prior_summary: str,
    scene: ParsedScene,
) -> list[tuple[int, str]]:
    """Run coherence-only evaluation on beats from_beat..end.

    Returns list of (beat_index, reason) for beats that failed coherence.
    """
    flags: list[tuple[int, str]] = []
    running_summary = prior_summary  # grows as we check each beat

    for idx in sorted(k for k in beats if k >= from_beat):
        prose = beats[idx]
        trimmed = _trim_prior_summary(running_summary)
        capped = _cap_prior_summary_chars(trimmed, max_chars=1800)

        prompt = (
            f"Check coherence for beat {idx}.\n\n"
            f"## Prose\n{prose}\n\n"
            f"## Prior Beats Summary\n{capped if capped else '(no prior context)'}"
        )

        gc.collect()
        checker = create_coherence_checker()
        try:
            result = checker(prompt)
            raw = str(result)
            j_start = raw.find("{")
            j_end = raw.rfind("}") + 1
            if j_start >= 0 and j_end > j_start:
                data = json.loads(raw[j_start:j_end])
                coherent = data.get("coherent", True)
                reason = data.get("reason", "")
                issues = data.get("issues", [])
                if not coherent:
                    detail = "; ".join(issues) if issues else reason
                    flags.append((idx, detail))
                    logger.info("Beat %d: coherence FAIL — %s", idx, detail)
                else:
                    logger.info("Beat %d: coherence OK", idx)
            else:
                logger.warning("Beat %d: coherence checker returned unparseable output", idx)
        except Exception as exc:
            logger.warning("Beat %d: coherence checker error — %s", idx, exc)

        # Summarise this beat and add to running_summary so subsequent beats
        # can be checked against it. This is the correct fix: the pre-built
        # prior_summary only covers beats before from_beat; beats within the
        # checked range must be accumulated as we go.
        gc.collect()
        summariser = create_summariser()
        try:
            raw_sum = str(summariser(f"Summarise beat {idx}:\n\n{prose}")).strip()
            capped_sum = _normalize_summary_for_budget(raw_sum)
            running_summary += f"\n\n### Beat {idx} Summary\n{capped_sum}"
        except Exception as exc:
            logger.warning("Beat %d: summariser error during coherence pass — %s", idx, exc)

    return flags


def _print_coherence_report(flags: list[tuple[int, str]], total_checked: int) -> None:
    print(f"\n{'═' * 60}")
    print(f"  COHERENCE REPORT  ({total_checked} beat(s) checked)")
    print(f"{'═' * 60}")
    if not flags:
        print("  All beats coherent — no contradictions found.")
    else:
        for beat_idx, reason in flags:
            print(f"\n  Beat {beat_idx}: FLAGGED")
            print(f"    {reason}")
        print(f"\n  {len(flags)} beat(s) flagged.")
        print("  To rewrite a flagged beat: python -m my_code.rewrite scene.md --beat N")
    print()


# ---------------------------------------------------------------------------
# --validate
# ---------------------------------------------------------------------------

def cmd_validate(scene: ParsedScene, story_path: str, from_beat: int) -> None:
    """Coherence-only pass on all (or tail) beats. Report only, no rewrite."""
    try:
        beats = _parse_output_beats(story_path)
    except ValueError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    beat_count = len(scene.beats)
    print(f"\nValidating coherence: {story_path}")
    print(f"  Beats in file: {sorted(beats.keys())}  |  Checking from beat {from_beat}")

    # Rebuild prior_summary for beats before from_beat
    print("  Rebuilding beat summaries...")
    prior_summary = _rebuild_prior_summary(beats, from_beat)

    # Run coherence pass
    flags = _run_coherence_pass(beats, from_beat, prior_summary, scene)
    checked = len([k for k in beats if k >= from_beat])
    _print_coherence_report(flags, checked)


# ---------------------------------------------------------------------------
# --beat N [--from-here]
# ---------------------------------------------------------------------------

def cmd_rewrite_beat(
    scene: ParsedScene,
    story_path: str,
    beat_num: int,
    from_here: bool,
) -> None:
    """Rewrite beat N. Optionally cascade to re-narrate N+1..end."""
    try:
        beats = _parse_output_beats(story_path)
    except ValueError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    if beat_num not in beats:
        print(f"ERROR: Beat {beat_num} not found in {story_path}. Available: {sorted(beats.keys())}")
        sys.exit(1)

    beat_obj = next((b for b in scene.beats if b.index == beat_num), None)
    if beat_obj is None:
        print(f"ERROR: Beat {beat_num} not in scene file {scene.meta.title}")
        sys.exit(1)

    beat_total = len(scene.beats)
    characters_json = json.dumps([asdict(c) for c in scene.characters], ensure_ascii=False)

    print(f"\nRewriting beat {beat_num}/{beat_total} in: {story_path}")

    # 1. Rebuild prior_summary from beats 1..N-1
    print("  Rebuilding beat summaries (beats 1 to {})...".format(beat_num - 1))
    prior_summary = _rebuild_prior_summary(beats, beat_num)

    # 2. Create narrator (fresh — different process, KV cache not warm, that's OK)
    narrator = create_narrator(scene)

    # 3. Inject beats 1..N-1 as fake conversation history
    if beat_num > 1:
        _inject_prior_beats(narrator, scene, beats, beat_num, prior_summary, characters_json)

    # 4. Build lore context for beat N
    matched_names = json.loads(scan_for_triggers(beat_obj.text, characters_json))
    cards = []
    for name in matched_names:
        card = get_character_card(name, characters_json)
        if not card.startswith("Character not found"):
            cards.append(card)
    lore_context = build_lore_block(json.dumps(cards))

    # 5. Narrate + evaluate beat N (full loop with retries)
    ctx = NarratorContext(
        beat_instruction=beat_obj.text,
        lore_context=lore_context,
        beat_index=beat_num,
        beat_total=beat_total,
        prior_story_summary=prior_summary or None,
    )

    print(f"  Narrating beat {beat_num}...")
    prose, retry_count, last_narrator_in, beat_start_state = _narrate_and_evaluate(
        narrator, ctx, scene.writing_style, prior_summary
    )
    print(f"  Done ({len(prose.split())} words, {retry_count} retries)")

    # 6. Update beats dict with new prose
    beats[beat_num] = prose

    if from_here:
        # Re-narrate N+1..end
        beats, prior_summary = _cascade_renarrate(
            narrator, scene, beats, beat_num, prose, prior_summary,
            characters_json, last_narrator_in,
        )
    else:
        # Rebuild summary for beat N and coherence-check N+1..end
        if beat_num < beat_total:
            gc.collect()
            summariser = create_summariser()
            beat_summary = _summarise_beat(summariser, prose, beat_num)
            prior_summary += f"\n\n### Beat {beat_num} Summary\n{beat_summary}"

            print(f"\n  Coherence-checking beats {beat_num + 1}..{beat_total}...")
            flags = _run_coherence_pass(beats, beat_num + 1, prior_summary, scene)
            checked = len([k for k in beats if k > beat_num])
            _print_coherence_report(flags, checked)

    # 7. Write updated output file
    _write_updated_output(beats, scene, story_path)
    print(f"\n  Output updated: {story_path}")


def _cascade_renarrate(
    narrator,
    scene: ParsedScene,
    beats: dict[int, str],
    from_beat: int,
    from_prose: str,
    prior_summary: str,
    characters_json: str,
    last_narrator_in: int,
) -> tuple[dict[int, str], str]:
    """Re-narrate beats from_beat+1 onward, same logic as the main engine."""
    beat_total = len(scene.beats)

    # Summarise the rewritten beat before continuing
    gc.collect()
    summariser = create_summariser()
    beat_summary = _summarise_beat(summariser, from_prose, from_beat)
    prior_summary += f"\n\n### Beat {from_beat} Summary\n{beat_summary}"

    for beat in scene.beats:
        if beat.index <= from_beat:
            continue

        logger.info("Re-narrating beat %d/%d", beat.index, beat_total)

        _trim_narrator_context(narrator, last_narrator_in)

        matched_names = json.loads(scan_for_triggers(beat.text, characters_json))
        cards = []
        for name in matched_names:
            card = get_character_card(name, characters_json)
            if not card.startswith("Character not found"):
                cards.append(card)
        lore_context = build_lore_block(json.dumps(cards))

        ctx = NarratorContext(
            beat_instruction=beat.text,
            lore_context=lore_context,
            beat_index=beat.index,
            beat_total=beat_total,
        )

        gc.collect()
        prose, retry_count, last_narrator_in, _ = _narrate_and_evaluate(
            narrator, ctx, scene.writing_style, prior_summary
        )
        beats[beat.index] = prose
        print(f"  Beat {beat.index}/{beat_total}: {len(prose.split())} words")

        is_last = beat.index == scene.beats[-1].index
        if not is_last:
            gc.collect()
            summariser = create_summariser()
            beat_summary = _summarise_beat(summariser, prose, beat.index)
            prior_summary += f"\n\n### Beat {beat.index} Summary\n{beat_summary}"

    return beats, prior_summary


# ---------------------------------------------------------------------------
# --show
# ---------------------------------------------------------------------------

def cmd_show(story_path: str) -> None:
    """Print current beat marker positions."""
    path = Path(story_path)
    if not path.exists():
        print(f"ERROR: Story file not found: {story_path}")
        sys.exit(1)

    lines = path.read_text(encoding="utf-8").splitlines()
    marker_re = re.compile(r"<!--\s*beat:(\d+)\s*-->")

    found = []
    for i, line in enumerate(lines, 1):
        m = marker_re.match(line.strip())
        if m:
            found.append((int(m.group(1)), i))

    if not found:
        print(f"No beat markers found in {story_path}.")
        print("Run: python -m my_code.rewrite scene.md --map")
        return

    print(f"\nBeat markers in {story_path}:")
    for beat_num, line_num in found:
        # Show a short excerpt of the first non-empty line after the marker
        excerpt = ""
        for line in lines[line_num:line_num + 3]:
            stripped = line.strip()
            if stripped and not stripped.startswith("<!--") and not stripped.startswith("#"):
                excerpt = stripped[:60] + ("..." if len(stripped) > 60 else "")
                break
        print(f"  Beat {beat_num}  →  line {line_num:<5}  {excerpt}")
    print()


# ---------------------------------------------------------------------------
# Write updated output file preserving beat markers
# ---------------------------------------------------------------------------

def _write_updated_output(beats: dict[int, str], scene: ParsedScene, story_path: str) -> None:
    """Reassemble the output file with updated beat prose, preserving markers."""
    output_format = scene.meta.output_format
    title = scene.meta.title

    parts: list[str] = [f"# {title}\n"]
    for i in sorted(beats.keys()):
        prose = beats[i]
        if output_format == "adventure":
            parts.append(f"<!-- beat:{i} -->\n## Beat {i}\n\n{prose}\n")
        elif output_format == "script":
            parts.append(f"<!-- beat:{i} -->\n---\n**BEAT {i}**\n\n{prose}\n")
        else:
            parts.append(f"<!-- beat:{i} -->\n{prose}\n")

    Path(story_path).write_text("\n".join(parts), encoding="utf-8")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    args = _parse_args()

    scene = parse_scene_file(args.scene)
    story_path = args.story or scene.meta.output_file

    if args.show:
        cmd_show(story_path)

    elif args.map:
        cmd_map(scene, story_path)

    elif args.validate:
        cmd_validate(scene, story_path, from_beat=args.from_beat)

    elif args.beat is not None:
        cmd_rewrite_beat(scene, story_path, args.beat, from_here=args.from_here)

    else:
        print("ERROR: Specify one of --map, --validate, or --beat N")
        print("Run with --help for usage.")
        sys.exit(1)


if __name__ == "__main__":
    main()
