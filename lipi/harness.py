#!/usr/bin/env python3
"""
harness.py — Main entry point
Usage:
  python harness.py                        # interactive REPL in current dir
  python harness.py --profile analyst      # use analyst (32B) profile
  python harness.py --resume SESSION_ID    # continue a previous session
  python harness.py --sessions             # list saved sessions
  python harness.py "do this one thing"    # single-shot non-interactive
  python harness.py --no-context           # skip project context injection
"""

import argparse
import os
import re
import readline
import sys
from pathlib import Path


# ── Make harness/ importable from wherever the script is invoked ──────────────
sys.path.insert(0, str(Path(__file__).parent))

from config import cfg, PROFILES
from agent import Agent
from context.packer import build_context_message
from context.memory import list_sessions, clean_sessions
from context.tokens import context_usage, estimate_tokens


# ── ANSI colours (skip if not a TTY) ─────────────────────────────────────────
IS_TTY = sys.stdout.isatty()

def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if IS_TTY else text

def _rl(code: str, text: str) -> str:
    """ANSI color wrapped in readline invisible markers (\001..\002) for correct line length calculation."""
    if not IS_TTY:
        return text
    return f"\001\033[{code}m\002{text}\001\033[0m\002"

BOLD          = lambda t: _c("1",    t)
DIM           = lambda t: _c("2",    t)
CYAN          = lambda t: _c("36",   t)
BOLD_CYAN     = lambda t: _c("1;36", t)
GREEN         = lambda t: _c("32",   t)
YELLOW        = lambda t: _c("33",   t)
ERROR_COLOR   = lambda t: _c("1;31", t)
MAGENTA       = lambda t: _c("35",   t)


# ── Markdown rendering ───────────────────────────────────────────────────────

def _inline(text: str) -> str:
    """Apply inline markdown: `code`, **bold**, *italic*."""
    text = re.sub(r'`([^`]+)`', lambda m: CYAN(m.group(1)), text)
    text = re.sub(r'\*\*(.+?)\*\*', lambda m: BOLD(m.group(1)), text)
    text = re.sub(r'(?<!\*)\*([^*]+?)\*(?!\*)', lambda m: _c("3", m.group(1)), text)
    return text


def _render_md(text: str) -> str:
    """Convert markdown to ANSI-formatted terminal output."""
    if not IS_TTY:
        return text

    lines = text.split('\n')
    result = []
    in_code = False

    for line in lines:
        if line.startswith('```'):
            in_code = not in_code
            if in_code:
                lang = line[3:].strip()
                result.append(DIM(f"  ┌─ {lang}") if lang else DIM("  ┌─"))
            else:
                result.append(DIM("  └─"))
            continue

        if in_code:
            result.append(DIM("  │") + " " + CYAN(line))
            continue

        m = re.match(r'^(#{1,3}) (.+)', line)
        if m:
            level = len(m.group(1))
            heading = m.group(2)
            if level == 1:
                result.append(_c("1;4", heading))
            else:
                result.append(BOLD(heading))
            continue

        if re.match(r'^[-*]{3,}\s*$', line):
            result.append(DIM("─" * 40))
            continue

        if line.startswith('> '):
            result.append(DIM("│ ") + _c("3", _inline(line[2:])))
            continue

        m = re.match(r'^(\s*)[-*] (.+)', line)
        if m:
            result.append(f"{m.group(1)}{CYAN('•')} {_inline(m.group(2))}")
            continue

        m = re.match(r'^(\s*)(\d+)\. (.+)', line)
        if m:
            result.append(f"{m.group(1)}{CYAN(m.group(2) + '.')} {_inline(m.group(3))}")
            continue

        result.append(_inline(line))

    return '\n'.join(result)


# ── REPL ──────────────────────────────────────────────────────────────────────

def _help_text():
    h = lambda cmd, desc: f"  {CYAN(cmd.ljust(16))}{desc}"
    return "\n".join([
        "",
        BOLD("  Commands"),
        h("/help",         "this message"),
        h("/profile NAME", "switch model profile"),
        h("/sessions",     "list saved sessions"),
        h("/resume ID",    "load a past session"),
        h("/context",      "re-inject project context"),
        h("/clear",        "clear history (keep system prompt)"),
        h("/cd PATH",      "change working directory"),
        h("/tools",        "list available tools"),
        h("/ctx",          "show context window usage"),
        h("/init",         "generate/update .Lipi.md for this project"),
        h("/clean [N]",    "delete saved sessions (keep last N)"),
        h("/exit",         "quit  (also: Ctrl-D, /quit, exit)"),
        "",
        BOLD("  Multiline input"),
        f"  End a line with {CYAN(chr(92))}     to continue on the next line",
        f"  Start with {CYAN('\"\"\"')}        to enter a block (close with \"\"\")",
        "",
    ])


