"""
tools/__init__.py — Tool registry
Each tool is a plain Python function + an OpenAI-format schema dict.
Add a new tool: write the function, write the schema, add to TOOLS list.
"""

import os
import re
import json
import sys
import base64
import subprocess
import textwrap
import fnmatch
import threading
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Any

from tavily import TavilyClient

from config import cfg, PROFILES


# ── Helpers ───────────────────────────────────────────────────────────────────

def _truncate(text: str, limit: int = None) -> str:
    limit = limit or cfg.max_tool_output
    if len(text) <= limit:
        return text
    half = limit // 2
    return text[:half] + f"\n\n[... {len(text) - limit} chars truncated ...]\n\n" + text[-half:]


def _expand(path: str) -> Path:
    return Path(path).expanduser().resolve()


def _confirm(command: str) -> bool:
    """Ask the user before running dangerous commands."""
    for pattern in cfg.confirm_commands:
        if pattern in command:
            input_active.set()
            sys.stdout.write("\r\033[K")
            sys.stdout.flush()
            try:
                print(f"\n⚠  Command contains '{pattern}'.")
                answer = input("   Run? [y/N] ").strip().lower()
            finally:
                input_active.clear()
            return answer == "y"
    return True


# Set while a confirmation prompt is active — spinner checks this to pause
input_active = threading.Event()

# Paths the user has trusted for this session (via 't' response)
_trusted_paths: set[str] = set()


def _is_locked(path: Path) -> bool:
    """Check if a resolved path matches any locked pattern."""
    s = str(path)
    for pattern in cfg.locked_paths:
        expanded = str(Path(pattern).expanduser())
        if fnmatch.fnmatch(s, expanded):
            return True
    return False


def _confirm_write(path: Path, action: str = "write") -> bool:
    """
    Gate for file writes.  Returns True if allowed.
    - Locked paths: always blocked, no prompt.
    - Trusted paths (session): auto-allowed.
    - Otherwise: prompt y/n/t.
    """
    if _is_locked(path):
        print(f"\n🔒 BLOCKED — {path} matches a locked path. Cannot {action}.")
        return False

    if not cfg.confirm_writes:
        return True

    s = str(path)
    if s in _trusted_paths:
        return True

    input_active.set()
    sys.stdout.write("\r\033[K")
    sys.stdout.flush()
    try:
        while True:
            print(f"\n✏  {action.title()} → {path}")
            answer = input(
                "   Allow? [y]es / [n]o / [t]rust this path: "
            ).strip().lower()
            if answer == "y":
                return True
            if answer == "t":
                _trusted_paths.add(s)
                print(f"   ✓ Trusted for this session: {path}")
                return True
            if answer in ("n", ""):
                return False
    finally:
        input_active.clear()


# ── Tool implementations ───────────────────────────────────────────────────────

def shell(command: str, working_dir: str = ".") -> str:
    """Run a bash command, stream stdout+stderr, return combined output."""
    if not _confirm(command):
        return "Cancelled by user."

    wd = _expand(working_dir) if working_dir != "." else Path.cwd()
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}

    try:
        proc = subprocess.Popen(
            command, shell=True, cwd=wd, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
        )
        lines = []
        for line in proc.stdout:
            print(line, end="", flush=True)   # live stream
            lines.append(line)
        proc.wait(timeout=cfg.shell_timeout)
        output = "".join(lines)
        if proc.returncode != 0:
            output += f"\n[exit code: {proc.returncode}]"
        return _truncate(output)
    except subprocess.TimeoutExpired:
        proc.kill()
        return f"[Command timed out after {cfg.shell_timeout}s]"
    except Exception as e:
        return f"[Shell error: {e}]"


