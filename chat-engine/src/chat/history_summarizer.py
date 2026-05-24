"""Rolling semantic history summarizer for bounded GM context."""

from __future__ import annotations

import re
from dataclasses import dataclass

from strands import Agent

from src.chat.chat_logger import TurnRecord
from src.chat.models.provider import get_model


@dataclass
class SummaryUpdate:
    text: str
    tokens: int
    raw: str


class HistorySummarizer:
    """Maintains a bounded semantic summary of turns that fall out of the live window."""

    def __init__(self):
        self._model = None
        self._system_prompt = (
            "You compress older multi-character dialogue into a compact continuity brief for an RPG-style chat. "
            "Preserve only story-relevant state: goals, commitments, revealed facts, tensions, emotional shifts, "
            "promises, threats, discoveries, and location/status changes. Omit phrasing details and minor banter. "
            "Write plain prose in short paragraphs, not bullets. Keep names exact."
        )

    def update_summary(
        self,
        previous_summary: str,
        turns: list[TurnRecord],
        max_chars: int,
    ) -> SummaryUpdate:
        if not turns or max_chars <= 0:
            return SummaryUpdate(text=previous_summary, tokens=0, raw=previous_summary)

        prompt = _build_summary_prompt(previous_summary, turns, max_chars)
        raw, tokens = self._call(prompt)
        summary = _parse_summary(raw) or _truncate(raw.strip(), max_chars)
        return SummaryUpdate(text=summary, tokens=tokens, raw=raw)

    def _call(self, prompt: str) -> tuple[str, int]:
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
        return text, _extract_tokens(response)


def format_history_with_summary(summary: str | None, recent_history: str) -> str:
    parts: list[str] = []
    if summary:
        parts.append("EARLIER CONTEXT SUMMARY:\n" + summary.strip())
    if recent_history.strip():
        parts.append(recent_history.strip())
    return "\n\n".join(parts)


def _build_summary_prompt(previous_summary: str, turns: list[TurnRecord], max_chars: int) -> str:
    turns_block = "\n".join(
        f'{turn.speaker}: "{_clean_text(turn.text, turn.speaker)}"'
        for turn in turns
    )
    existing = previous_summary.strip() or "(none yet)"
    return (
        f"EXISTING SUMMARY:\n{existing}\n\n"
        f"NEWLY AGED-OUT TURNS:\n{turns_block}\n\n"
        f"Rewrite the summary to include the new turns. Maximum length: {max_chars} characters. "
        "Return only the revised summary text."
    )


def _parse_summary(raw: str) -> str | None:
    text = raw.strip()
    if not text:
        return None
    match = re.search(r"^SUMMARY\s*:\s*(.+)$", text, re.MULTILINE | re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).strip()
    return text


def _clean_text(text: str, speaker: str) -> str:
    stripped = text.strip()
    pattern = re.compile(
        r'^(?:\[?' + re.escape(speaker) + r'\]?)\s*:\s*"?(.*?)"?\s*$',
        re.DOTALL,
    )
    match = pattern.match(stripped)
    if match:
        return match.group(1).strip()
    if stripped.startswith('"') and stripped.endswith('"') and len(stripped) > 1:
        return stripped[1:-1]
    return stripped


def _truncate(text: str, max_chars: int) -> str:
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    if max_chars <= 3:
        return text[:max_chars]
    return text[: max_chars - 3].rstrip() + "..."


def _extract_tokens(response) -> int:
    try:
        usage = response.metrics.accumulated_usage
        return int(usage.get("outputTokens", 0) + usage.get("inputTokens", 0))
    except Exception:
        pass
    try:
        return int(response.usage.total_tokens)
    except Exception:
        pass
    return 0