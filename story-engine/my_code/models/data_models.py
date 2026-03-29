"""Data models for Story Engine — all dataclasses per AGENT_DESIGN.md §3."""

from __future__ import annotations

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Scene input models
# ---------------------------------------------------------------------------

@dataclass
class Meta:
    title: str
    mode: str  # "autonomous" | "interactive" | "semi-interactive"
    output_file: str
    output_format: str  # "prose" | "adventure" | "script"
    pov: str  # "third-person" | "first-person" | "second-person"
    version: str = "1.0"
    pause_at: str = "beat"
    target_length: int = 1500
    language: str = "en"
    nsfw: bool = False


@dataclass
class AuthorNote:
    depth: int
    content: str


@dataclass
class CharacterCard:
    name: str
    role: str  # "player-character" | "npc" | "antagonist" | "neutral"
    triggers: list[str]
    description: str
    personality: str
    backstory: str | None = None
    speech_style: str | None = None


@dataclass
class SceneSetup:
    location: str | None = None
    time: str | None = None
    atmosphere: str | None = None


@dataclass
class Beat:
    index: int  # 1-based
    text: str
    has_pause: bool = False


@dataclass
class ParsedScene:
    meta: Meta
    narrator_prompt: str
    writing_style: str
    world_info: str
    characters: list[CharacterCard]
    scene_setup: SceneSetup
    scenario: str
    beats: list[Beat]
    author_note: AuthorNote | None = None
    writing_instructions: str | None = None


# ---------------------------------------------------------------------------
# Runtime models
# ---------------------------------------------------------------------------

@dataclass
class NarratorContext:
    beat_instruction: str
    lore_context: str
    beat_index: int  # 1-based
    beat_total: int
    author_note: str | None = None
    redirect_instruction: str | None = None


@dataclass
class LoreContext:
    world_info: str
    character_cards: list[str]  # pre-formatted strings per matched character
    triggered_names: list[str]
    full_block: str  # assembled injection string


@dataclass
class EvalResult:
    result: str  # "pass" | "retry"
    score: float  # 0.0 – 1.0
    reason: str
    beat_coverage: bool
    style_compliant: bool
    coherent: bool
    issues: list[str] = field(default_factory=list)


@dataclass
class HumanInput:
    action: str  # "continue" | "redirect" | "skip" | "stop" | "retry"
    text: str | None = None