def read_file(path: str, start_line: int = None, end_line: int = None) -> str:
    """Read a file, optionally a line range. Output includes line numbers."""
    p = _expand(path)
    if not p.exists():
        return f"[File not found: {path}]"
    try:
        raw_lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        total = len(raw_lines)
        sl = (start_line or 1) - 1
        el = end_line or len(raw_lines)
        selected = raw_lines[sl:el]

        max_lines = 200
        truncated_lines = False
        if len(selected) > max_lines:
            selected = selected[:max_lines]
            truncated_lines = True

        numbered = [f"{sl + i + 1:>4}| {line}" for i, line in enumerate(selected)]
        shown_end = sl + len(selected)
        header = f"[{p} — {total} lines total, showing {sl+1}-{shown_end}]"
        result = header + "\n" + "\n".join(numbered)

        if truncated_lines:
            result += (f"\n[Output capped at {max_lines} lines. "
                       f"Use start_line/end_line for a specific range, "
                       f"or shell with grep -n to find symbols.]")

        return _truncate(result)
    except Exception as e:
        return f"[Read error: {e}]"


def write_file(path: str, content: str) -> str:
    """Write content to a file, creating parent dirs as needed."""
    p = _expand(path)
    if not _confirm_write(p, "write"):
        return f"[Write cancelled by user: {p}]"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"Written {len(content)} chars to {p}"


def _fuzzy_find(content: str, old_text: str):
    """Try exact match first, then whitespace-normalized match. Returns (start, end) or None."""
    idx = content.find(old_text)
    if idx != -1:
        count = content.count(old_text)
        if count == 1:
            return idx, idx + len(old_text), "exact"
        return None  # ambiguous

    def normalize(s):
        return re.sub(r'[ \t]+', ' ', s).strip()

    norm_old = normalize(old_text)
    lines = content.splitlines(keepends=True)
    old_lines = old_text.splitlines()
    old_len = len(old_lines)

    for i in range(len(lines) - old_len + 1):
        candidate = lines[i:i + old_len]
        candidate_norm = normalize("".join(candidate))
        if candidate_norm == norm_old:
            start = sum(len(l) for l in lines[:i])
            end = start + sum(len(l) for l in candidate)
            return start, end, "fuzzy"
    return None


def _closest_lines(content: str, old_text: str, n: int = 3) -> str:
    """Find the lines most similar to old_text's first line, for error hints."""
    first_line = old_text.strip().splitlines()[0].strip() if old_text.strip() else ""
    if not first_line:
        return ""
    from difflib import SequenceMatcher
    scored = []
    for i, line in enumerate(content.splitlines(), 1):
        ratio = SequenceMatcher(None, first_line, line.strip()).ratio()
        if ratio > 0.5:
            scored.append((ratio, i, line.rstrip()))
    scored.sort(reverse=True)
    if not scored:
        return ""
    hints = [f"  line {ln}: {txt}" for _, ln, txt in scored[:n]]
    return "Closest matches:\n" + "\n".join(hints)


def patch_file(path: str, old_text: str, new_text: str) -> str:
    """
    Replace a unique block of text in a file.
    old_text must match exactly once — use enough context lines to be unique.
    Falls back to whitespace-normalized matching if exact match fails.
    """
    p = _expand(path)
    if not p.exists():
        return f"[File not found: {path}]"
    if not _confirm_write(p, "patch"):
        return f"[Patch cancelled by user: {p}]"
    content = p.read_text(encoding="utf-8")

    match = _fuzzy_find(content, old_text)
    if match is None:
        hint = _closest_lines(content, old_text)
        msg = "[Patch failed: old_text not found in file]"
        if hint:
            msg += f"\n{hint}\nTip: use read_file to see exact content, then patch_lines with line numbers."
        return msg

    start, end, mode = match
    patched = content[:start] + new_text + content[end:]
    p.write_text(patched, encoding="utf-8")
    note = " (fuzzy whitespace match)" if mode == "fuzzy" else ""
    return f"Patched {p}{note} — replaced {end - start} chars with {len(new_text)} chars"


