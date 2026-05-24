"""Chat input file parser — reads .md chat input files into ParsedChat objects.

Splits on [section-name] markers, parses each section into its typed structure.
See CHAT_SCHEMA.md for the full input format specification.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class ChatMeta:
    title: str
    mode: str                    # must be "chat"
    output_transcript: str
    output_runlog: str
    version: str = "1.0"
    language: str = "en"
    nsfw: bool = False


@dataclass
class ChatConfig:
    max_turns: int = 50          # 0 = unlimited
    pause_every: int = 5         # 0 = never auto-pause
    history_window: int = 20     # turns to include in GM context
    history_summary_chars: int = 700  # bounded summary for turns older than history_window
    ending_countdown_turns: int = 2  # start landing guidance this many turns before max_turns
    ending_grace_turns: int = 2  # extra turns allowed past max_turns to finish the scene cleanly
    orchestrator_history_window: int = 8  # smaller selector context budget
    opening_speaker: str = "auto"
    turn_selection: str = "rules"
    max_retries: int = 2
    response_length: str = "2-4 sentences"  # injected into turn prompt; "free" = no constraint


@dataclass
class CharacterCard:
    name: str
    role: str                    # player-character | npc | antagonist | neutral
    triggers: list[str]
    description: str
    personality: str
    speaking_weight: float = 1.0
    can_be_taken_over: bool = True
    backstory: str | None = None
    speech_style: str | None = None


@dataclass
class ChatPhase:
    name: str
    start_turn: int
    end_turn: int
    goal: str = ""
    pace: str | None = None
    focus_characters: list[str] = field(default_factory=list)
    required_characters: list[str] = field(default_factory=list)
    avoid_characters: list[str] = field(default_factory=list)
    guidance: str | None = None
    max_consecutive_turns: int = 2


@dataclass
class ParsedChat:
    meta: ChatMeta
    config: ChatConfig
    world_info: str
    gm_prompt: str
    writing_style: str
    scenario: str
    characters: list[CharacterCard] = field(default_factory=list)
    phases: list[ChatPhase] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class ParseError(Exception):
    def __init__(self, section: str, message: str):
        self.section = section
        super().__init__(f"[{section}]: {message}")


# ---------------------------------------------------------------------------
# Section splitter
# ---------------------------------------------------------------------------

_SECTION_RE = re.compile(r"^\[([a-z][a-z0-9_-]*)\]\s*$", re.MULTILINE)


def _strip_comments(text: str) -> str:
    """Remove lines whose stripped content starts with '#'."""
    lines = []
    for line in text.splitlines():
        if line.strip().startswith("#"):
            lines.append("")           # preserve line count for debugging
        else:
            lines.append(line)
    return "\n".join(lines)


def _split_sections(text: str) -> dict[str, str]:
    """Split raw file text into {section_name: body} pairs."""
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
    """Parse key: value lines with multi-line continuation and YAML '>' folding."""
    result: dict[str, str] = {}
    current_key: str | None = None
    current_lines: list[str] = []

    for line in text.splitlines():
        if line.strip().startswith("#"):
            continue
        kv_match = re.match(r"^([a-z_]+)\s*:\s*(.*)", line)
        if kv_match:
            if current_key is not None:
                result[current_key] = _join_lines(current_lines)
            current_key = kv_match.group(1)
            value = kv_match.group(2).strip()
            current_lines = [] if value == ">" else [value]
        elif current_key is not None:
            if line.strip():
                current_lines.append(line.strip())
            elif current_lines and current_lines[-1] != "":
                current_lines.append("")   # paragraph break

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

def _parse_meta(kv: dict[str, str]) -> ChatMeta:
    for key in ("title", "mode", "output_transcript", "output_runlog"):
        if key not in kv:
            raise ParseError("meta", f"Missing required field: {key}")
    if kv["mode"] != "chat":
        raise ParseError("meta", f"mode must be 'chat', got '{kv['mode']}'")
    return ChatMeta(
        title=kv["title"],
        mode=kv["mode"],
        output_transcript=kv["output_transcript"],
        output_runlog=kv["output_runlog"],
        version=kv.get("version", "1.0"),
        language=kv.get("language", "en"),
        nsfw=kv.get("nsfw", "false").lower() == "true",
    )


def _parse_config(kv: dict[str, str]) -> ChatConfig:
    return ChatConfig(
        max_turns=int(kv.get("max_turns", "50")),
        pause_every=int(kv.get("pause_every", "5")),
        history_window=int(kv.get("history_window", "20")),
        history_summary_chars=int(kv.get("history_summary_chars", "700")),
        ending_countdown_turns=int(kv.get("ending_countdown_turns", "2")),
        ending_grace_turns=int(kv.get("ending_grace_turns", "2")),
        orchestrator_history_window=int(kv.get("orchestrator_history_window", "8")),
        opening_speaker=kv.get("opening_speaker", "auto"),
        turn_selection=kv.get("turn_selection", "rules"),
        max_retries=int(kv.get("max_retries", "2")),
        response_length=kv.get("response_length", "2-4 sentences"),
    )


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
        speaking_weight=float(kv.get("speaking_weight", "1.0")),
        can_be_taken_over=kv.get("can_be_taken_over", "true").lower() == "true",
        backstory=kv.get("backstory"),
        speech_style=kv.get("speech_style"),
    )


def _parse_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _parse_turn_range(section_name: str, value: str | None) -> tuple[int, int]:
    if not value:
        raise ParseError(section_name, "Missing required field: turns (example: 1-8)")
    match = re.match(r"^(\d+)\s*-\s*(\d+)$", value.strip())
    if not match:
        raise ParseError(section_name, f"Invalid turns range '{value}' (expected start-end)")

    start_turn = int(match.group(1))
    end_turn = int(match.group(2))
    if start_turn < 1 or end_turn < start_turn:
        raise ParseError(section_name, f"Invalid turns range '{value}'")
    return start_turn, end_turn


def _parse_phase(section_name: str, kv: dict[str, str]) -> ChatPhase:
    for key in ("name", "turns"):
        if key not in kv:
            raise ParseError(section_name, f"Missing required field: {key}")

    start_turn, end_turn = _parse_turn_range(section_name, kv.get("turns"))
    max_consecutive_turns = int(kv.get("max_consecutive_turns", "2"))
    if max_consecutive_turns < 1:
        raise ParseError(section_name, "max_consecutive_turns must be >= 1")

    return ChatPhase(
        name=kv["name"],
        start_turn=start_turn,
        end_turn=end_turn,
        goal=kv.get("goal", ""),
        pace=kv.get("pace"),
        focus_characters=_parse_list(kv.get("focus_characters")),
        required_characters=_parse_list(kv.get("required_characters")),
        avoid_characters=_parse_list(kv.get("avoid_characters")),
        guidance=kv.get("guidance"),
        max_consecutive_turns=max_consecutive_turns,
    )


def _validate_phases(phases: list[ChatPhase], config: ChatConfig) -> None:
    if not phases:
        return

    ordered = sorted(phases, key=lambda phase: phase.start_turn)
    for index, phase in enumerate(ordered):
        if index == 0:
            continue
        prev = ordered[index - 1]
        if phase.start_turn <= prev.end_turn:
            raise ParseError(
                "phase-*",
                f"Phase '{phase.name}' overlaps '{prev.name}'",
            )

    if config.max_turns > 0 and ordered[-1].end_turn > config.max_turns:
        raise ParseError(
            "phase-*",
            f"Last phase ends at turn {ordered[-1].end_turn}, beyond max_turns={config.max_turns}",
        )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def parse_chat_file(file_path: str) -> ParsedChat:
    """Parse a .md chat input file into a fully structured ParsedChat object.

    Raises:
        FileNotFoundError: If the file does not exist.
        ParseError: On missing required sections or malformed content.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Chat input file not found: {file_path}")

    raw = path.read_text(encoding="utf-8")
    cleaned = _strip_comments(raw)
    sections = _split_sections(cleaned)

    for name in ("meta", "chat-config", "world-info", "gm-prompt", "writing-style", "scenario"):
        if name not in sections:
            raise ParseError(name, "Required section missing")

    char_sections = sorted(
        [(n, c) for n, c in sections.items() if re.match(r"^character-\d+$", n)],
        key=lambda x: int(x[0].split("-")[1]),
    )
    if len(char_sections) < 2:
        raise ParseError("character-*", "At least 2 character cards are required")

    phase_sections = sorted(
        [(n, c) for n, c in sections.items() if re.match(r"^phase-\d+$", n)],
        key=lambda x: int(x[0].split("-")[1]),
    )

    config = _parse_config(_parse_kv(sections["chat-config"]))
    phases = [_parse_phase(n, _parse_kv(c)) for n, c in phase_sections]
    _validate_phases(phases, config)

    return ParsedChat(
        meta=_parse_meta(_parse_kv(sections["meta"])),
        config=config,
        world_info=sections["world-info"],
        gm_prompt=sections["gm-prompt"],
        writing_style=sections["writing-style"],
        scenario=sections["scenario"],
        characters=[_parse_character(n, _parse_kv(c)) for n, c in char_sections],
        phases=phases,
    )


