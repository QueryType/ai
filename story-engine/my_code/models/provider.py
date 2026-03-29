"""Model provider factory — centralised model configuration per AGENT_DESIGN.md §7.

All config comes from env vars. Swap .env to switch between local/cloud backends.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

_DEFAULT_LOCAL_MODEL = "default"


def get_model(role: str):
    """Return a Strands model instance for the given agent role.

    Args:
        role: One of "narrator", "evaluator", "orchestrator", "lore_injector".

    Returns:
        A Strands Model instance ready to pass to Agent(model=...).
    """
    provider = os.environ.get("STORY_ENGINE_PROVIDER", "local")

    if provider == "local":
        return _build_openai_compat(
            base_url=os.environ.get("STORY_ENGINE_LOCAL_BASE_URL", "http://localhost:1234/v1"),
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
        raise ValueError(f"Unknown STORY_ENGINE_PROVIDER: {provider}")


def _build_openai_compat(base_url: str, model_id: str, api_key: str):
    """Build an OpenAIModel using client_args (verified strands-agents 1.33.0 API)."""
    from strands.models.openai import OpenAIModel

    return OpenAIModel(
        client_args={"base_url": base_url, "api_key": api_key},
        model_id=model_id,
    )
