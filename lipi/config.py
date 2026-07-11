"""
config.py — Harness configuration
Loads settings from config.yaml; falls back to defaults if the file is missing.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

_CONFIG_PATH = Path(__file__).parent / "config.yaml"


def _load_yaml() -> dict:
    if _CONFIG_PATH.exists():
        with open(_CONFIG_PATH) as f:
            return yaml.safe_load(f) or {}
    return {}


_raw = _load_yaml()

PROFILES: dict = _raw.get("profiles", {})

_harness: dict = _raw.get("harness", {})


@dataclass
class HarnessConfig:
    profile: str = _harness.get("profile", "coder")

    max_iterations: int = _harness.get("max_iterations", 30)
    max_tool_output: int = _harness.get("max_tool_output", 6000)
    compaction_threshold: float = _harness.get("compaction_threshold", 0.8)
    mid_turn_warn: float = _harness.get("mid_turn_warn", 0.90)
    mid_turn_abort: float = _harness.get("mid_turn_abort", 0.95)
    aging_start: float = _harness.get("aging_start", 0.5)
    aging_stub: float = _harness.get("aging_stub", 0.7)

    shell_timeout: int = _harness.get("shell_timeout", 60)
    allowed_write_paths: list = field(
        default_factory=lambda: _harness.get(
            "allowed_write_paths", ["~/projects", "~/harness", "/tmp"]
        )
    )
    confirm_commands: list = field(
        default_factory=lambda: _harness.get(
            "confirm_commands",
            ["rm -rf", "sudo", "pip install", "brew install",
             "git push", "curl | bash", "wget | bash"],
        )
    )

    confirm_writes: bool = _harness.get("confirm_writes", True)
    locked_paths: list = field(
        default_factory=lambda: _harness.get(
            "locked_paths",
            ["/etc/*", "/System/*", "/Library/*", "/usr/*", "/bin/*",
             "/sbin/*", "/var/*", "/private/*", "/boot/*",
             "~/.ssh/*", "~/.gnupg/*", "~/.bash_profile", "~/.zshrc", "~/.zprofile"],
        )
    )

    tavily_api_key: str = os.environ.get("TAVILY_API_KEY", "")

    vision_profile: str = _harness.get("vision_profile", "vision")

    duckdb_path: str = _harness.get("duckdb_path", "~/projects/breadth/breadth.duckdb")

    sessions_dir: str = _harness.get("sessions_dir", "~/.harness/sessions")
    save_sessions: bool = _harness.get("save_sessions", True)

    stream_output: bool = _harness.get("stream_output", True)
    show_tool_calls: bool = _harness.get("show_tool_calls", True)
    show_timings: bool = _harness.get("show_timings", False)
    render_markdown: bool = _harness.get("render_markdown", True)
    auto_approve: bool = False

    skill_dirs: list = field(
        default_factory=lambda: _harness.get(
            "skill_dirs", [".skills", "~/.lipi/skills"]
        )
    )


cfg = HarnessConfig()
