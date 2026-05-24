"""Model provider factory for chat-engine.

All config via env vars — swap .env to switch backends.

Env vars:
  CHAT_ENGINE_PROVIDER        — local | openrouter | anthropic | bedrock  (default: openrouter)
  CHAT_ENGINE_MODEL           — model id override
  OPENROUTER_API_KEY          — required for openrouter
  CHAT_ENGINE_LOCAL_BASE_URL  — base URL for local provider (default: http://localhost:1234/v1)
  CHAT_ENGINE_MAX_TOKENS      — max tokens the model may generate per turn (default: 200)
  CHAT_ENGINE_TEMPERATURE     — sampling temperature (default: 0.85)
  CHAT_ENGINE_HISTORY_WINDOW  — overrides history_window from the .md file (optional)
  CHAT_ENGINE_CONTEXT_LIMIT   — warn at startup if estimated prompt exceeds this token count (default: 3500)
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

_OPENROUTER_DEFAULT = "deepseek/deepseek-v3.2"
_ANTHROPIC_DEFAULT  = "claude-sonnet-4-6"
_BEDROCK_DEFAULT    = "us.anthropic.claude-sonnet-4-6-20251001-v1:0"

_DEFAULT_MAX_TOKENS    = 400   # headroom for speaker prefix + 3-5 sentences; keep above 300 to avoid Strands MaxTokensReachedException
_DEFAULT_TEMPERATURE   = 0.85
_DEFAULT_CONTEXT_LIMIT = 3500


def history_window_override() -> int | None:
    """Return CHAT_ENGINE_HISTORY_WINDOW if set, else None (use .md value)."""
    val = os.environ.get("CHAT_ENGINE_HISTORY_WINDOW")
    if val:
        return int(val)
    return None


def context_limit() -> int:
    return int(os.environ.get("CHAT_ENGINE_CONTEXT_LIMIT", _DEFAULT_CONTEXT_LIMIT))


def _gen_params() -> dict:
    """Read generation parameters from env, applying defaults."""
    return {
        "max_tokens": int(os.environ.get("CHAT_ENGINE_MAX_TOKENS", _DEFAULT_MAX_TOKENS)),
        "temperature": float(os.environ.get("CHAT_ENGINE_TEMPERATURE", _DEFAULT_TEMPERATURE)),
    }


def get_model():
    """Return a Strands model instance for the GM agent."""
    provider = os.environ.get("CHAT_ENGINE_PROVIDER", "openrouter")
    params = _gen_params()

    if provider == "local":
        return _openai_compat(
            base_url=os.environ.get("CHAT_ENGINE_LOCAL_BASE_URL", "http://localhost:1234/v1"),
            model_id=os.environ.get("CHAT_ENGINE_MODEL", "default"),
            api_key="not-needed",
            params=params,
        )

    if provider == "openrouter":
        return _openai_compat(
            base_url="https://openrouter.ai/api/v1",
            model_id=os.environ.get("CHAT_ENGINE_MODEL", _OPENROUTER_DEFAULT),
            api_key=os.environ["OPENROUTER_API_KEY"],
            params=params,
        )

    if provider == "anthropic":
        from strands.models import AnthropicModel
        return AnthropicModel(
            model_id=os.environ.get("CHAT_ENGINE_MODEL", _ANTHROPIC_DEFAULT),
            **params,
        )

    if provider == "bedrock":
        from strands.models import BedrockModel
        return BedrockModel(
            model_id=os.environ.get("CHAT_ENGINE_MODEL", _BEDROCK_DEFAULT),
            **params,
        )

    raise ValueError(f"Unknown CHAT_ENGINE_PROVIDER: '{provider}'")


def model_label() -> str:
    """Human-readable model label for run log headers."""
    provider = os.environ.get("CHAT_ENGINE_PROVIDER", "openrouter")
    if provider == "openrouter":
        model = os.environ.get("CHAT_ENGINE_MODEL", _OPENROUTER_DEFAULT)
        return f"{model} via openrouter"
    if provider == "anthropic":
        return os.environ.get("CHAT_ENGINE_MODEL", _ANTHROPIC_DEFAULT)
    if provider == "bedrock":
        return os.environ.get("CHAT_ENGINE_MODEL", _BEDROCK_DEFAULT)
    if provider == "local":
        base = os.environ.get("CHAT_ENGINE_LOCAL_BASE_URL", "http://localhost:1234/v1")
        model = os.environ.get("CHAT_ENGINE_MODEL", "default")
        return f"{model} @ {base}"
    return provider


def _openai_compat(base_url: str, model_id: str, api_key: str, params: dict):
    from strands.models.openai import OpenAIModel
    return OpenAIModel(
        client_args={"base_url": base_url, "api_key": api_key},
        model_id=model_id,
        params=params,
    )
