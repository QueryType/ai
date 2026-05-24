"""OrchestratorAgent — LLM-driven turn selection for Phase 2.

Replaces the rule-based ChatOrchestrator with a Strands Agent that reads the
chat history and decides who speaks next in a single LLM call.

Exposes the same interface as ChatOrchestrator so main_chat.py can swap them
with a single conditional on config.turn_selection.

The LLM response also carries a tone hint for the GM, so no second call is needed.
"""

from __future__ import annotations

import re

from strands import Agent

from src.chat.chat_logger import TurnRecord
from src.chat.models.provider import get_model
from src.chat.orchestrator import TurnSelection
from src.chat.parser import CharacterCard, ChatConfig
from src.chat.planner import ChatPlanner


class OrchestratorAgent:
    """LLM-driven turn selector. Matches ChatOrchestrator's public interface."""

    def __init__(
        self,
        world_info: str,
        scenario: str,
        characters: list[CharacterCard],
        config: ChatConfig,
        planner: ChatPlanner | None = None,
    ):
        self._characters = characters
        self._char_by_name: dict[str, CharacterCard] = {c.name: c for c in characters}
        self._config = config
        self._planner = planner
        self._system_prompt = _build_system_prompt(world_info, scenario, characters)
        self._model = None
        # Cached from the last select_next_speaker call — consumed by get_tone_hint
        self._pending_tone: str | None = None

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def select_next_speaker(
        self,
        turns: list[TurnRecord],
        force_speaker: str | None = None,
    ) -> TurnSelection:
        """Ask the LLM who speaks next and return a TurnSelection.

        Also caches a tone hint that get_tone_hint() will return on the
        same turn — no second LLM call needed.
        """
        self._pending_tone = None

        if force_speaker and force_speaker in self._char_by_name:
            return TurnSelection(
                speaker=force_speaker,
                rule="forced",
                reason=f"/next command forced {force_speaker}",
            )

        if not turns:
            speaker = self._opening_speaker()
            return TurnSelection(
                speaker=speaker,
                rule="opening_turn",
                reason=f"First turn — opening_speaker from config: {speaker}",
            )

        phase_context = self._planner.phase_prompt(turns) if self._planner else None
        prompt = _build_turn_prompt(
            turns,
            self._characters,
            self._config.orchestrator_history_window,
            phase_context,
        )
        raw = self._call(prompt)
        selection, tone = _parse_response(raw, self._char_by_name, self._characters)
        if self._planner:
            planned_speaker = self._planner.choose_speaker(turns, selection.speaker)
            if planned_speaker != selection.speaker:
                selection = TurnSelection(
                    speaker=planned_speaker,
                    rule="llm_selection_phase_bias",
                    reason=self._planner.selection_reason(turns, planned_speaker)
                    or selection.reason,
                )
        self._pending_tone = tone
        return selection

    def get_tone_hint(self, turns: list[TurnRecord], speaker: str) -> str | None:
        """Return the tone hint extracted from the last LLM selection call."""
        return self._pending_tone

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    def _call(self, prompt: str) -> str:
        if self._model is None:
            self._model = get_model()
        agent = Agent(
            system_prompt=self._system_prompt,
            model=self._model,
            tools=[],
            callback_handler=None,
        )
        return str(agent(prompt)).strip()

    def _opening_speaker(self) -> str:
        name = self._config.opening_speaker
        if name != "auto" and name in self._char_by_name:
            return name
        for c in self._characters:
            if c.role == "player-character":
                return c.name
        return self._characters[0].name


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def _build_system_prompt(
    world_info: str,
    scenario: str,
    characters: list[CharacterCard],
) -> str:
    char_lines = "\n".join(
        f"  - {c.name} [{c.role}, weight={c.speaking_weight}] triggers: {', '.join(c.triggers[:3])}"
        for c in characters
    )
    weight_notes = ", ".join(
        f"{c.name} speaks ~{int(c.speaking_weight * 100)}% as often as a weight-1.0 character"
        for c in characters
        if c.speaking_weight != 1.0
    )
    weight_block = f"\n\nSpeaking weight notes: {weight_notes}" if weight_notes else ""

    return f"""\
You are the Story Orchestrator for a multi-character chat.

Your ONLY job is to decide WHO speaks next. You do NOT write dialogue.
Another agent writes the actual words — you just choose the speaker.

## Opening Setup
{scenario.strip()}

## Characters
{char_lines}{weight_block}

## Turn-selection principles (apply in order)
1. If a character was addressed by name or directly questioned, they speak next.
2. If the last line challenged or contradicted someone, that person defends themselves.
3. After a human injection, the most relevant character reacts first.
4. Vary the cast — avoid two characters monopolising while others go silent.
5. Respect speaking_weight: lower weight = speaks proportionally less often.
6. Trust dramatic momentum — who has the most stake in what was just said?

## Response format (STRICT — three lines, nothing else)
SPEAKER: <exact character name, no quotes>
REASON: <one sentence — why this character speaks next>
TONE: <one short phrase hint for the GM — e.g. "defensive, cuts in fast" — or "none">"""


