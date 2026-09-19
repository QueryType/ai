"""Live rut detection: notices a character sliding into a verbal tic mid-session.

Independent of src/metrics.py on purpose — that module scores a whole finished
transcript in one pass; this one is incremental, updated one reply at a time
as a real session runs. See PLAN_RUT_DETECTION.md.
"""
from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass, field

_WORD = re.compile(r"[a-z']+")

_WINDOW = 6
_MIN_SAMPLES = 4
_OPENER_WORDS = 3
_OPENER_STUCK_RATIO = 0.5
_QUESTION_OK = 0.5
_LENGTH_FLAT_BAND = 0.2


def _opener(text: str) -> str:
    return " ".join(_WORD.findall(text.lower())[:_OPENER_WORDS])


@dataclass
class _Shape:
    opener: str
    ends_in_question: bool
    length: int


def _shape_of(text: str) -> _Shape:
    stripped = text.rstrip()
    return _Shape(
        opener=_opener(text),
        ends_in_question=stripped.endswith("?"),
        length=len(text),
    )


def _opener_stuck(buf: deque[_Shape]) -> bool:
    counts: dict[str, int] = {}
    for s in buf:
        if s.opener:
            counts[s.opener] = counts.get(s.opener, 0) + 1
    if not counts:
        return False
    return max(counts.values()) / len(buf) > _OPENER_STUCK_RATIO


def _question_heavy(buf: deque[_Shape]) -> bool:
    rate = sum(1 for s in buf if s.ends_in_question) / len(buf)
    return rate > _QUESTION_OK


def _length_flat(buf: deque[_Shape]) -> bool:
    lengths = [s.length for s in buf]
    mean = sum(lengths) / len(lengths)
    if mean == 0:
        return False
    return all(abs(l - mean) <= mean * _LENGTH_FLAT_BAND for l in lengths)


@dataclass
class RutTracker:
    """Per-character reply-shape history, nudging the next directive away
    from a detected tic. No dependency on Scenario, Config or Selector."""

    window: int = _WINDOW
    _by_speaker: dict[str, deque[_Shape]] = field(default_factory=dict)

    def record(self, speaker: str, text: str) -> None:
        """Call once per finalized reply."""
        if not text:
            return
        buf = self._by_speaker.setdefault(speaker, deque(maxlen=self.window))
        buf.append(_shape_of(text))

    def unrecord(self, speaker: str) -> None:
        """Undo the most recent record() for `speaker` — used by
        Engine.regenerate() to roll back exactly the entry the discarded
        reply added. No-op if there's nothing to pop (e.g. that reply was
        empty and record() never ran)."""
        buf = self._by_speaker.get(speaker)
        if buf:
            buf.pop()

    def snapshot(self) -> dict[str, deque]:
        """A copy safe to restore() later — used by Engine.delete_from()
        to rewind to an arbitrary earlier turn, not just undo the last one."""
        return {name: deque(buf, maxlen=self.window) for name, buf in self._by_speaker.items()}

    def restore(self, snapshot: dict[str, deque]) -> None:
        self._by_speaker = {name: deque(buf, maxlen=self.window) for name, buf in snapshot.items()}

    def nudge(self, speaker: str) -> str:
        """Directive fragment steering away from a detected tic, or "" if none."""
        buf = self._by_speaker.get(speaker)
        if not buf or len(buf) < _MIN_SAMPLES:
            return ""
        notes = []
        if _opener_stuck(buf):
            notes.append("Don't open with the same phrase you've used recently.")
        if _question_heavy(buf):
            notes.append("Don't end this one in a question.")
        if _length_flat(buf):
            notes.append("Vary how long this reply is from your recent ones.")
        return " ".join(notes)
