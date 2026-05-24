"""GMAgent — the single Game Master agent that voices all characters.

One stateless Strands Agent call per turn. The full chat history and the
next speaker's card travel in the turn prompt — the agent carries no state
between calls. A fresh Agent instance is created per generate() call to
guarantee isolation.

System prompt is built once at construction from world info + all character
cards. Turn prompt is built fresh each call with history + speaker selection.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from strands import Agent

from src.chat.models.provider import get_model
from src.chat.parser import CharacterCard, ChatConfig


# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------

@dataclass
class GMResponse:
    dialogue: str   # clean dialogue text — no speaker prefix, no outer quotes
    tokens: int     # usage tokens from the model (0 if unavailable)
    raw: str        # original model output, kept for debug


@dataclass
class SelectedGMResponse:
    speaker: str
    dialogue: str
    tokens: int
    raw: str


# ---------------------------------------------------------------------------
# GMAgent
# ---------------------------------------------------------------------------

class GMAgent:
    """Wraps a Strands Agent to produce one character's dialogue line per turn."""

    def __init__(
        self,
        world_info: str,
        gm_prompt: str,
        writing_style: str,
        scenario: str,
        characters: list[CharacterCard],
        config: ChatConfig,
    ):
        self._config = config
        self._char_by_name = {c.name: c for c in characters}
        self._system_prompt = _build_system_prompt(
            gm_prompt, writing_style, world_info, scenario, characters,
            config.response_length,
        )
        # Model is built lazily on first generate() call so that prompt
        # inspection and testing work without requiring API credentials.
        self._model = None

    # -----------------------------------------------------------------------
    # Prompt builders (exposed for inspection / testing)
    # -----------------------------------------------------------------------

    def build_turn_prompt(
        self,
        history: str,
        speaker: str,
        tone_hint: str | None = None,
        director_note: str | None = None,
        phase_context: str | None = None,
    ) -> str:
        """Assemble the per-turn user prompt sent to the GM."""
        card = self._char_by_name.get(speaker)
        parts: list[str] = []

        if history.strip():
            parts.append(f"CHAT HISTORY SO FAR:\n{history}")

        parts.append(f"NEXT SPEAKER: {speaker}")

        if card:
            parts.append(f"{speaker.upper()}'S CARD:\n{_format_card(card)}")

        if phase_context:
            parts.append(phase_context)

        if tone_hint:
            parts.append(f"TONE HINT: {tone_hint}")

        if director_note:
            parts.append(
                f"DIRECTOR NOTE (hidden from story — for your guidance only):\n{director_note}"
            )

        length = self._config.response_length.strip()
        if length.lower() == "free":
            parts.append(f"Write {speaker}'s next dialogue turn.")
        else:
            parts.append(f"Write {speaker}'s next dialogue turn. {length}.")
        return "\n\n".join(parts)

    def build_selected_turn_prompt(
        self,
        history: str,
        available_speakers: list[str],
        phase_context: str | None = None,
        director_note: str | None = None,
    ) -> str:
        """Assemble a per-turn prompt where the model selects the speaker and writes the line."""
        parts: list[str] = []

        if history.strip():
            parts.append(f"CHAT HISTORY SO FAR:\n{history}")

        parts.append("AVAILABLE SPEAKERS: " + ", ".join(available_speakers))

        if phase_context:
            parts.append(phase_context)

        if director_note:
            parts.append(
                f"DIRECTOR NOTE (hidden from story — for your guidance only):\n{director_note}"
            )

        parts.append(
            "Choose the most natural next speaker and write only one dialogue turn. "
            "Respond in this exact two-line format:\n"
            "SPEAKER: <exact character name>\n"
            "DIALOGUE: \"dialogue here\""
        )
        return "\n\n".join(parts)

    # -----------------------------------------------------------------------
    # Generation
    # -----------------------------------------------------------------------

    def generate(
        self,
        turn_prompt: str,
        speaker: str,
        max_retries: int | None = None,
    ) -> GMResponse:
        """Call the GM and return a clean GMResponse.

        Retries up to max_retries times if the output is malformed.
        Falls back to returning the raw text on final failure.
        """
        retries = max_retries if max_retries is not None else self._config.max_retries
        prompt = turn_prompt
        last_raw = ""
        last_tokens = 0

        for attempt in range(retries + 1):
            raw, tokens = self._call(prompt)
            last_raw = raw
            last_tokens = tokens

            dialogue = _parse_dialogue(raw, speaker)
            if dialogue:
                return GMResponse(dialogue=dialogue, tokens=tokens, raw=raw)

            if attempt < retries:
                prompt = (
                    turn_prompt
                    + f'\n\nYour last response was not formatted correctly. '
                    f'Write ONLY this character\'s line in this exact format:\n'
                    f'{speaker}: "dialogue here"'
                )

        # All retries exhausted — return cleaned raw text
        fallback = last_raw.strip().strip('"')
        return GMResponse(dialogue=fallback, tokens=last_tokens, raw=last_raw)

    def generate_selected_turn(
        self,
        turn_prompt: str,
        available_speakers: list[str],
        max_retries: int | None = None,
    ) -> SelectedGMResponse:
        """Call the GM once to pick the speaker and write the next line."""
        retries = max_retries if max_retries is not None else self._config.max_retries
        prompt = turn_prompt
        last_raw = ""
        last_tokens = 0

        for attempt in range(retries + 1):
            raw, tokens = self._call(prompt)
            last_raw = raw
            last_tokens = tokens

            speaker, dialogue = _parse_selected_dialogue(raw, available_speakers)
            if speaker and dialogue:
                return SelectedGMResponse(
                    speaker=speaker,
                    dialogue=dialogue,
                    tokens=tokens,
                    raw=raw,
                )

            if attempt < retries:
                prompt = (
                    turn_prompt
                    + "\n\nYour last response was not formatted correctly. "
                    + "Respond in this exact two-line format:\n"
                    + "SPEAKER: <exact character name>\n"
                    + "DIALOGUE: \"dialogue here\""
                )

        fallback_speaker = available_speakers[0]
        fallback_dialogue = last_raw.strip().splitlines()[-1].strip().strip('"') if last_raw.strip() else "..."
        return SelectedGMResponse(
            speaker=fallback_speaker,
            dialogue=fallback_dialogue,
            tokens=last_tokens,
            raw=last_raw,
        )

    # -----------------------------------------------------------------------
    # Internal
    # -----------------------------------------------------------------------

    def _call(self, prompt: str) -> tuple[str, int]:
        """Create a fresh stateless Agent and invoke it. Returns (text, tokens)."""
        if self._model is None:
            self._model = get_model()
        agent = Agent(
            system_prompt=self._system_prompt,
            model=self._model,
            tools=[],
            callback_handler=None,
        )
        response = agent(prompt)
        text = str(response).strip()
        tokens = _extract_tokens(response)
        return text, tokens


