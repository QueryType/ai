"""
context/memory.py — Rolling context compaction & tool output aging
"""

import json
from pathlib import Path
from typing import Any

from config import cfg, PROFILES
from context.tokens import estimate_tokens, context_usage


def _history_chars(messages: list[dict]) -> int:
    return sum(len(json.dumps(m)) for m in messages)


# ── Tool output aging ────────────────────────────────────────────────────────

def _last_user_index(messages: list[dict]) -> int:
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].get("role") == "user":
            return i
    return 0


def age_tool_outputs(messages: list[dict]) -> int:
    """Age old tool outputs. Returns number of tool messages aged this pass."""
    aged = 0
    boundary = _last_user_index(messages)
    for m in messages[:boundary]:
        if m.get("role") != "tool":
            continue
        seen = m.get("_seen", 0)
        content = m.get("content", "")

        if seen >= 3 and not content.startswith("[tool:"):
            first_line = content.split("\n", 1)[0][:80]
            m["content"] = f"[tool: {first_line}]"
            aged += 1
        elif seen >= 1 and len(content) > 800:
            head = content[:200]
            tail = content[-200:]
            m["content"] = f"{head}\n\n[... aged from {len(content)} chars ...]\n\n{tail}"
            aged += 1
    return aged


def increment_seen(messages: list[dict]) -> None:
    for m in messages:
        if m.get("role") == "tool":
            m["_seen"] = m.get("_seen", 0) + 1


def strip_internal_fields(messages: list[dict]) -> list[dict]:
    out = []
    for m in messages:
        if "_seen" in m:
            clean = {k: v for k, v in m.items() if k != "_seen"}
            out.append(clean)
        else:
            out.append(m)
    return out


def needs_compaction(
    messages: list[dict],
    context_window: int = 65536,
    turn_count: int = 0,
) -> bool:
    if turn_count < 3:
        return False
    usage = context_usage(messages, context_window)
    if usage >= cfg.compaction_threshold:
        print(f"\n  [compaction: ~{usage:.0%} of context window]")
        return True
    return False


def compact(messages: list[dict], client, context_window: int = 65536) -> list[dict]:
    if len(messages) < 6:
        return messages

    system = [m for m in messages if m["role"] == "system"]

    # Pin project context — never summarize it
    pinned = []
    rest = []
    for m in messages:
        if m["role"] == "system":
            continue
        content = m.get("content", "")
        if isinstance(content, str) and content.startswith("[Project context"):
            pinned.append(m)
        else:
            rest.append(m)

    # Budget-aware: walk backward, keep messages until 40% of context is used
    keep_budget = int(context_window * 0.4)
    keep_tokens = 0
    keep_boundary = len(rest)
    for i in range(len(rest) - 1, -1, -1):
        msg_tokens = estimate_tokens([rest[i]])
        if keep_tokens + msg_tokens > keep_budget and len(rest) - i >= 4:
            break
        keep_tokens += msg_tokens
        keep_boundary = i
    # Always keep at least the last 4 messages
    keep_boundary = min(keep_boundary, max(0, len(rest) - 4))

    to_summarize = rest[:keep_boundary]
    to_keep = rest[keep_boundary:]

    if not to_summarize:
        return messages

    # Check for previous summary to fold in
    prev_summary = ""
    for m in to_summarize:
        c = m.get("content", "")
        if isinstance(c, str) and c.startswith("[Context summary"):
            prev_summary = c

    summary_parts = []
    if prev_summary:
        summary_parts.append(f"Previous context:\n{prev_summary}\n")
    summary_parts.append(
        "Summarize the following conversation turns concisely. "
        "Focus on: decisions made, code written, files changed, errors resolved, "
        "and key facts. Be specific with file names and code details. "
        "This summary replaces these turns in context.\n"
    )
    for m in to_summarize:
        if isinstance(m.get("content", ""), str) and m["content"].startswith("[Context summary"):
            continue
        summary_parts.append(f"[{m['role'].upper()}]: {_extract_for_summary(m)}")

    summary_prompt = "\n".join(summary_parts)

    try:
        profile = PROFILES[cfg.profile]
        resp = client.chat.completions.create(
            model=profile["model"],
            messages=[{"role": "user", "content": summary_prompt}],
            max_tokens=1200,
            temperature=0.1,
        )
        summary_text = resp.choices[0].message.content
    except Exception as e:
        summary_text = f"[Context compacted — {len(to_summarize)} earlier turns dropped due to error: {e}]"

    summary_message = {
        "role": "user",
        "content": f"[Context summary of earlier conversation]\n{summary_text}",
    }

    compacted = system + pinned + [summary_message] + to_keep
    saved = _history_chars(messages) - _history_chars(compacted)
    print(f"  [compacted — saved ~{saved:,} chars, keeping {len(to_keep)} messages]\n")
    return compacted


def _extract_for_summary(message: dict) -> str:
    role = message.get("role", "")
    content = message.get("content", "")

    if isinstance(content, list):
        parts = [p.get("text", "") for p in content if isinstance(p, dict) and "text" in p]
        content = " ".join(parts)

    content = str(content)

    if role == "tool":
        if len(content) <= 600:
            return content
        return content[:300] + "\n[...]\n" + content[-300:]

    if role == "assistant" and message.get("tool_calls"):
        tool_names = [tc["function"]["name"] for tc in message["tool_calls"]]
        snippet = content[:200] if content else ""
        return f"[calls: {', '.join(tool_names)}] {snippet}"

    return content[:2000]


# ── Session persistence ───────────────────────────────────────────────────────

def save_session(session_id: str, messages: list[dict], metadata: dict = None):
    if not cfg.save_sessions:
        return
    sessions_dir = Path(cfg.sessions_dir).expanduser()
    sessions_dir.mkdir(parents=True, exist_ok=True)
    data = {"session_id": session_id, "metadata": metadata or {}, "messages": messages}
    path = sessions_dir / f"{session_id}.json"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def load_session(session_id: str) -> list[dict]:
    path = Path(cfg.sessions_dir).expanduser() / f"{session_id}.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    return data.get("messages", [])


def list_sessions(with_description: bool = False) -> list[dict] | list[str]:
    d = Path(cfg.sessions_dir).expanduser()
    if not d.exists():
        return []
    if not with_description:
        return sorted(p.stem for p in d.glob("*.json"))
    results = []
    for p in sorted(d.glob("*.json")):
        data = json.loads(p.read_text())
        msgs = data.get("messages", [])
        desc = _session_description(msgs)
        results.append({"id": p.stem, "messages": len(msgs), "description": desc})
    return results


def _session_description(messages: list[dict]) -> str:
    for m in messages:
        if m.get("role") != "user":
            continue
        c = m.get("content", "")
        text = c if isinstance(c, str) else str(c)[:80]
        if text.startswith("[Context") or text.startswith("[Project context"):
            continue
        return text[:80].split("\n")[0]
    return "(no description)"


def clean_sessions(keep_last: int = 0) -> int:
    d = Path(cfg.sessions_dir).expanduser()
    if not d.exists():
        return 0
    files = sorted(d.glob("*.json"))
    to_delete = files if keep_last == 0 else files[:-keep_last] if len(files) > keep_last else []
    for f in to_delete:
        f.unlink()
    return len(to_delete)
