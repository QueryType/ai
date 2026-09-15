from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from src.config import Config

_META = re.compile(r"^-?\s*(\w+)\s*:\s*(.+)$")


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
class Scenario:
    title: str
    setting: str
    characters: tuple[Character, ...]

    def by_name(self, name: str) -> Character | None:
        lowered = name.lower()
        return next((c for c in self.characters if c.name.lower() == lowered), None)


def load_scenario(path: Path) -> Scenario:
    title = ""
    setting: list[str] = []
    characters: list[Character] = []
    current: dict | None = None
    in_characters = False

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
        if line.startswith("# ") and not title:
            title = line[2:].strip()
        elif line.strip().lower().rstrip("s") == "## character":
            in_characters = True
        elif line.startswith("### "):
            flush()
            current = {"name": line[4:].strip(), "weight": 1.0, "body": []}
        elif not in_characters:
            setting.append(line)
        elif current is not None:
            meta = _META.match(line.strip())
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

    return Scenario(
        title=title or path.stem,
        setting="\n".join(setting).strip(),
        characters=tuple(characters),
    )
