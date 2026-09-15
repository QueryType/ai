"""Turn Engine.history into plain chat entries.

Filters out the internal speaker-directive and state-block system messages —
those steer generation, they aren't things anyone "said". Shared by the
terminal `/log` command and the web UI's initial transcript load.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Entry:
    role: str  # "user" | "assistant"
    speaker: str | None  # character name; None for the human
    text: str
    image_path: str | None = None  # relative to Engine.attachments_dir


def _user_text_and_image(content) -> tuple[str, str | None]:
    """A user turn's content is a plain string, or — when it carried an
    attachment — a list of parts (`{"type": "text", ...}` /
    `{"type": "image_ref", ...}`, see `src/vision.py`)."""
    if isinstance(content, str):
        return content, None
    text = next((p["text"] for p in content if p.get("type") == "text"), "")
    image_path = next((p["path"] for p in content if p.get("type") == "image_ref"), None)
    return text, image_path


def entries(history: list[dict]) -> list[Entry]:
    out: list[Entry] = []
    for msg in history:
        if msg["role"] == "user":
            text, image_path = _user_text_and_image(msg["content"])
            out.append(Entry(role="user", speaker=None, text=text, image_path=image_path))
        elif msg["role"] == "assistant":
            name, _, text = msg["content"].partition(": ")
            out.append(Entry(role="assistant", speaker=name, text=text))
    return out
