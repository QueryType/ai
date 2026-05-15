"""Model provider factory — same env var pattern as story-engine.

Supports local (LMStudio/llama.cpp), openrouter, anthropic, bedrock.
Role name for this project: "game_master".
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

_DEFAULT_LOCAL_MODEL = "default"


def system_prompt_suffix(prompt: str) -> str:
    """Append STORY_ENGINE_SYSTEM_SUFFIX to a system prompt if set."""
    suffix = os.environ.get("STORY_ENGINE_SYSTEM_SUFFIX", "").strip()
    return f"{prompt}\n{suffix}" if suffix else prompt


def get_model(role: str):
    """Return a Strands model instance for the given role.

    Args:
        role: Agent role name, e.g. "game_master".

    Returns:
        A Strands Model instance ready to pass to Agent(model=...).
    """
    provider = os.environ.get("STORY_ENGINE_PROVIDER", "local")

    if provider == "local":
        base_url = os.environ.get(
            f"STORY_ENGINE_{role.upper()}_BASE_URL",
            os.environ.get("STORY_ENGINE_LOCAL_BASE_URL", "http://localhost:1234/v1"),
        )
        return _build_openai_compat(
            base_url=base_url,
            model_id=os.environ.get(f"STORY_ENGINE_{role.upper()}_MODEL", _DEFAULT_LOCAL_MODEL),
            api_key="not-needed",
        )

    elif provider == "openrouter":
        return _build_openai_compat(
            base_url="https://openrouter.ai/api/v1",
            model_id=os.environ.get(f"STORY_ENGINE_{role.upper()}_MODEL", "deepseek/deepseek-v3.2"),
            api_key=os.environ["OPENROUTER_API_KEY"],
        )

    elif provider == "anthropic":
        from strands.models import AnthropicModel
        model_id = os.environ.get(f"STORY_ENGINE_{role.upper()}_MODEL", "claude-sonnet-4-20250514")
        return AnthropicModel(model=model_id)

    elif provider == "bedrock":
        from strands.models import BedrockModel
        model_id = os.environ.get(
            f"STORY_ENGINE_{role.upper()}_MODEL",
            "us.anthropic.claude-sonnet-4-20250514-v1:0",
        )
        return BedrockModel(model_id=model_id)

    else:
        raise ValueError(f"Unknown STORY_ENGINE_PROVIDER: {provider!r}")


def get_vision_client_args() -> tuple[str, str, str] | None:
    """Return (base_url, model_id, api_key) for direct OpenAI-compat vision calls.

    Returns None for providers that do not use the OpenAI-compat image format
    (anthropic, bedrock) — vision probe/describe is skipped for those.
    """
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

    return None  # anthropic / bedrock use native SDK image blocks


def _build_openai_compat(base_url: str, model_id: str, api_key: str):
    from strands.models.openai import OpenAIModel
    return OpenAIModel(
        client_args={"base_url": base_url, "api_key": api_key},
        model_id=model_id,
    )