# ---------------------------------------------------------------------------
# __main__ — quick parse test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    from pathlib import Path as _Path

    target = sys.argv[1] if len(sys.argv) > 1 else "examples/ashenveil_chat1.md"

    # Resolve relative to repo root (parent of src/)
    root = _Path(__file__).parent.parent.parent
    file_path = root / target

    print(f"Parsing: {file_path}\n")

    chat = parse_chat_file(str(file_path))

    print("=" * 60)
    print("META")
    print("=" * 60)
    print(f"  title             : {chat.meta.title}")
    print(f"  mode              : {chat.meta.mode}")
    print(f"  version           : {chat.meta.version}")
    print(f"  language          : {chat.meta.language}")
    print(f"  nsfw              : {chat.meta.nsfw}")
    print(f"  output_transcript : {chat.meta.output_transcript}")
    print(f"  output_runlog     : {chat.meta.output_runlog}")

    print()
    print("=" * 60)
    print("CHAT CONFIG")
    print("=" * 60)
    print(f"  max_turns         : {chat.config.max_turns}")
    print(f"  pause_every       : {chat.config.pause_every}")
    print(f"  history_window    : {chat.config.history_window}")
    print(f"  opening_speaker   : {chat.config.opening_speaker}")
    print(f"  turn_selection    : {chat.config.turn_selection}")
    print(f"  max_retries       : {chat.config.max_retries}")

    print()
    print("=" * 60)
    print("WORLD INFO")
    print("=" * 60)
    for line in chat.world_info.splitlines():
        print(f"  {line}")

    print()
    print("=" * 60)
    print("GM PROMPT  (first 3 lines)")
    print("=" * 60)
    for line in chat.gm_prompt.splitlines()[:3]:
        print(f"  {line}")
    print("  ...")

    print()
    print("=" * 60)
    print("SCENARIO  (first 3 lines)")
    print("=" * 60)
    for line in chat.scenario.splitlines()[:3]:
        print(f"  {line}")
    print("  ...")

    print()
    print("=" * 60)
    print(f"CHARACTERS  ({len(chat.characters)} found)")
    print("=" * 60)
    for c in chat.characters:
        print(f"\n  [{c.role}] {c.name}")
        print(f"    triggers        : {', '.join(c.triggers)}")
        print(f"    speaking_weight : {c.speaking_weight}")
        print(f"    can_take_over   : {c.can_be_taken_over}")
        print(f"    description     : {c.description[:80]}{'...' if len(c.description) > 80 else ''}")
        print(f"    personality     : {c.personality[:80]}{'...' if len(c.personality) > 80 else ''}")
        if c.speech_style:
            print(f"    speech_style    : {c.speech_style[:80]}{'...' if len(c.speech_style) > 80 else ''}")
        if c.backstory:
            print(f"    backstory       : {c.backstory[:80]}{'...' if len(c.backstory) > 80 else ''}")

    print()
    print("OK — parse complete.")
