"""
context/packer.py — Project context builder
Reads directory structure and key files to give the agent initial orientation
without stuffing everything into the prompt upfront.
"""

from datetime import date
from pathlib import Path
from typing import Optional


# Extensions considered "code" for context packing
CODE_EXTS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs",
    ".md", ".txt", ".yaml", ".yml", ".toml", ".json",
    ".sh", ".sql", ".html", ".css",
}

SKIP_DIRS  = {".git", "__pycache__", "node_modules", ".venv", "venv",
              ".mypy_cache", "dist", "build", ".egg-info"}
SKIP_FILES = {"package-lock.json", "yarn.lock", "poetry.lock", "Pipfile.lock"}


def project_overview(root: str = ".", max_files: int = 60) -> str:
    """
    Returns a compact project overview:
    - Directory tree (2 levels)
    - Contents of key files: README, pyproject.toml, requirements.txt, main entry
    """
    p = Path(root).expanduser().resolve()
    sections = []

    # 1. Tree
    tree_lines = [f"Project: {p}"]
    _tree(p, tree_lines, prefix="", depth=0, max_depth=2, max_files=max_files)
    sections.append("\n".join(tree_lines))

    # 2. Key files — auto-detected
    key_candidates = [
        "README.md", "README.rst", "README.txt",
        "pyproject.toml", "setup.py", "setup.cfg",
        "requirements.txt", "requirements-dev.txt",
        "main.py", "app.py", "run.py", "cli.py",
        "Makefile", "docker-compose.yml",
    ]
    for name in key_candidates:
        candidate = p / name
        if candidate.exists() and candidate.stat().st_size < 8000:
            content = candidate.read_text(encoding="utf-8", errors="replace")
            sections.append(f"── {name} ──\n{content.strip()}")

    return "\n\n".join(sections)


def _tree(path: Path, lines: list, prefix: str, depth: int, max_depth: int, max_files: int):
    if depth > max_depth:
        return
    try:
        entries = sorted(path.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
    except PermissionError:
        return

    shown = 0
    for entry in entries:
        if entry.name in SKIP_DIRS or entry.name.startswith("."):
            continue
        if entry.is_file() and entry.name in SKIP_FILES:
            continue
        if shown >= max_files:
            lines.append(f"{prefix}  ... (truncated)")
            break

        connector = "└── " if entry == entries[-1] else "├── "
        size_hint = ""
        if entry.is_file():
            size = entry.stat().st_size
            size_hint = f"  ({size:,} B)" if size > 1024 else ""

        lines.append(f"{prefix}{connector}{entry.name}{size_hint}")
        shown += 1

        if entry.is_dir() and entry.name not in SKIP_DIRS:
            ext = "    " if entry == entries[-1] else "│   "
            _tree(entry, lines, prefix + ext, depth + 1, max_depth, max_files)


CONTEXT_BUDGET = 3000

def build_context_message(
    cwd: str = ".",
    extra_files: Optional[list[str]] = None,
    skill_index: str = "",
    budget: int = CONTEXT_BUDGET,
) -> str:
    """
    Build the initial context USER message injected at session start.
    This is NOT part of the system prompt — so the system prompt stays cache-stable.
    Total output is capped at `budget` chars (tree trimmed first, then key files).
    """
    header = (
        f"Today's date: {date.today().isoformat()}\n"
        f"Working directory: {Path(cwd).expanduser().resolve()}\n"
    )
    reserved = len(header)

    lipi_block = ""
    lipi_md = Path(cwd) / ".Lipi.md"
    if lipi_md.exists():
        content = lipi_md.read_text(encoding="utf-8", errors="replace")
        if len(content) > 4000:
            content = content[:4000] + "\n[... truncated ...]"
        lipi_block = f"\n── .Lipi.md ──\n{content}"
        reserved += len(lipi_block)

    skill_block = f"\n{skill_index}" if skill_index else ""
    reserved += len(skill_block)

    extra_block = ""
    if extra_files:
        for fpath in extra_files:
            p = Path(fpath).expanduser().resolve()
            if p.exists():
                content = p.read_text(encoding="utf-8", errors="replace")
                if len(content) > 4000:
                    content = content[:4000] + "\n[... truncated ...]"
                extra_block += f"\n── {p.name} (pre-loaded) ──\n{content}"
        reserved += len(extra_block)

    overview = project_overview(cwd)
    tree_budget = budget - reserved
    if len(overview) > tree_budget:
        overview = overview[:max(tree_budget, 200)] + "\n[... truncated ...]"

    return header + "\n" + overview + lipi_block + skill_block + extra_block
