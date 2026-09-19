"""Generate the human's own line automatically — self-auto mode
(BACKLOG.md: "Self-Auto mode"). A short, separate completion, deliberately
outside Engine.turn()'s system-prompt/history machinery: it never reads or
appends to the immutable character system prompt (CLAUDE.md rule 1), it just
produces a string that then goes into engine.turn(text=...) exactly like
real typed input. One-off and uncached each time it fires — infrequent and
short enough that skipping the cache here costs nothing.
"""
from __future__ import annotations

from src.cast import Scenario
from src.engine import Engine
from src.register import strip_speaker_prefix
from src.transcript import entries

_TAIL = 12
_DEFAULT_VOICE = (
    "An ordinary participant in this conversation — no special background, "
    "just replies naturally and briefly in their own voice."
)


def _persona_name(scenario: Scenario) -> str:
    return scenario.human_persona.name if scenario.human_persona else "you"


def _system_prompt(scenario: Scenario) -> str:
    name = _persona_name(scenario)
    voice = scenario.human_persona.description if scenario.human_persona else _DEFAULT_VOICE
    return (
        f'You are role-playing as "{name}", a real participant in this scene — '
        "not one of the other named characters.\n\n"
        f"Setting:\n{scenario.setting}\n\n"
        f"Your persona: {voice}\n\n"
        "Write only your next line of dialogue, in first person, the way this "
        "person would actually say it. No name prefix, no narration, no "
        "describing yourself in the third person — just the line itself."
    )


async def generate_human_line(engine: Engine) -> str:
    name = _persona_name(engine.scenario)
    tail = [e for e in entries(engine.history)[-_TAIL:] if e.text]
    convo = [f"{name if e.role == 'user' else e.speaker}: {e.text}" for e in tail]
    messages = [
        {"role": "system", "content": _system_prompt(engine.scenario)},
        {
            "role": "user",
            "content": "Conversation so far:\n" + "\n".join(convo) + f"\n\n{name}:",
        },
    ]
    resp = await engine.client.chat.completions.create(
        model=engine.cfg.model,
        messages=messages,
        max_tokens=engine.policy.reply_max_tokens,
        temperature=engine.cfg.temperature,
    )
    text = (resp.choices[0].message.content or "").strip()
    return strip_speaker_prefix(text, name).strip()
