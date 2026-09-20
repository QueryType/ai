"""Texting register: strip model tells, split replies into message bubbles."""
from __future__ import annotations

import re
from collections.abc import Iterable

ASSISTANT_TICS = (
    "as an ai",
    "i'd be happy to",
    "i am happy to",
    "is there anything else",
    "let me know if",
    "i hope this helps",
    "how can i assist",
    "feel free to",
    "certainly!",
    "of course!",
)

_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_SENTENCE_END = re.compile(r"[.!?][\"'”’)]*$")


def strip_speaker_prefix(text: str, names: str | Iterable[str]) -> str:
    """Drop "Name: " labels from the start of every line, not just the
    first — including a whole chain of them ("A: B: C: ...").

    History stores replies as "Name: text" so the model can tell who said
    what. It imitates that label two ways: repeating its own name if it
    starts a second message mid-reply, and prefixing a reply with whoever
    it's responding to (a reply-quote convention it invents on its own,
    not something ever asked for). Left unstripped, the second kind
    compounds: each turn's stored "Speaker: Other: text" becomes the next
    turn's example to imitate and extend, so the chain only grows —
    observed live growing to five deep within a dozen turns. Stripping
    only the current speaker's own name (the original, narrower version of
    this function) catches the first kind but not the second, so this
    takes every known name in the scene and strips any leading run of
    them, not just the speaker's own.
    """
    if isinstance(names, str):
        names = [names]
    alternation = "|".join(re.escape(n) for n in names if n)
    if not alternation:
        return text
    pattern = rf"^(?:\s*(?:{alternation})\s*:\s*)+"
    return re.sub(pattern, "", text, flags=re.IGNORECASE | re.MULTILINE)


def trim_incomplete_sentence(text: str) -> str:
    """Drop a trailing sentence fragment left by a max_tokens cutoff.

    Only meant to be called when the model was hard-stopped mid-generation
    (finish_reason == "length", see engine.py) — turns a garbled mid-word cut
    into a shorter but complete-sounding reply. Leaves text alone if it
    already ends cleanly. If no sentence in the reply ever completed, there's
    nothing sound to keep — drops it entirely rather than storing the raw
    fragment, since history is append-only and can never be cleaned up later.
    """
    text = text.strip()
    if not text or _SENTENCE_END.search(text):
        return text
    parts = [p for p in _SENTENCE.split(text) if p.strip()]
    if len(parts) <= 1:
        return ""
    trimmed = " ".join(parts[:-1]).strip()
    return trimmed if trimmed else ""


def find_tics(text: str) -> list[str]:
    lowered = text.lower()
    return [t for t in ASSISTANT_TICS if t in lowered]


def _cap(parts: list[str], limit: int) -> list[str]:
    if len(parts) <= limit:
        return parts
    return parts[: limit - 1] + [" ".join(parts[limit - 1 :])]


def split_bubbles(text: str, limit: int = 3) -> list[str]:
    text = text.strip()
    if not text:
        return []
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(lines) > 1:
        return _cap(lines, limit)
    parts = [p.strip() for p in _SENTENCE.split(text) if p.strip()]
    return _cap(parts, limit) if len(parts) > 1 else [text]


def f2f_block(text: str) -> list[str]:
    """A turn is one screenplay block, not several text bubbles."""
    text = text.strip()
    return [text] if text else []