def _build_turn_prompt(
    turns: list[TurnRecord],
    characters: list[CharacterCard],
    history_window: int,
    phase_context: str | None = None,
) -> str:
    recent = turns[-history_window:] if history_window > 0 else turns
    history_lines = "\n".join(f'{t.speaker}: "{t.text}"' for t in recent)

    char_names = ", ".join(c.name for c in characters)

    parts = [
        f"CHAT HISTORY (most recent {len(recent)} turns):\n"
        f"{history_lines}",
        f"CHARACTERS: {char_names}",
    ]
    if phase_context:
        parts.append(phase_context)
    parts.append("Who speaks next? Reply in the exact three-line format.")
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Response parser
# ---------------------------------------------------------------------------

def _parse_response(
    raw: str,
    char_by_name: dict[str, CharacterCard],
    characters: list[CharacterCard],
) -> tuple[TurnSelection, str | None]:
    """Parse the LLM's three-line response into a TurnSelection + optional tone hint."""
    speaker = _extract_field(raw, "SPEAKER")
    reason  = _extract_field(raw, "REASON") or "LLM selected this speaker."
    tone_raw = _extract_field(raw, "TONE")
    tone = None if (not tone_raw or tone_raw.lower() in ("none", "n/a", "-")) else tone_raw

    # Validate speaker name — exact match first
    if speaker and speaker in char_by_name:
        return TurnSelection(speaker=speaker, rule="llm_selection", reason=reason), tone

    # Fuzzy match: name starts-with (handles "Lyra" → "Lyra Voss")
    if speaker:
        lower = speaker.lower()
        for c in characters:
            if c.name.lower().startswith(lower) or lower.startswith(c.name.lower().split()[0]):
                return TurnSelection(speaker=c.name, rule="llm_selection", reason=reason), tone

    # Fallback: first character mentioned in the raw text, else first in list
    for c in characters:
        if c.name.lower() in raw.lower():
            return TurnSelection(
                speaker=c.name,
                rule="llm_selection_fallback",
                reason=f"Name match fallback from raw LLM output (original: {speaker!r})",
            ), tone

    fallback = characters[0]
    return TurnSelection(
        speaker=fallback.name,
        rule="llm_selection_fallback",
        reason=f"Could not parse speaker from LLM output — defaulting to {fallback.name}",
    ), tone


def _extract_field(text: str, field: str) -> str | None:
    """Extract the value from a 'FIELD: value' line in the LLM response."""
    m = re.search(rf"^{field}\s*:\s*(.+)$", text, re.MULTILINE | re.IGNORECASE)
    return m.group(1).strip() if m else None


# ---------------------------------------------------------------------------
# __main__ — prompt preview + optional live call
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import os
    import sys
    from pathlib import Path

    root = Path(__file__).parent.parent.parent
    sys.path.insert(0, str(root))

    from src.chat.chat_logger import ChatLogger
    from src.chat.parser import parse_chat_file

    chat = parse_chat_file(str(root / "examples/ashenveil_chat1.md"))

    orc = OrchestratorAgent(
        world_info=chat.world_info,
        scenario=chat.scenario,
        characters=chat.characters,
        config=chat.config,
    )

    DIVIDER = "=" * 60

    print(DIVIDER)
    print("SYSTEM PROMPT")
    print(DIVIDER)
    for line in orc._system_prompt.splitlines():
        print(f"  {line}")

    # Build a sample turn prompt
    from src.chat.chat_logger import TurnRecord

    def fake_turn(speaker: str, text: str, generator: str = "gm") -> TurnRecord:
        return TurnRecord(
            turn_number=1, speaker=speaker, text=text,
            generator=generator, rule="", tokens=80,
        )

    turns = [
        fake_turn("Lyra Voss",      "You're going in there alone. That's brave or stupid."),
        fake_turn("Brother Aldric", "I've been called both. Neither has stopped me."),
        fake_turn("Lyra Voss",      "The Conclave has this place flagged. You know that."),
    ]

    print()
    print(DIVIDER)
    print("TURN PROMPT")
    print(DIVIDER)
    prompt = _build_turn_prompt(turns, chat.characters, chat.config.history_window)
    for line in prompt.splitlines():
        print(f"  {line}")

    provider = os.environ.get("CHAT_ENGINE_PROVIDER", "openrouter")
    has_key = bool(
        os.environ.get("OPENROUTER_API_KEY")
        or os.environ.get("ANTHROPIC_API_KEY")
        or provider in ("local", "bedrock")
    )

    print()
    if not has_key:
        print("No API key found — skipping live call.")
        print("Set OPENROUTER_API_KEY or ANTHROPIC_API_KEY and re-run to test.")
    else:
        print(DIVIDER)
        print("LIVE CALL")
        print(DIVIDER)
        sel = orc.select_next_speaker(turns)
        tone = orc.get_tone_hint(turns, sel.speaker)
        print(f"  speaker : {sel.speaker}")
        print(f"  rule    : {sel.rule}")
        print(f"  reason  : {sel.reason}")
        print(f"  tone    : {tone!r}")

    print()
    print("OK — orchestrator_agent ready.")
