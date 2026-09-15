"""Prompt assembly.

The system prompt is built once and never mutates for the life of a session.
On the measured server a changed prefix costs ~26s against ~0.1s cached, so
everything volatile is *appended* instead — history only ever grows, and the
cached prefix is never invalidated.
"""
from __future__ import annotations

from src.cast import Scenario

_REGISTER = """\
How everyone writes:
- Text like a real person in a group chat. Lowercase is fine. Contractions always.
- Short. One to three lines, never a paragraph.
- No narration, no asterisk actions, no stage directions — only what gets typed.
- Disagree, tease, change the subject, let things go unanswered.
- Never offer help, never summarise, never ask if there is anything else.
- Speak only as yourself. Never write anyone else's lines."""


def build_system_prompt(scenario: Scenario) -> str:
    parts = [f"This is a group chat: {scenario.title}."]
    if scenario.setting:
        parts.append(scenario.setting)
    parts.append("The people in it:")
    parts.extend(f"{c.name}\n{c.description}" for c in scenario.characters)
    parts.append(_REGISTER)
    return "\n\n".join(parts)


def speaker_directive(name: str) -> str:
    return f"[Reply as {name}. Only {name}.]"
