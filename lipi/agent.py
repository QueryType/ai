"""
agent.py — The agentic loop
Sends messages to the LLM, executes tool calls, feeds results back, repeats.
"""

import json
import os
import re
import sys
import threading
import time
from pathlib import Path
from typing import Optional

import openai

from config import cfg, PROFILES
from tools import TOOL_FUNCTIONS, TOOL_SCHEMAS, input_active
from context.memory import needs_compaction, compact, save_session, load_session, age_tool_outputs, increment_seen, strip_internal_fields
from context.tokens import calibrate, context_usage


SYSTEM_PROMPT = (Path(__file__).parent / "prompts" / "system.md").read_text()

_SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

class Spinner:
    """Braille dot spinner that runs in a background thread."""
    def __init__(self, label: str = "thinking"):
        self._label = label
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self):
        if not sys.stdout.isatty():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()

    def update_label(self, label: str):
        self._label = label

    def stop(self):
        if self._thread is None:
            return
        self._stop.set()
        self._thread.join()
        self._thread = None
        sys.stdout.write("\r\033[K")
        sys.stdout.flush()

    def _spin(self):
        i = 0
        while not self._stop.is_set():
            if not input_active.is_set():
                frame = _SPINNER_FRAMES[i % len(_SPINNER_FRAMES)]
                sys.stdout.write(f"\r\033[2m  {frame} {self._label}\033[0m")
                sys.stdout.flush()
                i += 1
            self._stop.wait(0.08)

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *_):
        self.stop()


# ── Live markdown rendering ──────────────────────────────────────────────────

_B = "\033[1m"     # bold
_D = "\033[2m"     # dim
_I = "\033[3m"     # italic
_U = "\033[4m"     # underline
_C = "\033[36m"    # cyan
_R = "\033[0m"     # reset


def _inline_ansi(text: str) -> str:
    text = re.sub(r'`([^`]+)`', f'{_C}\\1{_R}', text)
    text = re.sub(r'\*\*(.+?)\*\*', f'{_B}\\1{_R}', text)
    text = re.sub(r'(?<!\*)\*([^*]+?)\*(?!\*)', f'{_I}\\1{_R}', text)
    return text


def _render_line(line: str, in_code: bool) -> str:
    if not sys.stdout.isatty():
        return line

    if line.startswith('```'):
        if not in_code:
            lang = line[3:].strip()
            return f"{_D}  ┌─ {lang}{_R}" if lang else f"{_D}  ┌─{_R}"
        return f"{_D}  └─{_R}"

    if in_code:
        return f"{_D}  │{_R} {_C}{line}{_R}"

    m = re.match(r'^(#{1,3}) (.+)', line)
    if m:
        heading = m.group(2)
        return f"{_B}{_U}{heading}{_R}" if len(m.group(1)) == 1 else f"{_B}{heading}{_R}"

    if re.match(r'^[-*]{3,}\s*$', line):
        return f"{_D}{'─' * 40}{_R}"

    if line.startswith('> '):
        return f"{_D}│{_R} {_I}{_inline_ansi(line[2:])}{_R}"

    m = re.match(r'^(\s*)[-*] (.+)', line)
    if m:
        return f"{m.group(1)}{_C}•{_R} {_inline_ansi(m.group(2))}"

    m = re.match(r'^(\s*)(\d+)\. (.+)', line)
    if m:
        return f"{m.group(1)}{_C}{m.group(2)}.{_R} {_inline_ansi(m.group(3))}"

    return _inline_ansi(line)


