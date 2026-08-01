"""
config.py — loads config.yaml once at import time.
Public interface: cfg (SimpleNamespace) and PROFILES dict.
"""

from pathlib import Path
from types import SimpleNamespace
import yaml

_ROOT = Path(__file__).parent
_raw = yaml.safe_load((_ROOT / "config.yaml").read_text())

PROFILES: dict[str, dict] = _raw["profiles"]

_loop = _raw["loop"]
cfg = SimpleNamespace(
    max_iterations   = _loop["max_iterations"],
    score_threshold  = _loop["score_threshold"],
    plateau_patience = _loop.get("plateau_patience", 2),
    sessions_dir     = _ROOT / _loop["sessions_dir"],
    rubric           = _raw["rubric"],          # list of {name, description}
)
