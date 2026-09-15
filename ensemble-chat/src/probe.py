"""Measure what this (host, model) pair can actually do, and cache the result.

The engine hardcodes no model or hardware assumptions; every tuning constant is
derived from the profile written here. Run again after changing model or server.
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from openai import AsyncOpenAI

from src.config import Config, load_config
from src.provider import get_client
from src.vision import probe_vision

_FILLER = "alpha bravo charlie delta echo foxtrot golf hotel "
_FILLER_REPEAT = 600

_STATE_SCHEMA = {
    "type": "object",
    "properties": {
        "mood": {
            "type": "string",
            "enum": ["anxious", "happy", "sad", "angry", "neutral", "playful"],
        },
        "topics": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["mood", "topics"],
    "additionalProperties": False,
}

_STATE_MSG = [
    {
        "role": "user",
        "content": "User said: 'ugh, still waiting to hear back about the job'. Classify.",
    }
]


@dataclass
class Profile:
    model: str
    base_url: str
    structured_mode: str
    prefill_tok_s: float
    decode_tok_s: float
    cache_speedup: float
    effective_slots: int
    probe_prompt_tokens: int
    vision_capable: bool = False
    probed_at: float = field(default_factory=time.time)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> Profile | None:
        if not path.exists():
            return None
        try:
            return cls(**json.loads(path.read_text(encoding="utf-8")))
        except (TypeError, ValueError):
            return None


def _cold_messages() -> list[dict]:
    return [
        {"role": "system", "content": f"SESSION {uuid.uuid4().hex}. " + _FILLER * _FILLER_REPEAT},
        {"role": "user", "content": "hi"},
    ]


async def _timed(client: AsyncOpenAI, model: str, messages: list[dict], **kw):
    started = time.perf_counter()
    resp = await client.chat.completions.create(model=model, messages=messages, **kw)
    return time.perf_counter() - started, resp


async def _probe_structured(client: AsyncOpenAI, model: str) -> str:
    attempts = [
        (
            "json_schema",
            {
                "type": "json_schema",
                "json_schema": {"name": "turn_state", "strict": True, "schema": _STATE_SCHEMA},
            },
        ),
        ("json_object", {"type": "json_object"}),
    ]
    for mode, response_format in attempts:
        try:
            _, resp = await _timed(
                client,
                model,
                _STATE_MSG,
                max_tokens=120,
                temperature=0,
                response_format=response_format,
            )
            if "mood" in json.loads(resp.choices[0].message.content):
                return mode
        except Exception:
            continue
    return "text"


async def _probe_speed(client: AsyncOpenAI, model: str) -> tuple[float, float, float, int]:
    messages = _cold_messages()
    cold_s, resp = await _timed(client, model, messages, max_tokens=1, temperature=0)
    prompt_tokens = resp.usage.prompt_tokens

    warm_s, _ = await _timed(client, model, messages, max_tokens=1, temperature=0)

    gen_s, gen_resp = await _timed(client, model, messages, max_tokens=128, temperature=0.8)
    produced = gen_resp.usage.completion_tokens or 128

    return (
        prompt_tokens / max(cold_s, 1e-6),
        produced / max(gen_s - warm_s, 1e-6),
        cold_s / max(warm_s, 1e-6),
        prompt_tokens,
    )


async def _probe_slots(client: AsyncOpenAI, model: str) -> int:
    """Two concurrent short generations: wall time near single = real parallelism."""
    a = [{"role": "user", "content": "Count slowly from one to forty, in words."}]
    b = [{"role": "user", "content": "List forty common English nouns, one per line."}]

    single_s, _ = await _timed(client, model, a, max_tokens=96, temperature=0.8)

    started = time.perf_counter()
    await asyncio.gather(
        _timed(client, model, a, max_tokens=96, temperature=0.8),
        _timed(client, model, b, max_tokens=96, temperature=0.8),
    )
    concurrent_s = time.perf_counter() - started

    return 2 if concurrent_s < single_s * 1.6 else 1


async def run_probe(cfg: Config) -> Profile:
    client = get_client(cfg)
    structured = await _probe_structured(client, cfg.model)
    prefill, decode, speedup, tokens = await _probe_speed(client, cfg.model)
    slots = await _probe_slots(client, cfg.model)
    vision = await probe_vision(client, cfg.model)
    return Profile(
        model=cfg.model,
        base_url=cfg.base_url,
        structured_mode=structured,
        prefill_tok_s=prefill,
        decode_tok_s=decode,
        cache_speedup=speedup,
        effective_slots=slots,
        probe_prompt_tokens=tokens,
        vision_capable=vision,
    )


def main() -> None:
    cfg = load_config()
    print(f"probing {cfg.model} at {cfg.base_url} (cold pass takes a while)…")
    profile = asyncio.run(run_probe(cfg))
    profile.save(cfg.profile_path)
    print(json.dumps(asdict(profile), indent=2))
    print(f"\nsaved -> {cfg.profile_path}")


if __name__ == "__main__":
    main()
