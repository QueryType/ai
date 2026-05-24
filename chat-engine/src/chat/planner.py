"""Chat planner — optional whole-session phase guidance.

Keeps the current architecture intact by adding soft planning pressure on top of
speaker selection and by exposing phase context for the GM prompt.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.chat.chat_logger import TurnRecord
from src.chat.parser import CharacterCard, ChatPhase


@dataclass(frozen=True)
class PhaseSnapshot:
    name: str
    start_turn: int
    end_turn: int
    goal: str
    pace: str | None
    focus_characters: tuple[str, ...]
    required_characters: tuple[str, ...]
    avoid_characters: tuple[str, ...]
    guidance: str | None
    max_consecutive_turns: int

    def format_for_prompt(self) -> str:
        lines = [
            f"CURRENT CHAT PHASE: {self.name}",
            f"TURN RANGE: {self.start_turn}-{self.end_turn}",
        ]
        if self.goal:
            lines.append(f"PHASE GOAL: {self.goal}")
        if self.pace:
            lines.append(f"PACE: {self.pace}")
        if self.focus_characters:
            lines.append("FOCUS CHARACTERS: " + ", ".join(self.focus_characters))
        if self.required_characters:
            lines.append("REQUIRED CHARACTERS: " + ", ".join(self.required_characters))
        if self.avoid_characters:
            lines.append("DE-EMPHASISE: " + ", ".join(self.avoid_characters))
        if self.guidance:
            lines.append(f"PHASE GUIDANCE: {self.guidance}")
        return "\n".join(lines)


class ChatPlanner:
    """Provides optional session-level pacing and character coverage guidance."""

    def __init__(self, characters: list[CharacterCard], phases: list[ChatPhase]):
        self._characters = characters
        self._char_by_name = {c.name: c for c in characters}
        self._phases = sorted(phases, key=lambda phase: phase.start_turn)

    def phase_for_turn(self, turn_number: int) -> PhaseSnapshot | None:
        for phase in self._phases:
            if phase.start_turn <= turn_number <= phase.end_turn:
                return PhaseSnapshot(
                    name=phase.name,
                    start_turn=phase.start_turn,
                    end_turn=phase.end_turn,
                    goal=phase.goal,
                    pace=phase.pace,
                    focus_characters=tuple(phase.focus_characters),
                    required_characters=tuple(phase.required_characters),
                    avoid_characters=tuple(phase.avoid_characters),
                    guidance=phase.guidance,
                    max_consecutive_turns=phase.max_consecutive_turns,
                )
        return None

    def current_phase(self, turns: list[TurnRecord]) -> PhaseSnapshot | None:
        return self.phase_for_turn(len(turns) + 1)

    def phase_prompt(self, turns: list[TurnRecord]) -> str | None:
        phase = self.current_phase(turns)
        return phase.format_for_prompt() if phase else None

    def choose_speaker(
        self,
        turns: list[TurnRecord],
        preferred: str,
        candidates: list[str] | None = None,
    ) -> str:
        phase = self.current_phase(turns)
        if not phase:
            return preferred

        eligible = candidates[:] if candidates else list(self._char_by_name)
        if preferred in self._char_by_name and preferred not in eligible:
            eligible.append(preferred)
        eligible = [name for name in eligible if name in self._char_by_name]
        if not eligible:
            return preferred

        phase_counts = self._phase_counts(turns, phase)
        unmet_required = {
            name for name in phase.required_characters if phase_counts.get(name, 0) == 0
        }
        last_speaker = turns[-1].speaker if turns else None
        streak = self._speaker_streak(turns, last_speaker)

        def score(name: str) -> tuple[float, int, int]:
            value = 0.0
            if name == preferred:
                value += 1.5
            if name in phase.focus_characters:
                value += 2.5
            if name in unmet_required:
                value += 3.5
            if name in phase.avoid_characters:
                value -= 3.0

            value -= float(phase_counts.get(name, 0))

            if last_speaker == name:
                value -= 1.5
                if streak >= phase.max_consecutive_turns:
                    value -= 100.0

            return (value, -phase_counts.get(name, 0), 1 if name == preferred else 0)

        return max(eligible, key=score)

    def selection_reason(self, turns: list[TurnRecord], speaker: str) -> str | None:
        phase = self.current_phase(turns)
        if not phase:
            return None
        phase_counts = self._phase_counts(turns, phase)
        if speaker in phase.required_characters and phase_counts.get(speaker, 0) == 0:
            return f"phase '{phase.name}' requires {speaker} to participate"
        if speaker in phase.focus_characters:
            return f"phase '{phase.name}' focuses on {speaker}"
        return f"phase '{phase.name}' pacing bias applied"

    def _phase_counts(
        self,
        turns: list[TurnRecord],
        phase: PhaseSnapshot,
    ) -> dict[str, int]:
        counts: dict[str, int] = {}
        for turn in turns:
            if phase.start_turn <= turn.turn_number <= phase.end_turn:
                counts[turn.speaker] = counts.get(turn.speaker, 0) + 1
        return counts

    def _speaker_streak(self, turns: list[TurnRecord], speaker: str | None) -> int:
        if not turns or not speaker:
            return 0

        streak = 0
        for turn in reversed(turns):
            if turn.speaker != speaker:
                break
            streak += 1
        return streak