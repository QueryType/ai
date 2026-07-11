"""
skills/registry.py — Skill discovery and activation
Scans configured directories for SKILL.md files, parses frontmatter,
and provides activation (full body injection into agent context).
"""

import re
from pathlib import Path
from typing import Optional

import yaml


class Skill:
    __slots__ = ("name", "description", "path", "compatibility",
                 "metadata", "allowed_tools", "loaded", "body")

    def __init__(self, name: str, description: str, path: Path, *,
                 compatibility: str = "", metadata: dict = None,
                 allowed_tools: list[str] = None):
        self.name = name
        self.description = description
        self.path = path
        self.compatibility = compatibility
        self.metadata = metadata or {}
        self.allowed_tools = allowed_tools
        self.loaded = False
        self.body: Optional[str] = None


def _parse_skill_md(path: Path) -> Optional[Skill]:
    """Parse a SKILL.md file. Returns Skill with frontmatter only (body loaded lazily)."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None

    m = re.match(r"^---\s*\n(.+?)\n---\s*\n", text, re.DOTALL)
    if not m:
        return None

    try:
        fm = yaml.safe_load(m.group(1))
    except yaml.YAMLError:
        return None

    if not isinstance(fm, dict):
        return None

    name = fm.get("name", "")
    description = fm.get("description", "")
    if not name or not description:
        return None

    allowed_tools = None
    if "allowed-tools" in fm:
        raw = fm["allowed-tools"]
        allowed_tools = raw if isinstance(raw, list) else raw.split()

    return Skill(
        name=name,
        description=description.strip(),
        path=path,
        compatibility=fm.get("compatibility", ""),
        metadata=fm.get("metadata", {}),
        allowed_tools=allowed_tools,
    )


class SkillRegistry:
    def __init__(self, skill_dirs: list[str]):
        self.skills: dict[str, Skill] = {}
        self._active: set[str] = set()
        for d in skill_dirs:
            self._scan_dir(Path(d).expanduser())

    def _scan_dir(self, base: Path):
        if not base.is_dir():
            return
        for skill_md in sorted(base.glob("*/SKILL.md")):
            skill = _parse_skill_md(skill_md)
            if skill and skill.name not in self.skills:
                self.skills[skill.name] = skill

    def list_skills(self) -> list[Skill]:
        return list(self.skills.values())

    def get(self, name: str) -> Optional[Skill]:
        return self.skills.get(name)

    def activate(self, name: str) -> Optional[str]:
        """
        Load and return the full SKILL.md body for injection into context.
        Returns None if skill not found or already active.
        """
        skill = self.skills.get(name)
        if not skill:
            return None
        if name in self._active:
            return None

        if not skill.loaded:
            text = skill.path.read_text(encoding="utf-8", errors="replace")
            m = re.match(r"^---\s*\n.+?\n---\s*\n", text, re.DOTALL)
            skill.body = text[m.end():].strip() if m else text.strip()
            skill.loaded = True

        self._active.add(name)
        return f"[Skill activated: {skill.name}]\n{skill.description}\n\n{skill.body}"

    def is_active(self, name: str) -> bool:
        return name in self._active

    def deactivate_all(self):
        """Forget active skills (e.g. after /clear removes their bodies from context)."""
        self._active.clear()

    _STOP_WORDS = frozenset(
        "the a an and or but not for with from about into over after before "
        "that this what which where when how who why are was were has have had "
        "does did will can could should would may might shall its our your their "
        "then than them been being some any all each every much many more most "
        "also just only very well still already use used using".split()
    )

    def match(self, user_input: str) -> Optional[str]:
        """
        Simple keyword match: tokenize user input and skill descriptions,
        return the best-matching inactive skill name if overlap is strong enough.
        """
        words = set(re.findall(r"[a-z]{3,}", user_input.lower())) - self._STOP_WORDS
        if not words:
            return None

        best_name, best_score = None, 0
        for skill in self.skills.values():
            if skill.name in self._active:
                continue
            desc_words = set(re.findall(r"[a-z]{3,}", skill.description.lower())) - self._STOP_WORDS
            name_words = set(skill.name.split("-"))
            overlap = len(words & (desc_words | name_words))
            if overlap > best_score:
                best_name, best_score = skill.name, overlap

        return best_name if best_score >= 2 else None

    def skill_names(self) -> list[str]:
        return list(self.skills.keys())

    def index_block(self) -> str:
        """Compact index of all skills for context injection (~100 tokens per skill)."""
        if not self.skills:
            return ""
        lines = ["[Available skills]"]
        for skill in self.skills.values():
            desc = skill.description.split("\n")[0][:120]
            lines.append(f"  * {skill.name} -- {desc}")
        return "\n".join(lines)
