"""Data models for the game-master adventure engine."""

from __future__ import annotations

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Scene file models (parsed from .md scenario files)
# ---------------------------------------------------------------------------


@dataclass
class Meta:
    title: str
    mode: str = "interactive"        # always interactive for adventure
    pov: str = "second-person"       # "You ..." framing by default
    language: str = "en"
    nsfw: bool = False


@dataclass
class CharacterCard:
    name: str
    role: str                        # player-character | npc | antagonist | neutral
    triggers: list[str]              # keyword list for World Info injection
    description: str = ""
    personality: str = ""
    backstory: str = ""
    speech_style: str = ""
    portrait: str = ""               # optional image path; described once at startup


@dataclass
class AdventureScene:
    """Parsed representation of an adventure scenario file."""
    meta: Meta
    narrator_prompt: str             # GM identity, POV rules, NPC control rules
    writing_style: str               # Prose style directives
    world_info: str                  # Global lore — baked into system prompt
    characters: list[CharacterCard]
    scene_setup: str                 # Location, time, atmosphere
    scenario: str                    # Background context — baked into system prompt
    memory: str                      # Initial mutable persistent facts
    opening: str                     # GM's first narration shown before turn 1
    author_note: str = ""            # Tone/style injected near generation
    author_note_depth: int = 4       # Inject every N turns (0 = every turn)
    scene_image: str = ""            # optional image path; described once at startup


# ---------------------------------------------------------------------------
# Runtime state
# ---------------------------------------------------------------------------


@dataclass
class WorldInfoEntry:
    keyword: str                     # Trigger keyword (case-insensitive)
    content: str                     # Prose injected when keyword matches


@dataclass
class GameState:
    """Mutable runtime state for a running adventure session."""
    scene: AdventureScene
    memory: str                      # Current memory block (may be updated by GM tools)
    author_note: str                 # Current author's note (may be updated by GM tools)
    world_info_entries: list[WorldInfoEntry] = field(default_factory=list)
    story_log: list[str] = field(default_factory=list)  # GM narration only, one entry per turn
    turn_count: int = 0
    input_mode: str = "action"       # "action" | "story"
    save_name: str | None = None
    vision_capable: bool = False     # set at startup by vision probe
    pending_image_context: str = ""  # /img description for the next turn only; cleared after use

    @classmethod
    def from_scene(cls, scene: AdventureScene) -> "GameState":
        return cls(
            scene=scene,
            memory=scene.memory,
            author_note=scene.author_note,
        )
