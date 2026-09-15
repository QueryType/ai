"""Post-reply state classifier.

Runs *after* a reply and off the critical path — never before generation.
faaltoo-chat awaits its extractors inline, which is why it stalls every 2 turns.
"""
from __future__ import annotations

import json

from openai import AsyncOpenAI

from src.config import Config
from src.policy import Policy
from src.state import CLOSENESS, ENERGY, MOODS, State, WHEN

_SCHEMA = {
    "type": "object",
    "properties": {
        "mood": {"type": "string", "enum": list(MOODS)},
        "closeness": {"type": "string", "enum": list(CLOSENESS)},
        "energy": {"type": "string", "enum": list(ENERGY)},
        "open_threads": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"topic": {"type": "string"}, "status": {"type": "string"}},
                "required": ["topic", "status"],
                "additionalProperties": False,
            },
        },
        "new_traits": {"type": "array", "items": {"type": "string"}},
        "promises": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "by": {"type": "string"},
                    "when": {"type": "string", "enum": list(WHEN)},
                },
                "required": ["text", "by", "when"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["mood", "closeness", "energy", "open_threads", "new_traits", "promises"],
    "additionalProperties": False,
}

_INSTRUCTION = """\
Read the chat above and report the CURRENT state of the human in it. The
characters' messages are prefixed with their name; the human's messages are not.
- mood, energy: how they seem in their most recent messages.
- closeness: how close the group feels to them. Move this slowly, only on real evidence.
- open_threads: unresolved things someone should follow up on. Few, specific, short.
- new_traits: things about them that will still be true next week — habits,
  circumstances, work, relationships, what they are going through. Record one as
  soon as they state or clearly imply it. Not passing moods, not one-off events.
- promises: anything a character committed to doing later, with "by" set to the
  name of the character who committed to it. Not the human's own intentions.
  Empty if none."""


def _response_format(mode: str) -> dict | None:
    if mode == "json_schema":
        return {
            "type": "json_schema",
            "json_schema": {"name": "chat_state", "strict": True, "schema": _SCHEMA},
        }
    if mode == "json_object":
        return {"type": "json_object"}
    return None


class StateTracker:
    def __init__(self, client: AsyncOpenAI, cfg: Config, policy: Policy, state: State) -> None:
        self.client = client
        self.cfg = cfg
        self.policy = policy
        self.state = state
        self.enabled = policy.structured_mode in ("json_schema", "json_object")

    async def update(self, tail: list[dict], speaker: str = "") -> None:
        if not self.enabled:
            return
        instruction = _INSTRUCTION
        if self.policy.structured_mode == "json_object":
            instruction += "\nReply with a single JSON object."

        resp = await self.client.chat.completions.create(
            model=self.cfg.model,
            messages=tail + [{"role": "user", "content": instruction}],
            max_tokens=400,
            temperature=0,
            response_format=_response_format(self.policy.structured_mode),
        )
        self.state.merge(json.loads(resp.choices[0].message.content), speaker=speaker)
