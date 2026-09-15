"""Session persistence — history, state and speaking debt across runs."""
from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

from src.config import Config
from src.state import State

_SLIDING_REPLAY = 40


def session_path(cfg: Config, scenario_path: Path) -> Path:
    """Beside the scenario by default; under SESSION_LOC when one is set.

    Keyed on the full scenario path, not just its filename — two scenarios can
    easily share a stem once they live in one folder each.
    """
    if cfg.session_dir is None:
        return scenario_path.parent / f"{scenario_path.stem}.session.json"
    digest = hashlib.sha1(str(scenario_path.resolve()).encode()).hexdigest()[:6]
    return cfg.session_dir / f"{scenario_path.stem}-{digest}.json"


def attachments_dir(save_path: Path) -> Path:
    """Colocated with the session file — never in this repo (rule 6), and
    named off the same stem so it moves with the session if you relocate it."""
    stem = save_path.name.removesuffix(".json")
    return save_path.parent / f"{stem}.attachments"


@dataclass
class Session:
    history: list[dict] = field(default_factory=list)
    state: State = field(default_factory=State)
    debt: dict[str, float] = field(default_factory=dict)
    last_speaker: str | None = None
    updated_at: float = 0.0

    @classmethod
    def load(cls, path: Path, strategy: str) -> Session:
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            return cls()
        history = data.get("history") or []
        if strategy == "sliding":
            history = history[-_SLIDING_REPLAY:]
        return cls(
            history=history,
            state=State.from_dict(data.get("state") or {}),
            debt=data.get("debt") or {},
            last_speaker=data.get("last_speaker"),
            updated_at=float(data.get("updated_at") or 0.0),
        )

    def save(self, path: Path) -> None:
        """Write to a sibling temp file, then atomically rename over the
        target. `write_text` alone can leave a truncated/corrupt file if the
        process is killed mid-write (a second, impatient Ctrl-C is exactly
        this); `os.replace` on the same filesystem can't — the old file stays
        intact until the instant the new one is fully in place."""
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "history": self.history,
            "state": self.state.to_dict(),
            "debt": self.debt,
            "last_speaker": self.last_speaker,
            "updated_at": time.time(),
        }
        tmp = path.with_suffix(f"{path.suffix}.tmp")
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
