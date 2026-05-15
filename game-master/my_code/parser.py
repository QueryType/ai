"""Adventure scenario file parser — reads .md files into AdventureScene objects.

Same [section-name] format as story-engine. Drops [scene-beats]; adds [memory] and [opening].
"""

from __future__ import annotations

import re
from pathlib import Path

from my_code.models.data_models import AdventureScene, CharacterCard, Meta


class ParseError(Exception):
    def __init__(self, section: str, message: str):
        self.section = section
        super().__init__(f"[{section}]: {message}")


# ---------------------------------------------------------------------------
# Section splitter
# ---------------------------------------------------------------------------

_SECTION_RE = re.compile(r"^\[([a-z][a-z0-9_-]*)\]\s*$", re.MULTILINE)


def _split_sections(text: str) -> dict[str, str]:
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
# Key-value parser
# ---------------------------------------------------------------------------

def _parse_kv(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    current_key: str | None = None
    current_lines: list[str] = []

    for line in text.splitlines():
        kv_match = re.match(r"^([a-z_]+)\s*:\s*(.*)", line)
        if kv_match:
            if current_key is not None:
                result[current_key] = _join_lines(current_lines)
            current_key = kv_match.group(1)
            value = kv_match.group(2).strip()
            current_lines = [] if value == ">" else [value]
        elif current_key is not None and line.strip():
            current_lines.append(line.strip())
        elif current_key is not None and not line.strip():
            if current_lines and current_lines[-1] != "":
                current_lines.append("")

    if current_key is not None:
        result[current_key] = _join_lines(current_lines)
    return result


def _join_lines(lines: list[str]) -> str:
    while lines and lines[-1] == "":
        lines.pop()
    return " ".join(l for l in lines if l).strip()


# ---------------------------------------------------------------------------
# Section parsers
# ---------------------------------------------------------------------------

def _parse_meta(kv: dict[str, str]) -> tuple[Meta, str]:
    """Returns (Meta, scene_image_path)."""
    if "title" not in kv:
        raise ParseError("meta", "Missing required field: title")
    return Meta(
        title=kv["title"],
        mode=kv.get("mode", "interactive"),
        pov=kv.get("pov", "second-person"),
        language=kv.get("language", "en"),
        nsfw=kv.get("nsfw", "false").lower() == "true",
    ), kv.get("scene_image", "")


def _parse_character(section_name: str, kv: dict[str, str]) -> CharacterCard:
    for key in ("name", "role", "triggers", "description", "personality"):
        if key not in kv:
            raise ParseError(section_name, f"Missing required field: {key}")
    triggers = [t.strip() for t in kv["triggers"].split(",")]
    return CharacterCard(
        name=kv["name"],
        role=kv["role"],
        triggers=triggers,
        description=kv["description"],
        personality=kv["personality"],
        backstory=kv.get("backstory", ""),
        speech_style=kv.get("speech_style", ""),
        portrait=kv.get("portrait", ""),
    )


def _parse_author_note(kv: dict[str, str]) -> tuple[str, int]:
    """Returns (content, depth)."""
    content = kv.get("content", "")
    depth = int(kv.get("depth", "4"))
    return content, depth


def _parse_scene_setup(kv: dict[str, str]) -> str:
    parts = []
    if kv.get("location"):
        parts.append(f"Location: {kv['location']}")
    if kv.get("time"):
        parts.append(f"Time: {kv['time']}")
    if kv.get("atmosphere"):
        parts.append(f"Atmosphere: {kv['atmosphere']}")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

_REQUIRED = ("meta", "narrator-prompt", "writing-style", "world-info", "scenario")


def parse_scene_file(file_path: str) -> AdventureScene:
    """Parse an adventure .md scenario file into an AdventureScene.

    Args:
        file_path: Path to the scenario .md file.

    Returns:
        AdventureScene with all sections parsed.

    Raises:
        ParseError: On missing required sections or malformed content.
        FileNotFoundError: If the file does not exist.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Scenario file not found: {file_path}")

    raw = path.read_text(encoding="utf-8")
    sections = _split_sections(raw)

    for name in _REQUIRED:
        if name not in sections:
            raise ParseError(name, "Required section missing")

    meta, scene_image = _parse_meta(_parse_kv(sections["meta"]))

    # Characters
    char_sections = sorted(
        [(n, c) for n, c in sections.items() if n.startswith("character-")],
        key=lambda x: int(x[0].split("-")[1]),
    )
    if not char_sections:
        raise ParseError("character-*", "At least one character card is required")
    characters = [_parse_character(n, _parse_kv(c)) for n, c in char_sections]

    # Scene setup
    scene_setup = ""
    if "scene-setup" in sections:
        scene_setup = _parse_scene_setup(_parse_kv(sections["scene-setup"]))

    # Author note
    author_note = ""
    author_note_depth = 4
    if "author-note" in sections:
        author_note, author_note_depth = _parse_author_note(_parse_kv(sections["author-note"]))

    return AdventureScene(
        meta=meta,
        narrator_prompt=sections["narrator-prompt"],
        writing_style=sections["writing-style"],
        world_info=sections["world-info"],
        characters=characters,
        scene_setup=scene_setup,
        scenario=sections["scenario"],
        memory=sections.get("memory", ""),
        opening=sections.get("opening", ""),
        author_note=author_note,
        author_note_depth=author_note_depth,
        scene_image=scene_image,
    )