# ---------------------------------------------------------------------------
# Prompt assembly helpers
# ---------------------------------------------------------------------------

def _build_system_prompt(
    gm_prompt: str,
    writing_style: str,
    world_info: str,
    scenario: str,
    characters: list[CharacterCard],
    response_length: str = "2-4 sentences",
) -> str:
    cast_block = "\n".join(_format_cast_summary(c) for c in characters)

    if response_length.strip().lower() == "free":
        length_instruction = "Let each character speak as much as the moment demands — no length constraint."
    else:
        length_instruction = f"Each turn should be {response_length}."

    return (
        f"{gm_prompt.strip()}\n\n"
        f"## Turn Contract\n"
        f"If NEXT SPEAKER is provided in the user prompt, write only that character's next line. "
        f"If NEXT SPEAKER is omitted, choose the most natural next speaker from the available cast and then write only that speaker's line in the format requested by the user prompt.\n\n"
        f"## Writing Style\n{writing_style.strip()}\n\n"
        f"## Response Length\n{length_instruction}\n\n"
        f"## World\n{world_info.strip()}\n\n"
        f"## Opening Scenario\n{scenario.strip()}\n\n"
        f"## Cast Overview\n{cast_block}"
    )


def _format_card(c: CharacterCard) -> str:
    lines = [
        f"NAME: {c.name}",
        f"ROLE: {c.role}",
        f"DESCRIPTION: {c.description}",
        f"PERSONALITY: {c.personality}",
    ]
    if c.speech_style:
        lines.append(f"SPEECH STYLE: {c.speech_style}")
    if c.backstory:
        lines.append(f"BACKSTORY: {c.backstory}")
    return "\n".join(lines)


def _format_cast_summary(c: CharacterCard) -> str:
    summary = [f"- {c.name} [{c.role}]"]
    if c.speech_style:
        summary.append(f"voice: {c.speech_style}")
    else:
        summary.append(f"personality: {c.personality}")
    return " | ".join(summary)


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

def _parse_dialogue(raw: str, speaker: str) -> str | None:
    """Extract clean dialogue text from the model's raw output.

    Handles the formats the GM is instructed to produce, plus common
    variations models emit in practice.
    """
    text = raw.strip()

    # 1. Exact spec:  Speaker: "dialogue"  or  [Speaker]: "dialogue"
    m = re.match(
        r'^\[?' + re.escape(speaker) + r'\]?\s*:\s*"(.+?)"?\s*$',
        text, re.DOTALL | re.IGNORECASE,
    )
    if m:
        return m.group(1).strip()

    # 2. No quotes:  Speaker: dialogue text
    m = re.match(
        r'^\[?' + re.escape(speaker) + r'\]?\s*:\s*(.+)',
        text, re.DOTALL | re.IGNORECASE,
    )
    if m:
        return m.group(1).strip().strip('"')

    # 3. Bare quoted string: "dialogue"
    if text.startswith('"') and text.endswith('"') and len(text) > 2:
        return text[1:-1].strip()

    # 4. Single short line with no prefix — accept if clean (no newlines, <300 chars)
    if '\n' not in text and len(text) < 300:
        return text

    return None


