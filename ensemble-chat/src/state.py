"""Conversation state, split by how fast each part changes.

affect   — every turn, cheap, drives tone
threads  — event-driven, survives sessions, includes promises
traits   — rarely, high confidence only

They are kept apart deliberately: folding them into one blob is what lets a
noisy per-turn extractor overwrite facts it should have kept.
"""
from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass, field

MOODS = ("anxious", "happy", "sad", "angry", "neutral", "playful", "tired")
CLOSENESS = ("distant", "warm", "close")
ENERGY = ("low", "normal", "high")
WHEN = {
    "later_today": 6 * 3600,
    "tomorrow": 24 * 3600,
    "this_week": 5 * 24 * 3600,
    "someday": 30 * 24 * 3600,
}

_MAX_TRAITS = 24
_MAX_THREADS = 6

_WORDS = re.compile(r"[a-z0-9]+")
_STOP = frozenset(
    "a an the to on of and is are will would before after with their them they "
    "for in at about that this it its from by as".split()
)


def _keywords(text: str) -> set[str]:
    return {w for w in _WORDS.findall(text.lower()) if w not in _STOP}


def _similar(a: str, b: str, threshold: float = 0.5) -> bool:
    """The classifier rephrases the same item every turn; compare meaning, not text."""
    ka, kb = _keywords(a), _keywords(b)
    if not ka or not kb:
        return False
    return len(ka & kb) / len(ka | kb) >= threshold


@dataclass
class Affect:
    mood: str = "neutral"
    closeness: str = "warm"
    energy: str = "normal"


@dataclass
class Thread:
    topic: str
    status: str = "open"


@dataclass
class Promise:
    text: str
    speaker: str
    due: float
    fulfilled: bool = False


@dataclass
class State:
    affect: Affect = field(default_factory=Affect)
    threads: list[Thread] = field(default_factory=list)
    traits: list[str] = field(default_factory=list)
    promises: list[Promise] = field(default_factory=list)
    updated: bool = False

    def merge(self, payload: dict, speaker: str = "") -> None:
        self.updated = True
        if payload.get("mood") in MOODS:
            self.affect.mood = payload["mood"]
        if payload.get("closeness") in CLOSENESS:
            self.affect.closeness = payload["closeness"]
        if payload.get("energy") in ENERGY:
            self.affect.energy = payload["energy"]

        for raw in payload.get("open_threads") or []:
            topic = (raw.get("topic") or "").strip()
            if not topic:
                continue
            existing = next((t for t in self.threads if _similar(t.topic, topic)), None)
            if existing:
                existing.status = (raw.get("status") or existing.status).strip()
            else:
                self.threads.append(Thread(topic=topic, status=(raw.get("status") or "open").strip()))
        self.threads = [t for t in self.threads if t.status.lower() != "closed"][-_MAX_THREADS:]

        for trait in payload.get("new_traits") or []:
            trait = (trait or "").strip()
            if trait and not any(_similar(existing, trait) for existing in self.traits):
                self.traits.append(trait)
        self.traits = self.traits[-_MAX_TRAITS:]

        for raw in payload.get("promises") or []:
            text = (raw.get("text") or "").strip()
            if not text or any(_similar(p.text, text) for p in self.promises):
                continue
            offset = WHEN.get(raw.get("when", "tomorrow"), WHEN["tomorrow"])
            self.promises.append(
                Promise(
                    text=text,
                    speaker=(raw.get("by") or speaker or "").strip(),
                    due=time.time() + offset,
                )
            )

    def due_promises(self, now: float | None = None) -> list[Promise]:
        now = now if now is not None else time.time()
        return [p for p in self.promises if not p.fulfilled and p.due <= now]

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> State:
        return cls(
            affect=Affect(**(data.get("affect") or {})),
            threads=[Thread(**t) for t in data.get("threads") or []],
            traits=list(data.get("traits") or []),
            promises=[Promise(**p) for p in data.get("promises") or []],
            updated=bool(data.get("updated")),
        )


def _compose(affect: Affect, threads: list[Thread], traits: list[str]) -> str:
    lines = [
        f"Right now they seem {affect.mood}, energy {affect.energy}. "
        f"The group feels {affect.closeness} toward them."
    ]
    if threads:
        lines.append("Unfinished: " + "; ".join(f"{t.topic} ({t.status})" for t in threads))
    if traits:
        lines.append("You know about them: " + "; ".join(traits))
    return "[" + "\n".join(lines) + "]"


def render(state: State, budget_tokens: int) -> str:
    """Fit the state into the token budget by dropping the oldest details first."""
    limit = max(120, budget_tokens * 3)
    traits = list(state.traits)
    threads = list(state.threads)
    while True:
        block = _compose(state.affect, threads, traits)
        if len(block) <= limit or not (traits or threads):
            return block
        if traits:
            traits.pop(0)
        else:
            threads.pop(0)
