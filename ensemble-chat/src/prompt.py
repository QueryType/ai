"""Prompt assembly.

The system prompt is built once and never mutates for the life of a session.
On the measured server a changed prefix costs ~26s against ~0.1s cached, so
everything volatile is *appended* instead — history only ever grows, and the
cached prefix is never invalidated.
"""
from __future__ import annotations

from src.cast import Scenario

_REGISTER_TEXT = """\
How everyone writes:
- Text like a real person in a group chat. Lowercase is fine. Contractions always.
- Short. One to three lines, never a paragraph.
- No narration, no asterisk actions, no stage directions — only what gets typed.
- Disagree, tease, change the subject, let things go unanswered.
- Never offer help, never summarise, never ask if there is anything else.
- Speak only as yourself. Never write anyone else's lines."""

_REGISTER_F2F = """\
How everyone writes:
- Write like a short story, not a chat transcript or a screenplay. Weave
  action, tone, and spoken dialogue into the same flowing prose — never an
  action description as its own paragraph followed by a separate paragraph
  of dialogue. That split-paragraph shape is exactly what this isn't.
- Spoken words go in double quotes, with any attribution or action woven into
  the same sentence, the way fiction does it:
  "Worst food I've had all year," Priya says, pushing her plate away.
  Dev doesn't look up. "You say that every time."
- Action and physical detail are optional, not required every turn. Plain
  dialogue alone, with no action at all, is often the right call — don't pad
  a short line with a gesture just to have one.
- There's no name label shown above your turn, so name yourself early in
  EVERY reply — not just your first one in the conversation. The reader has
  no other way to know who's speaking now; a name you gave three turns ago
  doesn't carry forward. Either as the subject of the first action ("Priya
  sets her mug down...") or in the first line's dialogue tag ("'...,' Dev
  says"). Don't open a turn with a bare pronoun ("She said...") that has
  nothing on the page to point to. Pronouns are fine for the rest of that
  same turn, once you've named yourself in it.
- Turns can run longer than a text message, but stay in the moment: no
  narrating the whole scene, no summarising what already happened.
- Disagree, tease, change the subject, let things go unanswered.
- Rarely say each other's names inside the spoken dialogue itself — real
  conversation doesn't, even though the narration around it can name anyone
  freely.
- The other person in the scene is never one of the named characters above —
  that's who you're talking to. In narration, refer to them as "you", the way
  you'd address them if you turned to speak to them. Never call them "the
  human", "the user", or any other label that isn't a name.
- Never offer help, never summarise, never ask if there is anything else.
- Speak only as yourself. Never write anyone else's spoken lines."""


def build_system_prompt(scenario: Scenario) -> str:
    is_f2f = scenario.mode == "f2f"
    parts = [f"This is a scene: {scenario.title}." if is_f2f else f"This is a group chat: {scenario.title}."]
    if scenario.setting:
        parts.append(scenario.setting)
    parts.append("The people in it:")
    parts.extend(f"{c.name}\n{c.description}" for c in scenario.characters)
    parts.append(_REGISTER_F2F if is_f2f else _REGISTER_TEXT)
    return "\n\n".join(parts)


def speaker_directive(name: str) -> str:
    return f"[Reply as {name}. Only {name}.]"
