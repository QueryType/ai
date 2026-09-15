from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
PROFILES_DIR = ROOT / "profiles"


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ[name])
    except (KeyError, TypeError, ValueError):
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.environ[name])
    except (KeyError, TypeError, ValueError):
        return default


def _dir_from_env(name: str) -> Path | None:
    location = os.environ.get(name, "").strip()
    return Path(location).expanduser() if location else None


@dataclass(frozen=True)
class Config:
    base_url: str
    api_key: str
    model: str
    scenarios_dir: Path | None
    session_dir: Path | None
    context_tokens: int
    parallel_slots: int
    temperature: float
    target_append_ms: int
    target_reply_seconds: float
    continuation_max: int
    continuation_chance: float
    idle_seconds: float
    vision_max_dimension: int
    request_timeout_seconds: float
    web_host: str
    web_port: int

    @property
    def profile_path(self) -> Path:
        host = self.base_url.split("//", 1)[-1].replace("/", "_").replace(":", "-")
        return PROFILES_DIR / f"{host}__{self.model.replace('/', '_')}.json"


def load_config() -> Config:
    return Config(
        base_url=os.environ.get("CHAT_BASE_URL", "http://localhost:1234/v1"),
        api_key=os.environ.get("CHAT_API_KEY", "not-needed"),
        model=os.environ.get("CHAT_MODEL", "default"),
        scenarios_dir=_dir_from_env("SCENARIO_LOC"),
        session_dir=_dir_from_env("SESSION_LOC"),
        context_tokens=_int("CHAT_CONTEXT_TOKENS", 8192),
        parallel_slots=_int("CHAT_PARALLEL_SLOTS", 1),
        temperature=_float("CHAT_TEMPERATURE", 0.9),
        target_append_ms=_int("CHAT_TARGET_APPEND_MS", 700),
        target_reply_seconds=_float("CHAT_TARGET_REPLY_SECONDS", 2.5),
        continuation_max=_int("CHAT_CONTINUATION_MAX", 2),
        continuation_chance=_float("CHAT_CONTINUATION_CHANCE", 0.25),
        idle_seconds=_float("CHAT_IDLE_SECONDS", 45.0),
        vision_max_dimension=_int("CHAT_VISION_MAX_DIMENSION", 1024),
        request_timeout_seconds=_float("CHAT_REQUEST_TIMEOUT_SECONDS", 60.0),
        web_host=os.environ.get("CHAT_WEB_HOST", "127.0.0.1"),
        web_port=_int("CHAT_WEB_PORT", 8000),
    )