_COMMANDS = {
    "/help":     "show help",
    "/profile":  "switch model profile",
    "/ctx":      "context window usage",
    "/sessions": "list saved sessions",
    "/resume":   "load a past session",
    "/context":  "re-inject project context",
    "/clear":    "clear history",
    "/cd":       "change working directory",
    "/tools":    "list available tools",
    "/init":     "generate/update .Lipi.md",
    "/clean":    "delete saved sessions",
    "/exit":     "quit",
    "/quit":     "quit",
}

def _path_matches(text: str) -> list[str]:
    """Complete filesystem paths (files and directories)."""
    if text.startswith("~"):
        expanded = os.path.expanduser(text)
    else:
        expanded = text

    if os.path.isdir(expanded) and text.endswith("/"):
        parent, prefix = expanded, ""
    else:
        parent, prefix = os.path.split(expanded)

    parent = parent or "."
    try:
        entries = os.listdir(parent)
    except OSError:
        return []

    matches = []
    for name in entries:
        if name.startswith(".") and not prefix.startswith("."):
            continue
        if name.startswith(prefix):
            full = os.path.join(parent, name)
            # Reconstruct with the user's original prefix (~ etc.)
            if text.endswith("/"):
                display = text + name
            elif os.path.sep in text or text.startswith("~"):
                display = os.path.join(os.path.dirname(text), name)
            else:
                display = name
            if os.path.isdir(full):
                display += "/"
            matches.append(display)

    return sorted(matches)


def _completer(text, state):
    if text.startswith("/"):
        matches = [c for c in _COMMANDS if c.startswith(text)]
    else:
        matches = _path_matches(text)
    return matches[state] if state < len(matches) else None


_current_prompt = ""


def _display_matches(substitution, matches, longest_match_length):
    print()
    for m in matches:
        desc = _COMMANDS.get(m, "")
        if desc:
            cmd = f"\033[36m{m}\033[0m"
            print(f"  {cmd.ljust(26)}{_c('2', desc)}")
        else:
            is_dir = m.endswith("/")
            color = "1;34" if is_dir else "0"
            print(f"  {_c(color, m)}")
    sys.stdout.write(_current_prompt + readline.get_line_buffer())
    sys.stdout.flush()


def _context_meter(agent: Agent) -> str:
    cw = agent.context_window
    usage = context_usage(agent.messages, cw)
    pct = int(usage * 100)
    est = estimate_tokens(agent.messages)
    label = f" {pct}% ctx [{est:,}/{cw:,}] "
    bar_width = 38 - len(label)
    bar = "─" * max(bar_width, 2)
    if pct >= 80:
        color = "1;31"
    elif pct >= 60:
        color = "33"
    else:
        color = "2"
    return f"\033[{color}m  ──{label}{bar}\033[0m" if IS_TTY else f"  --{label}{'─' * bar_width}"


def _short_model(model: str) -> str:
    """Strip provider prefix from model name: 'google/gemma-4-12b-qat' → 'gemma-4-12b-qat'"""
    return model.rsplit("/", 1)[-1] if "/" in model else model


_LOGO = """\
\033[1;36m  ██╗     ██╗ ██████╗  ██╗\033[0m
\033[1;36m  ██║     ██║ ██╔══██╗ ██║\033[0m
\033[1;36m  ██║     ██║ ██████╔╝ ██║\033[0m
\033[36m  ██║     ██║ ██╔═══╝  ██║\033[0m
\033[36m  ███████╗██║ ██║      ██║\033[0m
\033[2;36m  ╚══════╝╚═╝ ╚═╝      ╚═╝\033[0m"""

_LOGO_PLAIN = """\
  ██╗     ██╗ ██████╗  ██╗
  ██║     ██║ ██╔══██╗ ██║
  ██║     ██║ ██████╔╝ ██║
  ██║     ██║ ██╔═══╝  ██║
  ███████╗██║ ██║      ██║
  ╚══════╝╚═╝ ╚═╝      ╚═╝"""