class Agent:
    def __init__(self, profile: Optional[str] = None, session_id: Optional[str] = None):
        self.profile_name = profile or cfg.profile
        self.profile = PROFILES[self.profile_name]

        self.client = openai.OpenAI(
            base_url=self.profile["base_url"],
            api_key="local",                    # llama-server ignores this
            timeout=120,
        )

        self.context_window = _detect_context_window(
            self.profile["base_url"],
            self.profile.get("model", ""),
            self.profile.get("context_window"),
        )

        self.session_id = session_id or _new_session_id()
        self.messages: list[dict] = []
        self.iteration = 0
        self.last_prompt_tokens: Optional[int] = None
        self.turn_count = 0

        # Load existing session if resuming
        if session_id:
            loaded = load_session(session_id)
            if loaded:
                self.messages = loaded
                print(f"  Resumed session '{session_id}' ({len(self.messages)} messages)")

        # Always starts with the system prompt
        if not self.messages or self.messages[0]["role"] != "system":
            self.messages.insert(0, {"role": "system", "content": SYSTEM_PROMPT})

    # ── Public API ─────────────────────────────────────────────────────────────

    def chat(self, user_input: str) -> str:
        """Single-turn: add user message, run the loop, return final assistant text."""
        self.messages.append({"role": "user", "content": user_input})
        self.turn_count += 1

        if needs_compaction(
            self.messages,
            context_window=self.context_window,
            turn_count=self.turn_count,
        ):
            self.messages = compact(self.messages, self.client, self.context_window)

        return self._run_loop()

    def switch_profile(self, name: str):
        """Switch to another profile: new client + re-detect the context window."""
        self.profile_name = name
        self.profile = PROFILES[name]
        self.client = openai.OpenAI(
            base_url=self.profile["base_url"],
            api_key="local",
            timeout=120,
        )
        self.context_window = _detect_context_window(
            self.profile["base_url"],
            self.profile.get("model", ""),
            self.profile.get("context_window"),
        )

    def inject_context(self, context_text: str):
        """Prepend project context as a user message (called at session start)."""
        self.messages.append({
            "role": "user",
            "content": f"[Project context — read-only, for orientation]\n{context_text}",
        })
        self.messages.append({
            "role": "assistant",
            "content": "Noted. Ready.",
        })

    # ── Core loop ─────────────────────────────────────────────────────────────

    def _run_loop(self) -> str:
        """Run the tool-call loop until the model returns a final text response."""
        self.iteration = 0
        final_text = ""
        empty_streak = 0

        context_window = self.context_window
        force_short = False

        while self.iteration < cfg.max_iterations:
            self.iteration += 1

            # Age old tool outputs (only under context pressure) and track seen counts
            usage = context_usage(self.messages, context_window)
            aged = age_tool_outputs(self.messages, usage)
            increment_seen(self.messages)

            if self.iteration > 1:
                parts = [f"ctx {usage:.0%}"]
                if aged:
                    parts.append(f"aged {aged}")
                print(f"  \033[2m[{' · '.join(parts)}]\033[0m")

            # Call the LLM (with shortened max_tokens if context is tight)
            response = self._call_llm(max_tokens_override=512 if force_short else None)
            if response.usage and hasattr(response.usage, "prompt_tokens"):
                self.last_prompt_tokens = response.usage.prompt_tokens
                calibrate(self.messages, self.last_prompt_tokens)

            choice = response.choices[0]
            msg = choice.message

            # Detect degenerate turns: no content and no valid tool calls
            has_content = bool(msg.content and msg.content.strip())
            valid_tools = [
                tc for tc in (msg.tool_calls or [])
                if tc.function.name in TOOL_FUNCTIONS
            ]

            if not has_content and not valid_tools:
                empty_streak += 1
                all_tool_calls = msg.tool_calls or []
                rejected = [tc.function.name for tc in all_tool_calls if tc.function.name not in TOOL_FUNCTIONS]
                if rejected:
                    print(f"  ⚠ Model called unknown tools: {rejected}")
                if all_tool_calls and not rejected:
                    print(f"  ⚠ Empty response (no content, no tool calls)")
                elif not all_tool_calls:
                    print(f"  ⚠ Model returned empty content with no tool calls (attempt {empty_streak}/3)")
                if empty_streak >= 3:
                    final_text = "[Stopped: model produced no output or tool calls]"
                    break
                # Nudge so the retry isn't a byte-identical request (matters at temp=0)
                self.messages.append({
                    "role": "user",
                    "content": "[Your last response was empty. Reply with a tool call or your final answer as text.]",
                })
                continue
            empty_streak = 0

            # Append assistant turn to history
            assistant_turn = {"role": "assistant", "content": msg.content or ""}
            if valid_tools:
                assistant_turn["tool_calls"] = [
                    {
                        "id":       tc.id,
                        "type":     "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in valid_tools
                ]
            self.messages.append(assistant_turn)

            # If no tool calls → we're done
            if not valid_tools:
                final_text = msg.content or ""
                break

            # Execute tool calls
            for tc in valid_tools:
                result = self._execute_tool(tc)
                self.messages.append({
                    "role":         "tool",
                    "tool_call_id": tc.id,
                    "content":      result,
                })

            # Mid-turn context protection
            usage = context_usage(self.messages, context_window)
            if usage >= cfg.mid_turn_abort:
                final_text = "[Stopped: context window nearly full]"
                break
            elif usage >= cfg.mid_turn_warn and not force_short:
                print(f"\n  \033[33m[context at {usage:.0%} — wrapping up]\033[0m")
                force_short = True

        else:
            final_text = f"[Loop stopped after {cfg.max_iterations} iterations]"

        save_session(self.session_id, strip_internal_fields(self.messages))

        return final_text

    def _call_llm(self, max_tokens_override: int = None) -> openai.types.chat.ChatCompletion:
        """Call the LLM. Uses streaming if cfg.stream_output, else blocking."""
        kwargs = dict(
            model=self.profile["model"],
            messages=strip_internal_fields(self.messages),
            tools=TOOL_SCHEMAS,
            tool_choice="auto",
            temperature=self.profile["temperature"],
            max_tokens=max_tokens_override or self.profile["max_tokens"],
        )

        if cfg.stream_output:
            return self._call_streaming(**kwargs)
        else:
            t0 = time.time()
            with Spinner("thinking"):
                resp = self.client.chat.completions.create(**kwargs)
            if cfg.show_timings:
                elapsed = time.time() - t0
                usage = resp.usage
                if usage:
                    print(f"\n  [{usage.completion_tokens} tokens in {elapsed:.1f}s = {usage.completion_tokens/elapsed:.0f} t/s]")
            return resp

    def _call_streaming(self, **kwargs) -> openai.types.chat.ChatCompletion:
        """
        Stream from the LLM with live markdown rendering.
        Completed lines are rendered immediately; the partial line streams raw
        and gets replaced with its rendered form once the newline arrives.
        """
        kwargs["stream"] = True
        kwargs["stream_options"] = {"include_usage": True}

        t0 = time.time()
        spinner = Spinner("thinking")
        spinner.start()

        stream = self.client.chat.completions.create(**kwargs)

        full_content = ""
        tool_calls_raw = {}
        finish_reason = None
        usage_data = None
        line_buffer = ""
        in_code_block = False
        content_started = False
        try:
            term_cols = os.get_terminal_size().columns - 2
        except OSError:
            term_cols = 78

        for chunk in stream:
            if not chunk.choices:
                if hasattr(chunk, "usage") and chunk.usage:
                    usage_data = chunk.usage
                continue
            delta = chunk.choices[0].delta
            finish_reason = chunk.choices[0].finish_reason or finish_reason

            if hasattr(chunk, "usage") and chunk.usage:
                usage_data = chunk.usage

            if delta.content:
                full_content += delta.content

                if not content_started:
                    spinner.stop()
                    content_started = True
                    print()

                text = delta.content

                if cfg.render_markdown:
                    while '\n' in text:
                        before, text = text.split('\n', 1)
                        line_buffer += before
                        sys.stdout.write('\r\033[K')
                        sys.stdout.write(_render_line(line_buffer, in_code_block))
                        sys.stdout.write('\n')
                        sys.stdout.flush()
                        if line_buffer.startswith('```'):
                            in_code_block = not in_code_block
                        line_buffer = ""

                    if text:
                        line_buffer += text
                        if len(line_buffer) < term_cols:
                            sys.stdout.write(text)
                            sys.stdout.flush()
                else:
                    sys.stdout.write(text)
                    sys.stdout.flush()

            if delta.tool_calls:
                spinner.stop()
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in tool_calls_raw:
                        tool_calls_raw[idx] = {
                            "id":        tc_delta.id or "",
                            "name":      tc_delta.function.name or "",
                            "arguments": "",
                        }
                    if tc_delta.id:
                        tool_calls_raw[idx]["id"] = tc_delta.id
                    if tc_delta.function:
                        if tc_delta.function.name:
                            tool_calls_raw[idx]["name"] = tc_delta.function.name
                        if tc_delta.function.arguments:
                            tool_calls_raw[idx]["arguments"] += tc_delta.function.arguments

        spinner.stop()

        if cfg.render_markdown and line_buffer:
            sys.stdout.write('\r\033[K')
            sys.stdout.write(_render_line(line_buffer, in_code_block))
            sys.stdout.write('\n')
            sys.stdout.flush()
        elif not cfg.render_markdown and full_content:
            print()

        if cfg.show_timings:
            elapsed = time.time() - t0
            if usage_data:
                print(f"  \033[2m[{usage_data.completion_tokens} tok · {elapsed:.1f}s · {usage_data.completion_tokens/elapsed:.0f} t/s]\033[0m")
            else:
                print(f"  \033[2m[{elapsed:.1f}s]\033[0m")

        return _make_completion(full_content, tool_calls_raw, finish_reason, usage_data)

    def _execute_tool(self, tc) -> str:
        name = tc.function.name
        try:
            args = json.loads(tc.function.arguments or "{}")
        except json.JSONDecodeError as e:
            return f"[Invalid tool arguments JSON: {e}]"

        fn = TOOL_FUNCTIONS.get(name)
        if fn is None:
            return f"[Unknown tool: {name}]"

        if cfg.show_tool_calls:
            args_preview = "  ".join(f"\033[2m{k}=\033[0m\033[33m{repr(v)[:60]}{'…' if len(repr(v)) > 60 else ''}\033[0m" for k, v in args.items())
            print(f"\n  \033[36m▶ {name}\033[0m  {args_preview}")

        try:
            with Spinner(f"{name}"):
                result = fn(**args)
        except TypeError as e:
            result = f"[Tool call error — bad arguments: {e}]"
        except Exception as e:
            result = f"[Tool execution error: {e}]"

        if cfg.show_tool_calls:
            preview = str(result)[:120].replace("\n", " ")
            print(f"  \033[2m◀ {preview}{'…' if len(str(result)) > 120 else ''}\033[0m\n")

        return str(result)


# ── Helpers ───────────────────────────────────────────────────────────────────

_DEFAULT_CONTEXT_WINDOW = 32768


def _detect_context_window(base_url: str, model: str, yaml_value: int | None) -> int:
    """
    Try to detect the actual context window from the server.
    Priority: LM Studio /api/v0 → llama.cpp /slots → YAML → conservative default.
    """
    import urllib.request
    import urllib.error

    origin = base_url.rstrip("/").rsplit("/v1", 1)[0]

    # 1. LM Studio: /api/v0/models has loaded_context_length
    try:
        req = urllib.request.Request(f"{origin}/api/v0/models", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read())
            for m in data.get("data", []):
                if m.get("id") == model or m.get("state") == "loaded":
                    ctx = m.get("loaded_context_length") or m.get("max_context_length")
                    if ctx:
                        return int(ctx)
    except Exception:
        pass

    # 2. llama.cpp: /slots returns n_ctx per slot
    try:
        req = urllib.request.Request(f"{origin}/slots", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            slots = json.loads(resp.read())
            if isinstance(slots, list) and slots:
                ctx = slots[0].get("n_ctx")
                if ctx:
                    return int(ctx)
    except Exception:
        pass

    # 3. Fall back to YAML, then default
    if yaml_value:
        return yaml_value

    print(f"  \033[33m⚠ Could not detect context window — using {_DEFAULT_CONTEXT_WINDOW:,}\033[0m")
    return _DEFAULT_CONTEXT_WINDOW


def _new_session_id() -> str:
    import datetime
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")


def _make_completion(content: str, tool_calls_raw: dict, finish_reason: str, usage=None):
    """Build a minimal ChatCompletion-shaped object from streamed parts."""
    from types import SimpleNamespace

    tool_calls = []
    for idx in sorted(tool_calls_raw):
        tc = tool_calls_raw[idx]
        tool_calls.append(SimpleNamespace(
            id=tc["id"],
            type="function",
            function=SimpleNamespace(name=tc["name"], arguments=tc["arguments"]),
        ))

    message = SimpleNamespace(
        content=content or None,
        tool_calls=tool_calls or None,
        role="assistant",
    )
    choice = SimpleNamespace(message=message, finish_reason=finish_reason)
    return SimpleNamespace(choices=[choice], usage=usage)
