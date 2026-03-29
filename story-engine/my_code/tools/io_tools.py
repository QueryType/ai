"""I/O tools — parse_scene_file, save_beat, save_final_output, request_human_input.

Owned by OrchestratorAgent. See AGENT_DESIGN.md §2.1.
"""

from __future__ import annotations

import json
from pathlib import Path

from strands import tool

from my_code.models.data_models import HumanInput, Meta
from my_code.parser import parse_scene_file as _parse_scene_file


@tool
def parse_scene_file(file_path: str) -> str:
    """Parse a .md scene file into a structured ParsedScene JSON.

    Args:
        file_path: Path to the scene .md file.

    Returns:
        JSON string of the ParsedScene (serialised for agent consumption).
    """
    from dataclasses import asdict

    scene = _parse_scene_file(file_path)
    return json.dumps(asdict(scene), ensure_ascii=False, indent=2)


@tool
def save_beat(beat_index: int, prose: str) -> str:
    """Record a completed beat's prose to the in-memory beat list.

    This is a logical marker — actual storage is managed by the orchestrator.

    Args:
        beat_index: 1-based index of the beat.
        prose: The prose text for this beat.

    Returns:
        Confirmation message.
    """
    return f"Beat {beat_index} saved ({len(prose.split())} words)."


@tool
def save_final_output(completed_beats: str, meta_json: str) -> str:
    """Assemble all beat prose and write the final output file.

    Args:
        completed_beats: JSON array of prose strings in beat order.
        meta_json: JSON string of Meta fields (title, output_file, output_format, pov).

    Returns:
        Path to the written file.
    """
    beats: list[str] = json.loads(completed_beats)
    meta: dict = json.loads(meta_json)

    output_format = meta.get("output_format", "prose")
    title = meta.get("title", "Untitled")
    output_file = meta.get("output_file", "output/story.md")

    parts: list[str] = []

    if output_format == "adventure":
        parts.append(f"# {title}\n")
        for i, prose in enumerate(beats, 1):
            parts.append(f"## Beat {i}\n\n{prose}\n")
    elif output_format == "script":
        parts.append(f"# {title}\n")
        for i, prose in enumerate(beats, 1):
            parts.append(f"---\n**BEAT {i}**\n\n{prose}\n")
    else:
        # prose — seamless, no headers
        parts.append(f"# {title}\n")
        for prose in beats:
            parts.append(f"{prose}\n")

    content = "\n".join(parts)

    path = Path(output_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

    return str(path)


@tool
def request_human_input(beat_index: int, beat_total: int, prose_output: str) -> str:
    """Pause execution and prompt the human for input.

    Displays the current beat output and waits for human direction.

    Args:
        beat_index: 1-based index of the current beat.
        beat_total: Total number of beats in the scene.
        prose_output: The prose written for this beat.

    Returns:
        JSON-serialised HumanInput (action + optional text).
    """
    print(f"\n{'='*60}")
    print(f"  Beat {beat_index}/{beat_total} complete")
    print(f"{'='*60}\n")
    print(prose_output)
    print(f"\n{'─'*60}")
    print("Commands: Enter=continue | /skip | /stop | /retry | free text=redirect")

    user_input = input("> ").strip()

    if not user_input:
        result = HumanInput(action="continue")
    elif user_input == "/skip":
        result = HumanInput(action="skip")
    elif user_input == "/stop":
        result = HumanInput(action="stop")
    elif user_input == "/retry":
        result = HumanInput(action="retry")
    else:
        result = HumanInput(action="redirect", text=user_input)

    return json.dumps({"action": result.action, "text": result.text})
