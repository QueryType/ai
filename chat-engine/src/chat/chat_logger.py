"""ChatLogger — appends turns, tracks human interventions, saves both output files."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class TurnRecord:
    turn_number: int       # 1-based
    speaker: str
    text: str              # dialogue text only, no speaker prefix
    generator: str         # "gm" | "human"
    rule: str              # e.g. "opening_turn", "direct_address", "human_injection"
    tokens: int = 0        # populated for gm turns; 0 for human turns
    cmd: str | None = None # original human command string, if generator == "human"
    director_note: str | None = None  # director note attached to this turn, if any


class ChatLogger:
    def __init__(self, title: str, input_file: str, model_label: str = ""):
        self._title = title
        self._input_file = input_file
        self._model_label = model_label
        self._started_at = datetime.now().isoformat(timespec="seconds")
        self._turns: list[TurnRecord] = []
        self._human_intervention_count = 0
        self._director_note_count = 0
        self._total_tokens = 0

    # -----------------------------------------------------------------------
    # Write
    # -----------------------------------------------------------------------

    def append_turn(
        self,
        speaker: str,
        text: str,
        generator: str,
        rule: str,
        tokens: int = 0,
        cmd: str | None = None,
        director_note: str | None = None,
    ) -> TurnRecord:
        """Record one completed turn. Returns the TurnRecord."""
        turn_number = len(self._turns) + 1
        record = TurnRecord(
            turn_number=turn_number,
            speaker=speaker,
            text=text,
            generator=generator,
            rule=rule,
            tokens=tokens,
            cmd=cmd,
            director_note=director_note,
        )
        self._turns.append(record)

        if generator == "human":
            self._human_intervention_count += 1
        if director_note:
            self._director_note_count += 1
        self._total_tokens += tokens

        return record

    # -----------------------------------------------------------------------
    # Read
    # -----------------------------------------------------------------------

    @property
    def turns(self) -> list[TurnRecord]:
        """Read-only view of all recorded turns."""
        return self._turns

    def get_history(self, n: int = 20) -> str:
        """Return the last n turns as a formatted transcript string for prompt context."""
        window = self._turns[-n:] if n > 0 else self._turns
        lines = []
        for t in window:
            # Ensure text is already stripped of any speaker prefix the GM may have echoed
            text = _strip_speaker_prefix(t.text, t.speaker)
            lines.append(f'{t.speaker}: "{text}"')
        return "\n".join(lines)

    def turn_count(self) -> int:
        return len(self._turns)

    def speaking_stats(self) -> dict[str, int]:
        stats: dict[str, int] = {}
        for t in self._turns:
            stats[t.speaker] = stats.get(t.speaker, 0) + 1
        return stats

    def last_speaker(self) -> str | None:
        return self._turns[-1].speaker if self._turns else None

    def recent_speakers(self, n: int = 2) -> list[str]:
        """Names of the last n speakers (oldest first)."""
        return [t.speaker for t in self._turns[-n:]]

    # -----------------------------------------------------------------------
    # Save outputs
    # -----------------------------------------------------------------------

    def save_transcript(self, path: str) -> None:
        """Write clean chat-style transcript — human turns indistinguishable from GM turns."""
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)

        lines = [
            f"# {self._title}",
            f"*Session started: {self._started_at}*",
            "",
            "---",
            "",
        ]
        for t in self._turns:
            text = _strip_speaker_prefix(t.text, t.speaker)
            lines.append(f'{t.speaker}: "{text}"')

        lines += [
            "",
            "---",
            f"*Session ended — Turn {len(self._turns)} | Reason: user /stop*",
        ]
        out.write_text("\n".join(lines), encoding="utf-8")

    def save_runlog(self, path: str, end_reason: str = "user /stop") -> None:
        """Write application run log with full turn metadata."""
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)

        header = [
            f"# Run Log — {self._title}",
            f"*Session: {self._started_at}*",
            f"*Input: {self._input_file}*",
        ]
        if self._model_label:
            header.append(f"*Model: {self._model_label}*")
        header += ["", "---", ""]

        turn_lines = []
        for t in self._turns:
            tag = f"[T{t.turn_number:03d}]"
            speaker_col = f"SPEAKER: {t.speaker:<12}"
            gen_col = f"GEN: {t.generator:<5}"
            if t.generator == "human":
                rule_col = f"CMD: {t.rule}"
                input_col = f' | INPUT: "{t.cmd}"' if t.cmd else ""
                turn_lines.append(f"{tag} {speaker_col} | {gen_col} | {rule_col}{input_col}")
            else:
                rule_col = f"RULE: {t.rule:<24}"
                tok_col = f"TOKENS: {t.tokens}"
                turn_lines.append(f"{tag} {speaker_col} | {gen_col} | {rule_col} | {tok_col}")
            if t.director_note:
                turn_lines.append(f'       DIRECTOR NOTE: "{t.director_note}"')

        footer = [
            "",
            "---",
            f"*SESSION END*",
            f"*Total turns: {len(self._turns)} | "
            f"Human interventions: {self._human_intervention_count} | "
            f"Director notes: {self._director_note_count}*",
            f"*Total tokens generated: {self._total_tokens}*",
            f"*Transcript saved: (see meta)*",
            f"*Run log saved: {path}*",
        ]

        content = "\n".join(header + turn_lines + footer)
        out.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_speaker_prefix(text: str, speaker: str) -> str:
    """Remove 'Speaker: "..."' wrapper if the GM echoed the speaker name in the text."""
    # Handle: Speaker: "dialogue" or [Speaker]: "dialogue"
    pattern = re.compile(
        r'^(?:\[?' + re.escape(speaker) + r'\]?)\s*:\s*"?(.*?)"?\s*$',
        re.DOTALL,
    )
    m = pattern.match(text.strip())
    if m:
        return m.group(1).strip()
    # Strip bare surrounding quotes if present
    stripped = text.strip()
    if stripped.startswith('"') and stripped.endswith('"') and len(stripped) > 1:
        return stripped[1:-1]
    return stripped




# ---------------------------------------------------------------------------
# __main__ — smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logger = ChatLogger(
        title="Ashenveil — The Ruins Encounter",
        input_file="examples/ashenveil_chat1.md",
        model_label="deepseek/deepseek-v3.2 via openrouter",
    )

    logger.append_turn("Lyra",   "You're going in there alone. That's either brave or stupid.", "gm",    "opening_turn",        tokens=142)
    logger.append_turn("Aldric", "I've been called both. Neither has stopped me.",               "gm",    "direct_address",      tokens=98)
    logger.append_turn("Lyra",   "The Conclave has this place flagged. You know that.",          "gm",    "conflict_escalation", tokens=115)
    logger.append_turn("Lyra",   "I'm here because of you.",                                    "human", "human_injection",     cmd="[as Lyra] I'm here because of you.")
    logger.append_turn("Aldric", "Then perhaps we have more in common than you think.",          "gm",    "direct_address",      tokens=87,
                       director_note="Aldric should hint he's been inside before")
    logger.append_turn("Mira",   "The door already knows you're here.",                         "gm",    "round_robin",         tokens=54)

    print("=" * 60)
    print("HISTORY (last 20)")
    print("=" * 60)
    print(logger.get_history(20))

    print()
    print("=" * 60)
    print("SPEAKING STATS")
    print("=" * 60)
    for name, count in logger.speaking_stats().items():
        print(f"  {name}: {count}")

    print()
    print(f"Last speaker : {logger.last_speaker()}")
    print(f"Recent (2)   : {logger.recent_speakers(2)}")
    print(f"Turn count   : {logger.turn_count()}")

    print()
    print("=" * 60)
    print("TRANSCRIPT PREVIEW")
    print("=" * 60)
    logger.save_transcript("/tmp/test_transcript.md")
    print(Path("/tmp/test_transcript.md").read_text())

    print()
    print("=" * 60)
    print("RUN LOG PREVIEW")
    print("=" * 60)
    logger.save_runlog("/tmp/test_runlog.md")
    print(Path("/tmp/test_runlog.md").read_text())

    print("OK — chat_logger smoke test complete.")
