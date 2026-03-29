"""Scene file parser — reads .md input files into ParsedScene objects.

Splits on [section-name] markers, parses each section into its typed structure.
See SCHEMA.md for the full input format specification.
"""

from __future__ import annotations

import re
from pathlib import Path

from my_code.models.data_models import (
    AuthorNote,
    Beat,
    CharacterCard,
    Meta,
    ParsedScene,
    SceneSetup,
)


class ParseError(Exception):
    """Raised when a scene file is malformed."""

    def __init__(self, section: str, message: str):
        self.section = section
        super().__init__(f"[{section}]: {message}")


# ---------------------------------------------------------------------------
# Section splitter
# ---------------------------------------------------------------------------

_SECTION_RE = re.compile(r"^\[([a-z][a-z0-9_-]*)\]\s*$", re.MULTILINE)


def _split_sections(text: str) -> dict[str, str]:
    """Split raw file text into {section_name: content} pairs."""
    matches = list(_SECTION_RE.finditer(text))
    if not matches:
        raise ParseError("file", "No [section] markers found")

    sections: dict[str, str] = {}
    for i, m in enumerate(matches):
        name = m.group(1)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections[name] = text[start:end].strip()
    return sections


# ---------------------------------------------------------------------------
# Key-value parser (for meta, scene-setup, character cards, author-note)
# ---------------------------------------------------------------------------

def _parse_kv(text: str) -> dict[str, str]:
    """Parse a block of key: value lines, handling multi-line continuation.

    Multi-line values use either YAML-style `>` folding or simple indentation.
    """
    result: dict[str, str] = {}
    current_key: str | None = None
    current_lines: list[str] = []

    for line in text.splitlines():
        # New key: value line
        kv_match = re.match(r"^([a-z_]+)\s*:\s*(.*)", line)
        if kv_match:
            # Save previous key
            if current_key is not None:
                result[current_key] = _join_lines(current_lines)
            current_key = kv_match.group(1)
            value = kv_match.group(2).strip()
            # Strip YAML fold marker
            if value == ">":
                current_lines = []
            else:
                current_lines = [value]
        elif current_key is not None and line.strip():
            # Continuation line
            current_lines.append(line.strip())
        elif current_key is not None and not line.strip():
            # Blank line inside multi-line — keep as paragraph break
            if current_lines and current_lines[-1] != "":
                current_lines.append("")

    if current_key is not None:
        result[current_key] = _join_lines(current_lines)

    return result


def _join_lines(lines: list[str]) -> str:
    """Join continuation lines, collapsing whitespace but preserving paragraph breaks."""
    # Remove trailing empty lines
    while lines and lines[-1] == "":
        lines.pop()
    return " ".join(l for l in lines if l).strip()


# ---------------------------------------------------------------------------
# Section parsers
# ---------------------------------------------------------------------------

def _parse_meta(kv: dict[str, str]) -> Meta:
    required = ("title", "mode", "output_file", "output_format", "pov")
    for key in required:
        if key not in kv:
            raise ParseError("meta", f"Missing required field: {key}")

    return Meta(
        title=kv["title"],
        version=kv.get("version", "1.0"),
        mode=kv["mode"],
        pause_at=kv.get("pause_at", "beat"),
        output_file=kv["output_file"],
        output_format=kv["output_format"],
        pov=kv["pov"],
        target_length=int(kv.get("target_length", "1500")),
        language=kv.get("language", "en"),
        nsfw=kv.get("nsfw", "false").lower() == "true",
    )


def _parse_author_note(kv: dict[str, str]) -> AuthorNote:
    if "depth" not in kv or "content" not in kv:
        raise ParseError("author-note", "Requires both 'depth' and 'content'")
    return AuthorNote(depth=int(kv["depth"]), content=kv["content"])


