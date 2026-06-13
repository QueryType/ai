"""
context/init_md.py — Generate or update .Lipi.md for the current project.

Produces a living project context file with:
- LLM-generated description (falls back to placeholder if server is down)
- Structured sections (mostly empty) for the LLM to fill over time
- Mechanical data: git state, recent commits, TODOs
"""

import subprocess
from datetime import date
from pathlib import Path
from typing import Optional

from context.packer import project_overview, SKIP_DIRS

NO_LLM_PLACEHOLDER = "*(run `/init` again with a model available to generate)*"

SECTIONS = [
    ("## Description", None),            # filled by LLM or placeholder
    ("## Architecture", ""),
    ("## Conventions", ""),
    ("## Key decisions", ""),
    ("## Work in progress", None),       # filled mechanically from git
    ("## Recent activity", None),        # filled mechanically from git
    ("## TODOs / FIXMEs", None),         # filled mechanically from source scan
    ("## Notes", ""),
]


def _run(cmd: list[str], cwd: str = ".", timeout: int = 10) -> str:
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True,
            cwd=cwd, timeout=timeout,
        )
        return r.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return ""


def _llm_description(client, model: str, tree: str) -> Optional[str]:
    """Ask the LLM for a one-paragraph project description."""
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{
                "role": "user",
                "content": (
                    "Below is a project's file tree and key files. "
                    "Write a single short paragraph (3-4 sentences) describing "
                    "what this project is, what it does, and the main technologies used. "
                    "Be specific, not generic. No headings, no bullet points.\n\n"
                    f"{tree}"
                ),
            }],
            temperature=0.3,
            max_tokens=300,
        )
        return resp.choices[0].message.content.strip()
    except Exception:
        return None


def _git_state(cwd: str) -> str:
    if not Path(cwd, ".git").exists():
        return ""

    lines = []
    branch = _run(["git", "branch", "--show-current"], cwd)
    if branch:
        lines.append(f"- **Branch:** `{branch}`")

    status = _run(["git", "status", "--short"], cwd)
    if status:
        changed = len(status.splitlines())
        lines.append(f"- **Uncommitted changes:** {changed} file(s)")
    else:
        lines.append("- Working tree clean")

    return "\n".join(lines)


def _wip_section(cwd: str) -> str:
    if not Path(cwd, ".git").exists():
        return ""

    branch = _run(["git", "branch", "--show-current"], cwd)
    if not branch or branch in ("main", "master"):
        return _git_state(cwd)

    lines = [_git_state(cwd)]

    ahead = _run(["git", "log", "--oneline", f"main..{branch}"], cwd)
    if not ahead:
        ahead = _run(["git", "log", "--oneline", f"master..{branch}"], cwd)
    if ahead:
        lines.append("")
        lines.append(f"**Commits ahead on `{branch}`:**")
        for entry in ahead.strip().splitlines():
            lines.append(f"- `{entry}`")

    return "\n".join(lines)


def _recent_activity(cwd: str, n: int = 10) -> str:
    if not Path(cwd, ".git").exists():
        return ""

    log = _run(["git", "log", f"-{n}", "--format=%h %s (%ar)"], cwd)
    if not log:
        return ""

    lines = []
    for entry in log.splitlines():
        lines.append(f"- `{entry}`")
    return "\n".join(lines)


def _todo_scan(cwd: str) -> str:
    p = Path(cwd).resolve()
    code_exts = {".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".sh"}
    todos = []
    for f in p.rglob("*"):
        if any(part in SKIP_DIRS for part in f.parts):
            continue
        if f.suffix not in code_exts or not f.is_file():
            continue
        try:
            for i, line in enumerate(f.read_text(errors="replace").splitlines(), 1):
                for tag in ("TODO", "FIXME", "HACK"):
                    if tag in line:
                        rel = f.relative_to(p)
                        comment = line.strip()
                        if len(comment) > 120:
                            comment = comment[:120] + "…"
                        todos.append(f"- `{rel}:{i}` — {comment}")
                        break
        except OSError:
            continue
        if len(todos) >= 30:
            break

    return "\n".join(todos) if todos else ""


def _read_existing(path: Path) -> dict[str, str]:
    """Parse existing .Lipi.md into section_heading -> content."""
    if not path.exists():
        return {}

    text = path.read_text(encoding="utf-8", errors="replace")
    sections = {}
    current_heading = None
    current_lines = []

    for line in text.splitlines():
        if line.startswith("## "):
            if current_heading:
                sections[current_heading] = "\n".join(current_lines).strip()
            current_heading = line
            current_lines = []
        elif current_heading:
            current_lines.append(line)

    if current_heading:
        sections[current_heading] = "\n".join(current_lines).strip()

    return sections


def generate_lipi_md(cwd: str = ".", client=None, model: str = None) -> str:
    p = Path(cwd).resolve()
    lipi_path = p / ".Lipi.md"
    existing = _read_existing(lipi_path)

    tree = project_overview(cwd, max_files=40)

    # LLM description — try LLM, fall back to existing, then placeholder
    description = None
    if client and model:
        description = _llm_description(client, model, tree)
    if not description:
        description = existing.get("## Description") or NO_LLM_PLACEHOLDER

    # Mechanical sections
    mechanical = {
        "## Work in progress": _wip_section(cwd),
        "## Recent activity": _recent_activity(cwd),
        "## TODOs / FIXMEs": _todo_scan(cwd),
    }

    # Build output
    parts = [
        f"# {p.name}",
        f"*Updated {date.today().isoformat()} by `lipi /init`*",
        f"## Project structure\n\n```\n{tree}\n```",
    ]

    for heading, default_content in SECTIONS:
        if heading in mechanical:
            content = mechanical[heading]
        elif heading == "## Description":
            content = description
        else:
            # Preserve existing content for editable sections; empty if new
            content = existing.get(heading, default_content or "")

        parts.append(f"{heading}\n\n{content}" if content else heading)

    return "\n\n".join(parts) + "\n"