def _banner(agent: Agent, cwd: Path):
    model = _short_model(agent.profile.get("model", "?"))
    ctx = f"{agent.context_window // 1024}K"
    info = f"  {GREEN(model)} · {YELLOW(agent.profile_name)} · {DIM(ctx + ' ctx')}"

    print()
    print(_LOGO if IS_TTY else _LOGO_PLAIN)
    print(DIM("  local agentic coding harness"))
    print()
    print(info)
    print(f"  {DIM('session')} {DIM(agent.session_id)}")
    print(f"  {DIM(str(cwd))}")
    print(f"  {DIM('Type /help for commands, Ctrl-D to quit')}")
    print()


def repl(agent: Agent, inject_context: bool, one_shot: str = None):
    cwd = Path.cwd()

    # Set up readline: history + tab completion
    history_path = Path("~/.harness/history").expanduser()
    history_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        readline.read_history_file(history_path)
    except FileNotFoundError:
        pass
    readline.set_history_length(500)
    readline.set_completer(_completer)
    readline.set_completion_display_matches_hook(_display_matches)
    readline.set_completer_delims(" \t")
    if "libedit" in (readline.__doc__ or ""):
        readline.parse_and_bind("bind ^I rl_complete")
    else:
        readline.parse_and_bind("tab: complete")

    import atexit
    atexit.register(readline.write_history_file, str(history_path))

    # Inject project context at session start
    if inject_context and not one_shot:
        context = build_context_message(str(cwd))
        agent.inject_context(context)

    if one_shot:
        response = agent.chat(one_shot)
        if response:
            print(response)
        return

    _banner(agent, cwd)

    def _prompt():
        global _current_prompt
        p = _rl("1;36", f"{agent.profile_name}") + _rl("2", " ▸ ")
        _current_prompt = p
        return p

    while True:
        try:
            raw = input(_prompt()).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not raw:
            continue

        # Multiline: line ending with \ continues on next line,
        # or start with """ to enter a block (close with """)
        if raw == '"""' or raw.startswith('"""'):
            lines = [raw[3:]] if len(raw) > 3 else []
            try:
                while True:
                    line = input(_rl("2", "  · "))
                    if line.rstrip().endswith('"""'):
                        lines.append(line.rstrip()[:-3])
                        break
                    lines.append(line)
            except (EOFError, KeyboardInterrupt):
                print()
                continue
            raw = "\n".join(lines).strip()
            if not raw:
                continue
        else:
            while raw.endswith("\\"):
                try:
                    raw = raw[:-1] + "\n" + input(_rl("2", "  · "))
                except (EOFError, KeyboardInterrupt):
                    break

        # ── Built-in commands ──────────────────────────────────────────────────
        if raw in ("/exit", "/quit", "exit", "quit"):
            break

        if raw == "/help":
            print(_help_text())
            continue

        if raw == "/tools":
            from tools import TOOL_FUNCTIONS
            print("  " + "  ".join(CYAN(t) for t in TOOL_FUNCTIONS.keys()))
            continue

        if raw == "/sessions":
            sessions = list_sessions(with_description=True)
            if sessions:
                for s in sessions:
                    print(f"  {s['id']}  ({s['messages']} msgs)  {DIM(s['description'])}")
            else:
                print("  No saved sessions.")
            continue

        if raw == "/clean" or raw.startswith("/clean "):
            parts = raw.split(None, 1)
            keep = int(parts[1]) if len(parts) > 1 else 0
            deleted = clean_sessions(keep_last=keep)
            print(f"  Deleted {deleted} session(s).")
            continue

        if raw.startswith("/resume "):
            sid = raw[8:].strip()
            agent.session_id = sid
            from context.memory import load_session
            loaded = load_session(sid)
            if loaded:
                agent.messages = loaded
                print(f"  Loaded session '{sid}' ({len(loaded)} messages)")
            else:
                print(f"  Session '{sid}' not found.")
            continue

        if raw.startswith("/profile "):
            name = raw[9:].strip()
            if name in PROFILES:
                agent.profile_name = name
                agent.profile = PROFILES[name]
                import openai
                agent.client = openai.OpenAI(
                    base_url=agent.profile["base_url"], api_key="local", timeout=120
                )
                model = _short_model(agent.profile.get("model", "?"))
                print(f"  Switched to {YELLOW(name)} ({GREEN(model)})")
            else:
                print(f"  Unknown profile. Available: {', '.join(PROFILES)}")
            continue

        if raw.startswith("/cd "):
            path = Path(raw[4:].strip()).expanduser().resolve()
            if path.is_dir():
                os.chdir(path)
                cwd = path
                print(f"  cwd → {cwd}")
            else:
                print(f"  Not a directory: {path}")
            continue

        if raw == "/ctx":
            cw = agent.context_window
            usage = context_usage(agent.messages, cw)
            est = estimate_tokens(agent.messages)
            n_msgs = len(agent.messages)
            n_tool = sum(1 for m in agent.messages if m.get("role") == "tool")
            print(f"  {BOLD('Context usage')}  {usage:.0%}  ({est:,} / {cw:,} est. tokens)")
            print(f"  {DIM('Messages')}       {n_msgs}  ({n_tool} tool results)")
            continue

        if raw == "/context":
            context = build_context_message(str(cwd))
            agent.inject_context(context)
            print(DIM(f"  [context refreshed from {cwd}]"))
            continue

        if raw == "/init":
            from context.init_md import generate_lipi_md
            print(DIM("  Generating .Lipi.md ..."))
            content = generate_lipi_md(
                str(cwd),
                client=agent.client,
                model=agent.profile.get("model"),
            )
            out = cwd / ".Lipi.md"
            out.write_text(content, encoding="utf-8")
            print(f"  {GREEN('✓')} Written {CYAN(str(out))}")
            continue

        if raw == "/clear":
            agent.messages = [{"role": "system", "content": agent.messages[0]["content"]}]
            print("  History cleared.")
            continue

        # ── Normal message → agent ─────────────────────────────────────────────
        try:
            response = agent.chat(raw)
            if response:
                if not cfg.stream_output:
                    if cfg.render_markdown:
                        print(f"\n{_render_md(response)}")
                    else:
                        print(f"\n{response}\n")
                print(_context_meter(agent))
                print()
        except KeyboardInterrupt:
            print(f"\n{DIM('[interrupted]')}\n")
        except Exception as e:
            print(f"\n{ERROR_COLOR(f'Error: {e}')}\n")
            import traceback; traceback.print_exc()


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Local LLM coding harness",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("task", nargs="?", help="Single-shot task (non-interactive)")
    parser.add_argument("--profile",    default=cfg.profile, choices=list(PROFILES),
                        help="Model profile to use")
    parser.add_argument("--resume",     metavar="SESSION_ID",
                        help="Resume a saved session")
    parser.add_argument("--sessions",   action="store_true",
                        help="List saved sessions and exit")
    parser.add_argument("--clean-sessions", nargs="?", const=0, type=int, metavar="KEEP",
                        help="Delete saved sessions (optionally keep last N)")
    parser.add_argument("--no-context", action="store_true",
                        help="Skip project context injection at startup")
    parser.add_argument("--no-stream",  action="store_true",
                        help="Disable streaming (blocking mode)")
    parser.add_argument("--no-render",  action="store_true",
                        help="Disable markdown rendering (plain text output)")
    parser.add_argument("--timings",    action="store_true",
                        help="Show token/sec after each call")
    args = parser.parse_args()

    # Apply CLI overrides to config
    cfg.profile          = args.profile
    cfg.stream_output    = not args.no_stream
    cfg.render_markdown  = not args.no_render
    cfg.show_timings     = args.timings

    if args.sessions:
        sessions = list_sessions(with_description=True)
        if sessions:
            for s in sessions:
                print(f"  {s['id']}  ({s['messages']} msgs)  {s['description']}")
        else:
            print("No saved sessions.")
        return

    if args.clean_sessions is not None:
        deleted = clean_sessions(keep_last=args.clean_sessions)
        print(f"Deleted {deleted} session(s).")
        return

    # Check openai is installed
    try:
        import openai  # noqa
    except ImportError:
        print("Error: openai package not installed. Run: pip install openai")
        sys.exit(1)

    agent = Agent(
        profile=args.profile,
        session_id=args.resume,
    )

    repl(
        agent,
        inject_context=not args.no_context,
        one_shot=args.task,
    )


if __name__ == "__main__":
    main()
