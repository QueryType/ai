from __future__ import annotations

from openai import AsyncOpenAI

from src.config import Config


def get_client(cfg: Config, timeout: float | None = None) -> AsyncOpenAI:
    """A bounded timeout turns a stalled server into a visible error instead of
    an indefinite hang — the SDK default is 10 minutes with no feedback."""
    return AsyncOpenAI(
        base_url=cfg.base_url,
        api_key=cfg.api_key,
        timeout=timeout if timeout is not None else cfg.request_timeout_seconds,
    )