def patch_lines(path: str, start_line: int, end_line: int, new_text: str) -> str:
    """
    Replace lines start_line..end_line (inclusive, 1-indexed) with new_text.
    Use when patch_file fails due to inexact text matching.
    """
    p = _expand(path)
    if not p.exists():
        return f"[File not found: {path}]"
    if not _confirm_write(p, "patch_lines"):
        return f"[Patch cancelled by user: {p}]"
    lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
    total = len(lines)
    if start_line < 1 or end_line < start_line or start_line > total:
        return f"[Invalid range: {start_line}-{end_line} (file has {total} lines)]"
    end_line = min(end_line, total)
    removed = lines[start_line - 1 : end_line]
    if not new_text.endswith("\n"):
        new_text += "\n"
    lines[start_line - 1 : end_line] = [new_text]
    p.write_text("".join(lines), encoding="utf-8")
    return f"Patched {p} — replaced lines {start_line}-{end_line} ({len(removed)} lines) with new content"


def insert_lines(path: str, before_line: int, new_text: str) -> str:
    """
    Insert new_text before the given line number (1-indexed).
    Use before_line = total_lines + 1 to append at end of file.
    """
    p = _expand(path)
    if not p.exists():
        return f"[File not found: {path}]"
    if not _confirm_write(p, "insert_lines"):
        return f"[Insert cancelled by user: {p}]"
    lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
    total = len(lines)
    if before_line < 1 or before_line > total + 1:
        return f"[Invalid line: {before_line} (file has {total} lines, use 1-{total + 1})]"
    if not new_text.endswith("\n"):
        new_text += "\n"
    lines.insert(before_line - 1, new_text)
    p.write_text("".join(lines), encoding="utf-8")
    return f"Inserted content before line {before_line} in {p}"


def list_files(pattern: str = "**/*", base_dir: str = ".") -> str:
    """
    List files matching a glob pattern.
    Automatically skips .git, __pycache__, node_modules, *.pyc, .env.
    """
    SKIP = {".git", "__pycache__", "node_modules", ".venv", "venv", ".mypy_cache"}
    SKIP_EXT = {".pyc", ".pyo", ".egg-info"}

    base = _expand(base_dir)
    results = []
    for p in sorted(base.glob(pattern)):
        parts = set(p.parts)
        if parts & SKIP:
            continue
        if p.suffix in SKIP_EXT:
            continue
        rel = p.relative_to(base)
        size = f"{p.stat().st_size:>8,}" if p.is_file() else "     DIR"
        results.append(f"{size}  {rel}")

    if not results:
        return f"[No files matching '{pattern}' in {base}]"
    return "\n".join(results[:200])   # cap at 200 entries


def _tavily() -> TavilyClient:
    """Lazily instantiated Tavily client — fails clearly if key is missing."""
    if not cfg.tavily_api_key:
        raise RuntimeError("tavily_api_key not set in config.py")
    return TavilyClient(api_key=cfg.tavily_api_key)


def web_search(
    query: str,
    num_results: int = 8,
    search_depth: str = "basic",
    topic: str = "general",
    include_answer: bool = True,
) -> str:
    """
    Search the web via Tavily.

    search_depth: "basic" (fast, cheap) | "advanced" (deeper, costs 2 credits)
    topic:        "general" | "news"  — use "news" for stock/market queries
    include_answer: prepend Tavily's AI-synthesised answer snippet
    """
    try:
        client = _tavily()
        resp = client.search(
            query=query,
            max_results=num_results,
            search_depth=search_depth,
            topic=topic,
            include_answer=include_answer,
        )
    except Exception as e:
        return f"[Tavily search error: {e}]"

    lines = []

    # Tavily's own synthesised answer — very useful for factual queries
    if include_answer and resp.get("answer"):
        lines.append(f"Answer: {resp['answer']}\n")

    for r in resp.get("results", []):
        title   = r.get("title", "")
        url     = r.get("url", "")
        content = r.get("content", "").strip()
        score   = r.get("score", 0)
        lines.append(f"• {title}\n  {content[:300]}\n  {url}  [score={score:.2f}]")

    return "\n\n".join(lines) if lines else "[No results]"


