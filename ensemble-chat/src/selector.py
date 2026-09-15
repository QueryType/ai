from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.cast import Character, Scenario


@dataclass
class Selector:
    """Who speaks next: direct address wins, else lowest weighted speaking debt."""

    scenario: Scenario
    debt: dict[str, float] = field(init=False)

    def __post_init__(self) -> None:
        self.debt = {c.name: 0.0 for c in self.scenario.characters}

    def _addressed(self, text: str) -> Character | None:
        lowered = text.lower()
        for c in self.scenario.characters:
            if re.search(rf"\b{re.escape(c.name.lower())}\b", lowered):
                return c
        return None

    def charge(self, character: Character) -> None:
        """Record that `character` spoke, including forced speakers that bypass select()."""
        self.debt[character.name] += 1.0 / max(character.weight, 0.01)

    def select(self, user_text: str, last_speaker: str | None) -> Character:
        chosen = self._addressed(user_text)
        if chosen is None:
            pool = [c for c in self.scenario.characters if c.name != last_speaker]
            chosen = min(pool or list(self.scenario.characters), key=lambda c: self.debt[c.name])
        self.charge(chosen)
        return chosen