def _parse_character(section_name: str, kv: dict[str, str]) -> CharacterCard:
    required = ("name", "role", "triggers", "description", "personality")
    for key in required:
        if key not in kv:
            raise ParseError(section_name, f"Missing required field: {key}")

    triggers = [t.strip() for t in kv["triggers"].split(",")]
    return CharacterCard(
        name=kv["name"],
        role=kv["role"],
        triggers=triggers,
        description=kv["description"],
        personality=kv["personality"],
        backstory=kv.get("backstory"),
        speech_style=kv.get("speech_style"),
    )


def _parse_scene_setup(kv: dict[str, str]) -> SceneSetup:
    return SceneSetup(
        location=kv.get("location"),
        time=kv.get("time"),
        atmosphere=kv.get("atmosphere"),
    )


_BEAT_RE = re.compile(r"^(\d+)\.\s+", re.MULTILINE)


def _parse_beats(text: str) -> list[Beat]:
    """Parse numbered beat list, detecting inline [pause] markers."""
    matches = list(_BEAT_RE.finditer(text))
    if not matches:
        raise ParseError("scene-beats", "No numbered beats found")

    beats: list[Beat] = []
    for i, m in enumerate(matches):
        index = int(m.group(1))
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        raw = text[start:end].strip()

        has_pause = "[pause]" in raw
        # Remove the [pause] marker from the beat text
        beat_text = raw.replace("[pause]", "").strip()
        # Collapse internal whitespace
        beat_text = re.sub(r"\s+", " ", beat_text)

        beats.append(Beat(index=index, text=beat_text, has_pause=has_pause))

    return beats


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def parse_scene_file(file_path: str) -> ParsedScene:
    """Parse a .md scene file into a fully structured ParsedScene object.

    Args:
        file_path: Absolute or relative path to the scene .md file.

    Returns:
        ParsedScene with all sections parsed.

    Raises:
        ParseError: On missing required sections or malformed content.
        FileNotFoundError: If the file does not exist.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Scene file not found: {file_path}")

    raw = path.read_text(encoding="utf-8")

    # Strip comment lines (# ...)
    lines = []
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") and not stripped.startswith("#="):
            # Keep section-internal # comments only if inside a section
            # But top-level # comments are stripped
            pass
        else:
            lines.append(line)
    # Re-join — but we actually want to keep comments inside sections too
    # Simpler: just split on section markers from the raw text
    sections = _split_sections(raw)

    # --- Required sections ---
    required_sections = ("meta", "narrator-prompt", "writing-style", "world-info", "scenario", "scene-beats")
    for name in required_sections:
        if name not in sections:
            raise ParseError(name, "Required section missing")

    # --- Parse each section ---
    meta = _parse_meta(_parse_kv(sections["meta"]))

    narrator_prompt = sections["narrator-prompt"]
    writing_style = sections["writing-style"]
    world_info = sections["world-info"]
    scenario = sections["scenario"]

    # Author note (optional)
    author_note = None
    if "author-note" in sections:
        author_note = _parse_author_note(_parse_kv(sections["author-note"]))

    # Characters — collect all [character-N] sections
    characters: list[CharacterCard] = []
    char_sections = sorted(
        [(name, content) for name, content in sections.items() if name.startswith("character-")],
        key=lambda x: int(x[0].split("-")[1]),
    )
    if not char_sections:
        raise ParseError("character-*", "At least one character card is required")
    for name, content in char_sections:
        characters.append(_parse_character(name, _parse_kv(content)))

    # Scene setup
    scene_setup = SceneSetup()
    if "scene-setup" in sections:
        scene_setup = _parse_scene_setup(_parse_kv(sections["scene-setup"]))

    # Beats
    beats = _parse_beats(sections["scene-beats"])

    # Writing instructions (optional)
    writing_instructions = sections.get("writing-instructions")

    return ParsedScene(
        meta=meta,
        narrator_prompt=narrator_prompt,
        writing_style=writing_style,
        author_note=author_note,
        world_info=world_info,
        characters=characters,
        scene_setup=scene_setup,
        scenario=scenario,
        beats=beats,
        writing_instructions=writing_instructions,
    )
