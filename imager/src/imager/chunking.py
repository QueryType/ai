"""Split large story text into ordered, budget-sized chunks for map-reduce LLM passes."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class Chunk:
    id: str
    index: int
    char_start: int
    char_end: int
    text: str


# Prefer splitting on paragraph boundaries so we never cut a sentence in half.
_PARAGRAPH_SPLIT = re.compile(r"\n\s*\n")


def split_into_chunks(story_text: str, budget_chars: int) -> list[Chunk]:
    if len(story_text) <= budget_chars:
        return [Chunk(id="000", index=0, char_start=0, char_end=len(story_text), text=story_text)]

    paragraphs = []
    pos = 0
    for m in _PARAGRAPH_SPLIT.finditer(story_text):
        paragraphs.append((pos, m.start(), story_text[pos:m.start()]))
        pos = m.end()
    paragraphs.append((pos, len(story_text), story_text[pos:]))

    chunks: list[Chunk] = []
    buf_start = None
    buf_end = None
    buf_parts: list[str] = []

    def flush():
        nonlocal buf_start, buf_end, buf_parts
        if not buf_parts:
            return
        text = "\n\n".join(buf_parts)
        chunks.append(Chunk(id=f"{len(chunks):03d}", index=len(chunks), char_start=buf_start, char_end=buf_end, text=text))
        buf_start = None
        buf_end = None
        buf_parts = []

    for start, end, para in paragraphs:
        if not para.strip():
            continue
        # A single paragraph bigger than the whole budget: hard-split it on its own.
        if len(para) > budget_chars:
            flush()
            for i in range(0, len(para), budget_chars):
                piece = para[i:i + budget_chars]
                chunks.append(Chunk(
                    id=f"{len(chunks):03d}", index=len(chunks),
                    char_start=start + i, char_end=start + i + len(piece), text=piece,
                ))
            continue

        cur_len = sum(len(p) for p in buf_parts)
        if buf_parts and cur_len + len(para) > budget_chars:
            flush()

        if buf_start is None:
            buf_start = start
        buf_end = end
        buf_parts.append(para)

    flush()
    return chunks
