#!/usr/bin/env python3
"""
Smoke test for context management — no llama-server needed.
Simulates multi-turn conversations with fake LLM responses and tool results,
then verifies aging, compaction, pinning, mid-turn protection, and the meter.

Run:  python test_context.py
"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent))

from context.tokens import estimate_tokens, calibrate, context_usage, _chars_per_token
from context.memory import (
    age_tool_outputs, increment_seen, strip_internal_fields,
    needs_compaction, compact, _last_user_index,
)
from config import cfg

# ── Helpers ──────────────────────────────────────────────────────────────────

PASS = "\033[32m✓\033[0m"
FAIL = "\033[1;31m✗\033[0m"
failures = 0


def check(label: str, condition: bool, detail: str = ""):
    global failures
    if condition:
        print(f"  {PASS} {label}")
    else:
        failures += 1
        msg = f"  {FAIL} {label}"
        if detail:
            msg += f"  — {detail}"
        print(msg)


def make_messages(n_tool_results: int = 5, tool_size: int = 2000) -> list[dict]:
    """Build a realistic message list with system, project context, user/assistant/tool turns."""
    msgs = [
        {"role": "system", "content": "You are a coding assistant." * 20},
        {"role": "user", "content": "[Project context — read-only, for orientation]\nProject: /tmp/test\n├── main.py\n├── utils.py\n└── config.yaml"},
        {"role": "assistant", "content": "Noted. Ready."},
    ]
    for i in range(n_tool_results):
        msgs.append({"role": "user", "content": f"Do task {i}"})
        msgs.append({
            "role": "assistant", "content": f"I'll read file_{i}.py",
            "tool_calls": [{"id": f"tc_{i}", "type": "function", "function": {"name": "read_file", "arguments": f'{{"path": "file_{i}.py"}}'}}],
        })
        msgs.append({
            "role": "tool", "tool_call_id": f"tc_{i}",
            "content": f"{'x' * tool_size}  # file_{i}.py content line {i}\nerror on last line {i}",
        })
        msgs.append({"role": "assistant", "content": f"File {i} looks fine."})
    return msgs


class _FakeCompletions:
    def create(self, **kwargs):
        content = kwargs["messages"][0]["content"]
        return SimpleNamespace(
            choices=[SimpleNamespace(
                message=SimpleNamespace(content=f"Summary: processed {content[:50]}...", role="assistant")
            )],
            usage=SimpleNamespace(prompt_tokens=len(content) // 4),
        )


class FakeClient:
    """Mock OpenAI client that returns a canned summary."""
    def __init__(self):
        self.chat = SimpleNamespace(completions=_FakeCompletions())


# ── Tests ────────────────────────────────────────────────────────────────────

def test_token_estimator():
    print("\n── Token estimator ──")
    msgs = [{"role": "user", "content": "hello world"}]
    est = estimate_tokens(msgs)
    check("estimate_tokens returns positive int", est > 0, f"got {est}")

    usage = context_usage(msgs, 65536)
    check("context_usage returns small fraction for tiny input", 0 < usage < 0.01, f"got {usage:.4f}")

    # Calibration shifts the ratio
    import context.tokens as tok
    old_ratio = tok._chars_per_token
    big_msgs = [{"role": "user", "content": "a" * 10000}]
    calibrate(big_msgs, 5000)  # implies 2.0 chars/token
    check("calibrate shifts _chars_per_token", tok._chars_per_token != old_ratio,
          f"old={old_ratio:.2f} new={tok._chars_per_token:.2f}")
    # Reset for other tests
    tok._chars_per_token = 3.8


def test_tool_aging():
    print("\n── Tool output aging ──")
    msgs = make_messages(n_tool_results=3, tool_size=2000)
    original_sizes = [len(m["content"]) for m in msgs if m["role"] == "tool"]

    # First pass: increment seen, then age
    increment_seen(msgs)
    age_tool_outputs(msgs)

    # Add a new user message so all prior tool results are "completed turns"
    msgs.append({"role": "user", "content": "next task"})

    # Second pass — now aging should trim (seen >= 1, content > 800)
    increment_seen(msgs)
    age_tool_outputs(msgs)

    aged_sizes = [len(m["content"]) for m in msgs if m["role"] == "tool"]
    check("stage 1: tool outputs shrunk", all(a < o for a, o in zip(aged_sizes, original_sizes)),
          f"original={original_sizes} aged={aged_sizes}")
    check("stage 1: aged marker present",
          any("[... aged from" in m["content"] for m in msgs if m["role"] == "tool"))

    # More passes to reach stage 2 (seen >= 3)
    for _ in range(3):
        increment_seen(msgs)
        age_tool_outputs(msgs)

    stage2 = [m["content"] for m in msgs if m["role"] == "tool"]
    check("stage 2: collapsed to one-line stubs",
          all(c.startswith("[tool:") for c in stage2),
          f"first content: {stage2[0][:60]}")


def test_strip_internal_fields():
    print("\n── Strip internal fields ──")
    msgs = [
        {"role": "tool", "content": "result", "_seen": 3},
        {"role": "user", "content": "hello"},
    ]
    stripped = strip_internal_fields(msgs)
    check("_seen removed from stripped output", "_seen" not in stripped[0])
    check("original still has _seen", "_seen" in msgs[0])
    check("non-tool messages pass through", stripped[1] is msgs[1])


def test_needs_compaction():
    print("\n── Needs compaction ──")
    small = [{"role": "system", "content": "hi"}]
    check("tiny conversation: no compaction", not needs_compaction(small, 65536, turn_count=5))

    # Use a small context window so our test data actually fills it
    big = make_messages(n_tool_results=10, tool_size=3000)
    check("large conversation: triggers compaction", needs_compaction(big, 8000, turn_count=5))

    check("turn_count < 3: never compacts", not needs_compaction(big, 8000, turn_count=2))


def test_compact_budget_aware():
    print("\n── Budget-aware compaction ──")
    msgs = make_messages(n_tool_results=10, tool_size=3000)
    original_count = len(msgs)
    original_chars = sum(len(json.dumps(m)) for m in msgs)

    compacted = compact(msgs, FakeClient(), context_window=8000)
    compacted_chars = sum(len(json.dumps(m)) for m in compacted)

    check("compacted is smaller", len(compacted) < original_count,
          f"original={original_count} compacted={len(compacted)}")
    check("compacted chars reduced", compacted_chars < original_chars,
          f"original={original_chars:,} compacted={compacted_chars:,}")
    check("system prompt preserved", compacted[0]["role"] == "system")
    check("summary message present",
          any("[Context summary" in m.get("content", "") for m in compacted))

    non_system_non_summary = [
        m for m in compacted
        if m["role"] != "system"
        and not m.get("content", "").startswith("[Context summary")
        and not m.get("content", "").startswith("[Project context")
    ]
    check("at least 4 messages kept", len(non_system_non_summary) >= 4,
          f"got {len(non_system_non_summary)}")


def test_project_context_pinned():
    print("\n── Project context pinning ──")
    msgs = make_messages(n_tool_results=10, tool_size=3000)
    compacted = compact(msgs, FakeClient(), context_window=8000)

    pinned = [m for m in compacted if m.get("content", "").startswith("[Project context")]
    check("project context survives compaction", len(pinned) == 1)

    if pinned:
        idx = compacted.index(pinned[0])
        check("project context is right after system prompt", idx == 1,
              f"found at index {idx}")


def test_progressive_resummarization():
    print("\n── Progressive re-summarization ──")
    msgs = make_messages(n_tool_results=10, tool_size=3000)

    # First compaction with small window to force it
    compacted1 = compact(msgs, FakeClient(), context_window=8000)

    # Add more turns to the compacted history
    for i in range(10, 20):
        compacted1.append({"role": "user", "content": f"Do task {i}"})
        compacted1.append({
            "role": "assistant", "content": f"Reading file_{i}",
            "tool_calls": [{"id": f"tc_{i}", "type": "function", "function": {"name": "read_file", "arguments": "{}"}}],
        })
        compacted1.append({"role": "tool", "tool_call_id": f"tc_{i}", "content": "x" * 3000})
        compacted1.append({"role": "assistant", "content": f"Done with {i}."})

    # Second compaction — should fold old summary into new one
    compacted2 = compact(compacted1, FakeClient(), context_window=8000)

    summaries = [m for m in compacted2 if m.get("content", "").startswith("[Context summary")]
    check("only one summary after re-compaction", len(summaries) == 1,
          f"found {len(summaries)} summaries")


def test_extract_for_summary():
    print("\n── Extract for summary ──")
    from context.memory import _extract_for_summary

    tool_msg = {"role": "tool", "content": "A" * 1000}
    extracted = _extract_for_summary(tool_msg)
    check("large tool output: head + tail", len(extracted) < 700 and "[...]" in extracted,
          f"len={len(extracted)}")

    small_tool = {"role": "tool", "content": "short result"}
    check("small tool output: kept in full", _extract_for_summary(small_tool) == "short result")

    assistant_with_tools = {
        "role": "assistant",
        "content": "I'll check the file now",
        "tool_calls": [{"function": {"name": "read_file"}}],
    }
    extracted = _extract_for_summary(assistant_with_tools)
    check("assistant with tools: shows tool names", "read_file" in extracted)

    user_msg = {"role": "user", "content": "B" * 3000}
    check("user message: capped at 2000", len(_extract_for_summary(user_msg)) == 2000)


def test_mid_turn_thresholds():
    print("\n── Mid-turn thresholds ──")
    check("mid_turn_warn < mid_turn_abort",
          cfg.mid_turn_warn < cfg.mid_turn_abort,
          f"warn={cfg.mid_turn_warn} abort={cfg.mid_turn_abort}")
    check("mid_turn_warn is 0.90", cfg.mid_turn_warn == 0.90)
    check("mid_turn_abort is 0.95", cfg.mid_turn_abort == 0.95)

    # Simulate a context at ~92% — should trigger warn
    cw = 65536
    target_tokens = int(cw * 0.92)
    target_chars = int(target_tokens * 3.8)
    big_msgs = [{"role": "user", "content": "x" * target_chars}]
    usage = context_usage(big_msgs, cw)
    check("92% usage detected correctly", 0.88 < usage < 0.96,
          f"got {usage:.2%}")


def test_context_meter_values():
    print("\n── Context meter ──")
    msgs = make_messages(n_tool_results=2, tool_size=500)
    cw = 65536
    usage = context_usage(msgs, cw)
    est = estimate_tokens(msgs)
    check("meter values are reasonable", 0 < usage < 0.5 and est > 0,
          f"usage={usage:.2%} est={est:,}")


# ── Run ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Context management smoke tests\n" + "=" * 40)

    test_token_estimator()
    test_tool_aging()
    test_strip_internal_fields()
    test_needs_compaction()
    test_compact_budget_aware()
    test_project_context_pinned()
    test_progressive_resummarization()
    test_extract_for_summary()
    test_mid_turn_thresholds()
    test_context_meter_values()

    print(f"\n{'=' * 40}")
    if failures:
        print(f"\033[1;31m{failures} test(s) failed\033[0m")
        sys.exit(1)
    else:
        print("\033[32mAll tests passed\033[0m")
