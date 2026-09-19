from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from src.config import Config

_META = re.compile(r"^-?\s*(\w+)\s*:\s*(.+)$")
_SECTION_CHARACTERS = re.compile(r"^##\s*characters?\s*$", re.IGNORECASE)
_SECTION_YOU = re.compile(r"^##\s*you\s*$", re.IGNORECASE)


def resolve_scenario(cfg: Config, arg: str | None) -> Path:
    """Accept an explicit path, or a bare name looked up under SCENARIO_LOC."""
    if arg:
        explicit = Path(arg).expanduser()
        if explicit.is_file():
            return explicit

    if cfg.scenarios_dir is None:
        raise SystemExit("SCENARIO_LOC is not set — export it to point at your scenarios directory")
    if not cfg.scenarios_dir.is_dir():
        raise SystemExit(f"SCENARIO_LOC does not exist: {cfg.scenarios_dir}")

    # SCENARIO_LOC may point either at a folder of .md files or at a parent
    # holding one folder per scenario.
    found = sorted({*cfg.scenarios_dir.glob("*.md"), *cfg.scenarios_dir.glob("*/*.md")})

    if arg:
        stem = arg[:-3] if arg.endswith(".md") else arg
        match = next((p for p in found if stem in (p.stem, p.parent.name)), None)
        if match:
            return match
        raise SystemExit(f"no scenario {arg!r} in {cfg.scenarios_dir}")

    if not found:
        raise SystemExit(f"no .md scenarios in {cfg.scenarios_dir}")
    if len(found) == 1:
        return found[0]
    raise SystemExit("pick a scenario: " + ", ".join(p.stem for p in found))


@dataclass(frozen=True)
class Character:
    name: str
    weight: float
    description: str


@dataclass(frozen=True)
class HumanPersona:
    """Optional stand-in persona for "you", used only by self-auto mode
    (src/human_agent.py) to generate the human's own lines. Scenarios that
    don't define a `## You` section have no persona and self-auto falls
    back to a generic one — see BACKLOG.md."""

    name: str
    description: str


@dataclass(frozen=True)
class Scenario:
    title: str
    setting: str
    characters: tuple[Character, ...]
    mode: str = "text"  # "text" | "f2f" — see PLAN_F2F.md
    human_persona: HumanPersona | None = None

    def by_name(self, name: str) -> Character | None:
        lowered = name.lower()
        return next((c for c in self.characters if c.name.lower() == lowered), None)


def load_scenario(path: Path) -> Scenario:
    title = ""
    mode = "text"
    mode_consumed = False
    setting: list[str] = []
    characters: list[Character] = []
    you_name = "you"
    you_body: list[str] = []
    current: dict | None = None
    section = "setting"  # "setting" | "you" | "characters"

    def flush() -> None:
        if current and current["name"]:
            characters.append(
                Character(
                    name=current["name"],
                    weight=current["weight"],
                    description="\n".join(current["body"]).strip(),
                )
            )

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if line.startswith("# ") and not title:
            title = line[2:].strip()
            continue
        if _SECTION_CHARACTERS.match(stripped):
            flush()
            current = None
            section = "characters"
            continue
        if _SECTION_YOU.match(stripped):
            section = "you"
            continue
        if section == "characters" and line.startswith("### "):
            flush()
            current = {"name": line[4:].strip(), "weight": 1.0, "body": []}
            continue
        if section == "setting":
            if not mode_consumed and not any(s.strip() for s in setting):
                meta = _META.match(stripped)
                if meta and meta.group(1).lower() == "mode":
                    mode = meta.group(2).strip().lower()
                    mode_consumed = True
                    continue
            setting.append(line)
        elif section == "you":
            meta = _META.match(stripped)
            if meta and meta.group(1).lower() == "name":
                you_name = meta.group(2).strip()
            else:
                you_body.append(line)
        elif current is not None:
            meta = _META.match(stripped)
            if meta and meta.group(1).lower() == "weight":
                try:
                    current["weight"] = float(meta.group(2))
                except ValueError:
                    pass
            else:
                current["body"].append(line)

    flush()
    if not characters:
        raise ValueError(f"{path} defines no characters (expected '### Name' headings)")

    you_description = "\n".join(you_body).strip()
    human_persona = HumanPersona(name=you_name, description=you_description) if you_description else None

    return Scenario(
        title=title or path.stem,
        setting="\n".join(setting).strip(),
        characters=tuple(characters),
        mode=mode,
        human_persona=human_persona,
    )