def fetch_url(url: str, max_chars: int = 6000) -> str:
    """
    Fetch a URL and return clean text via Tavily Extract.
    Tavily handles JS-heavy pages, paywalls it can reach, and cleans the HTML —
    much better than raw urllib for modern sites.
    """
    try:
        client = _tavily()
        resp = client.extract(urls=[url])
        results = resp.get("results", [])
        if not results:
            return f"[Tavily extract: no content returned for {url}]"
        raw = results[0].get("raw_content", "") or results[0].get("content", "")
        return _truncate(raw.strip(), max_chars)
    except Exception as e:
        return f"[Tavily extract error: {e}]"


def vision(image_path: str, question: str = "Describe this image in detail.") -> str:
    """
    Send an image to the vision model for analysis.
    Useful for stock charts, screenshots, diagrams.
    Returns the model's text response.
    """
    import openai  # only needed here
    p = _expand(image_path)
    if not p.exists():
        return f"[Image not found: {image_path}]"

    suffix = p.suffix.lower()
    mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "gif": "image/gif", "webp": "image/webp"}.get(suffix[1:], "image/png")

    b64 = base64.b64encode(p.read_bytes()).decode()

    vcfg = PROFILES[cfg.vision_profile]
    client = openai.OpenAI(base_url=vcfg["base_url"], api_key="local")

    resp = client.chat.completions.create(
        model=vcfg["model"],
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": question},
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
            ],
        }],
        max_tokens=vcfg["max_tokens"],
    )
    return resp.choices[0].message.content


def python_repl(code: str) -> str:
    """
    Execute Python code in-process and return stdout + return value.
    Good for quick calculations, data exploration, regex testing.
    """
    import io, contextlib, traceback
    buf = io.StringIO()
    local_ns = {}
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            exec(compile(code, "<repl>", "exec"), local_ns)  # noqa: S102
        output = buf.getvalue()
        # If the last statement is an expression, show its value
        lines = code.strip().split("\n")
        try:
            val = eval(compile(lines[-1], "<repl>", "eval"), local_ns)  # noqa: S307
            if val is not None:
                output += f"\n→ {repr(val)}"
        except Exception:
            pass
        return output or "[No output]"
    except Exception:
        return f"[Error]\n{traceback.format_exc()}"


def duckdb_query(sql: str) -> str:
    """Run a SQL query against the local stock breadth DuckDB database."""
    try:
        import duckdb
    except ImportError:
        return "[duckdb not installed — run: pip install duckdb]"

    db_path = _expand(cfg.duckdb_path)
    if not db_path.exists():
        return f"[Database not found: {db_path}]"

    try:
        con = duckdb.connect(str(db_path), read_only=True)
        result = con.execute(sql).fetchdf()
        con.close()
        if result.empty:
            return "[Query returned no rows]"
        return _truncate(result.to_string(index=False))
    except Exception as e:
        return f"[DuckDB error: {e}]"


# ── Tool registry & schemas ───────────────────────────────────────────────────
# Each entry: ("function", schema_dict)
# The agent loop uses this to build the `tools=` parameter for the API call.