def _parse_selected_dialogue(raw: str, available_speakers: list[str]) -> tuple[str | None, str | None]:
    speaker_raw = _extract_field(raw, "SPEAKER")
    dialogue_raw = _extract_field(raw, "DIALOGUE")

    speaker = _match_speaker_name(speaker_raw, available_speakers)
    if not speaker or not dialogue_raw:
        return None, None

    dialogue = dialogue_raw.strip().strip('"')
    return speaker, dialogue or None


def _extract_field(text: str, field: str) -> str | None:
    m = re.search(rf"^{field}\s*:\s*(.+)$", text, re.MULTILINE | re.IGNORECASE)
    return m.group(1).strip() if m else None


def _match_speaker_name(speaker_raw: str | None, available_speakers: list[str]) -> str | None:
    if not speaker_raw:
        return None

    for speaker in available_speakers:
        if speaker_raw == speaker:
            return speaker

    lower = speaker_raw.lower()
    for speaker in available_speakers:
        speaker_lower = speaker.lower()
        if speaker_lower.startswith(lower) or lower.startswith(speaker_lower.split()[0]):
            return speaker
    return None


def _extract_tokens(response) -> int:
    """Best-effort token count extraction from a Strands response object."""
    # Strands stores usage in response.metrics.accumulated_usage
    try:
        usage = response.metrics.accumulated_usage
        return int(usage.get("outputTokens", 0) + usage.get("inputTokens", 0))
    except Exception:
        pass
    # Fallback: try direct usage attribute
    try:
        return int(response.usage.total_tokens)
    except Exception:
        pass
    return 0


# ---------------------------------------------------------------------------
# __main__ — prompt preview + optional live call
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import os
    import sys
    from pathlib import Path

    root = Path(__file__).parent.parent.parent
    sys.path.insert(0, str(root))

    from src.chat.parser import parse_chat_file
    from src.chat.chat_logger import ChatLogger

    chat = parse_chat_file(str(root / "examples/ashenveil_chat1.md"))

    gm = GMAgent(
        world_info=chat.world_info,
        gm_prompt=chat.gm_prompt,
        writing_style=chat.writing_style,
        scenario=chat.scenario,
        characters=chat.characters,
        config=chat.config,
    )

    DIVIDER = "=" * 60

    print(DIVIDER)
    print("SYSTEM PROMPT")
    print(DIVIDER)
    for line in gm._system_prompt.splitlines():
        print(f"  {line}")

    # Simulate a few turns of history
    logger = ChatLogger(chat.meta.title, "examples/ashenveil_chat1.md")
    logger.append_turn("Lyra Voss",     "You're going in there alone. That's either brave or stupid.", "gm", "opening_turn", tokens=142)
    logger.append_turn("Brother Aldric","I've been called both. Neither has stopped me.",               "gm", "direct_address", tokens=98)

    history = logger.get_history(chat.config.history_window)
    speaker = "Lyra Voss"
    tone    = "suspicious — she doesn't believe a word he says"

    print()
    print(DIVIDER)
    print(f"TURN PROMPT  (next speaker: {speaker})")
    print(DIVIDER)
    prompt = gm.build_turn_prompt(
        history=history,
        speaker=speaker,
        tone_hint=tone,
        director_note=None,
    )
    for line in prompt.splitlines():
        print(f"  {line}")

    # ---- Live call (only if API key is set) --------------------------------
    provider = os.environ.get("CHAT_ENGINE_PROVIDER", "openrouter")
    has_key = bool(
        os.environ.get("OPENROUTER_API_KEY")
        or os.environ.get("ANTHROPIC_API_KEY")
        or provider in ("local", "bedrock")
    )

    print()
    if not has_key:
        print("No API key found — skipping live call.")
        print("Set OPENROUTER_API_KEY (or CHAT_ENGINE_PROVIDER + key) and re-run to test generation.")
    else:
        print(DIVIDER)
        print(f"LIVE CALL — {speaker}")
        print(DIVIDER)
        result = gm.generate(prompt, speaker)
        print(f"  dialogue : {result.dialogue}")
        print(f"  tokens   : {result.tokens}")
        print(f"  raw      : {result.raw!r}")

    print()
    print("OK — gm_agent ready.")
