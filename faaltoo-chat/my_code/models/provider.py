"""Model provider — returns (AsyncOpenAI client, model_id) for faaltoo-chat."""
from __future__ import annotations

import os

from dotenv import load_dotenv
from openai import AsyncOpenAI

load_dotenv()

_DEFAULT_MODEL = "default"


def get_client() -> tuple[AsyncOpenAI, str]:
    provider = os.environ.get("FAALTOO_PROVIDER", "local")

    if provider == "local":
        base_url = os.environ.get("FAALTOO_LOCAL_BASE_URL", "http://localhost:1234/v1")
        model_id = os.environ.get("FAALTOO_MODEL", _DEFAULT_MODEL)
        return AsyncOpenAI(base_url=base_url, api_key="not-needed"), model_id

    if provider == "openrouter":
        model_id = os.environ.get("FAALTOO_MODEL", "deepseek/deepseek-v3.2")
        return (
            AsyncOpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=os.environ["OPENROUTER_API_KEY"],
            ),
            model_id,
        )

    raise ValueError(
        f"Provider {provider!r} not supported. "
        "Set FAALTOO_PROVIDER to 'local' or 'openrouter'."
    )


def get_vision_client_args() -> tuple[str, str, str] | None:
    """Return (base_url, model_id, api_key) for vision calls, or None if not configured."""
    provider = os.environ.get("FAALTOO_PROVIDER", "local")

    if provider == "local":
        base_url = os.environ.get("FAALTOO_LOCAL_BASE_URL", "http://localhost:1234/v1")
        model_id = os.environ.get(
            "FAALTOO_VISION_MODEL",
            os.environ.get("FAALTOO_MODEL", _DEFAULT_MODEL),
        )
        return base_url, model_id, "not-needed"

    if provider == "openrouter":
        model_id = os.environ.get(
            "FAALTOO_VISION_MODEL",
            os.environ.get("FAALTOO_MODEL", "openai/gpt-4o"),
        )
        return "https://openrouter.ai/api/v1", model_id, os.environ.get("OPENROUTER_API_KEY", "")

    return None
