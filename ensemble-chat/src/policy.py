"""Turn a measured Profile into the runtime constants the engine uses.

Conservative defaults apply when no profile exists, so the app always starts.
"""
from __future__ import annotations

from dataclasses import dataclass

from src.config import Config
from src.probe import Profile

_UNPROBED = Profile(
    model="",
    base_url="",
    structured_mode="text",
    prefill_tok_s=150.0,
    decode_tok_s=15.0,
    cache_speedup=1.0,
    effective_slots=1,
    probe_prompt_tokens=0,
    vision_capable=False,
)


@dataclass(frozen=True)
class Policy:
    structured_mode: str
    state_block_tokens: int
    reply_max_tokens: int
    history_strategy: str
    cache_matters: bool
    probed: bool
    vision_capable: bool


def _clamp(value: float, low: int, high: int) -> int:
    return max(low, min(high, int(value)))


def derive(cfg: Config, profile: Profile | None, mode: str = "text") -> Policy:
    p = profile or _UNPROBED
    target_reply_seconds = cfg.target_reply_seconds_f2f if mode == "f2f" else cfg.target_reply_seconds
    return Policy(
        structured_mode=p.structured_mode,
        state_block_tokens=_clamp(cfg.target_append_ms / 1000 * p.prefill_tok_s, 80, 400),
        reply_max_tokens=_clamp(target_reply_seconds * p.decode_tok_s, 48, 400),
        history_strategy="full" if cfg.context_tokens >= 100_000 else "sliding",
        cache_matters=p.cache_speedup >= 3.0,
        probed=profile is not None,
        vision_capable=p.vision_capable,
    )


def load_policy(cfg: Config, mode: str = "text") -> Policy:
    return derive(cfg, Profile.load(cfg.profile_path), mode)


if __name__ == "__main__":
    import json
    from dataclasses import asdict

    from src.config import load_config

    _cfg = load_config()
    _policy = load_policy(_cfg)
    print(f"{_cfg.model} @ {_cfg.base_url}")
    print(json.dumps(asdict(_policy), indent=2))
    if not _policy.probed:
        print("\nno profile found — using conservative defaults; run: python -m src.probe")
