"""Model provider — returns (AsyncOpenAI client, model_id) for the game_master role.

Supports: local (LMStudio / llama.cpp), openrouter.
Both speak the OpenAI-compatible API, so the same client works for both.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from openai import AsyncOpenAI

load_dotenv()

_DEFAULT_LOCAL_MODEL = "default"


def system_prompt_suffix(prompt: str) -> str:
    """Append STORY_ENGINE_SYSTEM_SUFFIX to a system prompt if set."""
    suffix = os.environ.get("STORY_ENGINE_SYSTEM_SUFFIX", "").strip()
    return f"{prompt}\n{suffix}" if suffix else prompt


def get_client() -> tuple[AsyncOpenAI, str]:
    """Return (AsyncOpenAI client, model_id) for the game_master role."""
    provider = os.environ.get("STORY_ENGINE_PROVIDER", "local")
    role = "game_master"

    if provider == "local":
        base_url = os.environ.get(
            f"STORY_ENGINE_{role.upper()}_BASE_URL",
            os.environ.get("STORY_ENGINE_LOCAL_BASE_URL", "http://localhost:1234/v1"),
        )
        model_id = os.environ.get(f"STORY_ENGINE_{role.upper()}_MODEL", _DEFAULT_LOCAL_MODEL)
        return AsyncOpenAI(base_url=base_url, api_key="not-needed"), model_id

    if provider == "openrouter":
        model_id = os.environ.get(f"STORY_ENGINE_{role.upper()}_MODEL", "deepseek/deepseek-v3.2")
        return (
            AsyncOpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=os.environ["OPENROUTER_API_KEY"],
            ),
            model_id,
        )

    raise ValueError(
        f"Provider {provider!r} is not supported. Set STORY_ENGINE_PROVIDER to 'local' or 'openrouter'."
    )


def get_vision_client_args() -> tuple[str, str, str] | None:
    """Return (base_url, model_id, api_key) for direct OpenAI-compat vision calls."""
    provider = os.environ.get("STORY_ENGINE_PROVIDER", "local")
    role = "game_master"

    if provider == "local":
        base_url = os.environ.get(
            f"STORY_ENGINE_{role.upper()}_BASE_URL",
            os.environ.get("STORY_ENGINE_LOCAL_BASE_URL", "http://localhost:1234/v1"),
        )
        model_id = os.environ.get(f"STORY_ENGINE_{role.upper()}_MODEL", _DEFAULT_LOCAL_MODEL)
        return base_url, model_id, "not-needed"

    if provider == "openrouter":
        model_id = os.environ.get(f"STORY_ENGINE_{role.upper()}_MODEL", "deepseek/deepseek-v3.2")
        return "https://openrouter.ai/api/v1", model_id, os.environ["OPENROUTER_API_KEY"]

    return None