TOOL_FUNCTIONS = {
    "shell":        shell,
    "read_file":    read_file,
    "write_file":   write_file,
    "patch_file":   patch_file,
    "patch_lines":   patch_lines,
    "insert_lines":  insert_lines,
    "list_files":    list_files,
    "web_search":   web_search,
    "fetch_url":    fetch_url,
    "vision":       vision,
    "python_repl":  python_repl,
    "duckdb_query": duckdb_query,
}

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "shell",
            "description": "Run a bash command. Streams live output. Use for building, testing, installing packages, running scripts.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command":     {"type": "string", "description": "The bash command to run"},
                    "working_dir": {"type": "string", "description": "Working directory (default: current dir)"},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file's contents. Optionally specify a line range to read a section.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path":       {"type": "string", "description": "File path (absolute or relative, ~ supported)"},
                    "start_line": {"type": "integer", "description": "First line to read (1-indexed, optional)"},
                    "end_line":   {"type": "integer", "description": "Last line to read (inclusive, optional)"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write content to a file (creates or overwrites). For edits, prefer patch_lines or insert_lines instead.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path":    {"type": "string", "description": "File path"},
                    "content": {"type": "string", "description": "Full file content to write"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "patch_file",
            "description": "Replace a unique block of text in a file. old_text must match exactly once. Supports fuzzy whitespace matching. For large files, prefer patch_lines with line numbers instead.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path":     {"type": "string", "description": "File path"},
                    "old_text": {"type": "string", "description": "Exact text to find and replace (include enough context lines to be unique)"},
                    "new_text": {"type": "string", "description": "Replacement text"},
                },
                "required": ["path", "old_text", "new_text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "patch_lines",
            "description": "PREFERRED edit tool. Replace a range of lines by line number. Always use read_file first to see line numbers, then specify the range to replace. Most reliable for all file edits.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path":       {"type": "string", "description": "File path"},
                    "start_line": {"type": "integer", "description": "First line to replace (1-indexed, inclusive)"},
                    "end_line":   {"type": "integer", "description": "Last line to replace (1-indexed, inclusive)"},
                    "new_text":   {"type": "string", "description": "Replacement text (replaces the entire line range)"},
                },
                "required": ["path", "start_line", "end_line", "new_text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "insert_lines",
            "description": "Insert new content before a given line number without replacing anything. Use read_file first to find the right line number. Use before_line = last_line + 1 to append.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path":        {"type": "string", "description": "File path"},
                    "before_line": {"type": "integer", "description": "Line number to insert before (1-indexed). Use total_lines + 1 to append at end."},
                    "new_text":    {"type": "string", "description": "Text to insert"},
                },
                "required": ["path", "before_line", "new_text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files matching a glob pattern. Skips .git, __pycache__, node_modules automatically.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern":  {"type": "string", "description": "Glob pattern (e.g. '**/*.py', '*.md')"},
                    "base_dir": {"type": "string", "description": "Base directory to search from (default: current dir)"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Search the web via Tavily. For stock/market/news queries set topic='news'. "
                "Use search_depth='advanced' for thorough research (costs 2 credits). "
                "include_answer=true prepends a synthesised answer — leave on for factual queries."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query":          {"type": "string",  "description": "Search query"},
                    "num_results":    {"type": "integer", "description": "Number of results (default 8)"},
                    "search_depth":   {"type": "string",  "enum": ["basic", "advanced"],
                                       "description": "basic=fast, advanced=deeper (default: basic)"},
                    "topic":          {"type": "string",  "enum": ["general", "news"],
                                       "description": "general or news (default: general)"},
                    "include_answer": {"type": "boolean", "description": "Prepend AI answer snippet (default: true)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": "Fetch a URL and return its text content. Use after web_search to read a full article or doc page.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url":       {"type": "string", "description": "Full URL to fetch"},
                    "max_chars": {"type": "integer", "description": "Max characters to return (default 6000)"},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "vision",
            "description": "Analyse an image using the vision model. Use for stock charts, screenshots, diagrams.",
            "parameters": {
                "type": "object",
                "properties": {
                    "image_path": {"type": "string", "description": "Path to the image file"},
                    "question":   {"type": "string", "description": "What to ask about the image"},
                },
                "required": ["image_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "python_repl",
            "description": "Execute Python code in-process. Good for quick calculations, data exploration, regex testing.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Python code to execute"},
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "duckdb_query",
            "description": "Run a SQL query against the local stock breadth DuckDB database. Tables include symbol_trend_history.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sql": {"type": "string", "description": "SQL query to execute (read-only)"},
                },
                "required": ["sql"],
            },
        },
    },
]
