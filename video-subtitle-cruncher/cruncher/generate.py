"""Phase 3: generate summaries / write-ups / answers from a stored timeline.

Works purely off the job's durable artifacts — nothing re-decodes the video,
so the user can return any time and ask for something different.
"""

import json
import time
from pathlib import Path

from .manifest import Job
from .provider import VisionProvider

# Rough char budget for a single-pass request against a local model.
# Beyond this, chunk-summarize first (map-reduce).
SINGLE_PASS_CHARS = 20_000

STYLE_PROMPTS = {
    "short": (
        "Write a short summary (one tight paragraph, max 120 words) of this video. "
        "Weave together what was SAID and what was SHOWN."
    ),
    "detailed": (
        "Write a detailed write-up of this video in Markdown. Use sections that "
        "follow the video's own structure. For each section, weave together what "
        "was said and what was shown on screen; quote important on-screen text. "
        "When a frame is clearly the visual anchor of a section, reference it "
        "inline as ![frame](frames/FRAME_FILENAME) using the frame filename "
        "from the context."
    ),
    "chapters": (
        "Produce a timestamped chapter list for this video in Markdown: one line "
        "per chapter as `MM:SS — title (one-sentence gist)`. Base chapters on "
        "real content shifts, not fixed intervals."
    ),
}


def _fmt_time(t: float) -> str:
    return f"{int(t) // 60:02d}:{int(t) % 60:02d}"


def build_context(job: Job) -> str:
    """One text document combining the timeline and the full transcript."""
    timeline = json.loads(job.timeline_path.read_text()) \
        if job.timeline_path.exists() else []
    transcript = json.loads(job.transcript_path.read_text()) \
        if job.transcript_path.exists() else {"segments": []}

    lines = ["# VISUAL TIMELINE (deduplicated keyframes)"]
    for e in timeline:
        lines.append(f"\n[{_fmt_time(e['t'])}] frame {e['frame']}\n{e['description']}")
    lines.append("\n\n# TRANSCRIPT")
    if transcript["segments"]:
        for s in transcript["segments"]:
            lines.append(f"[{_fmt_time(s['start'])}-{_fmt_time(s['end'])}] {s['text']}")
    else:
        lines.append("(no transcript available — rely on the visual timeline)")
    return "\n".join(lines)


def _complete(provider: VisionProvider, instruction: str, context: str,
              max_tokens: int = 2000) -> str:
    messages = [{
        "role": "user",
        "content": (f"You are analyzing a video from its extracted context "
                    f"(keyframe descriptions + transcript).\n\n{context}\n\n"
                    f"---\nTASK: {instruction}"),
    }]
    return provider.chat(messages, max_tokens=max_tokens, temperature=0.2)


def _chunk_context(job: Job, provider: VisionProvider) -> str:
    """Map-reduce: condense the context in time-ordered chunks first."""
    full = build_context(job)
    if len(full) <= SINGLE_PASS_CHARS:
        return full
    print(f"  context is {len(full)} chars — condensing in chunks ...")
    chunks = [full[i:i + SINGLE_PASS_CHARS]
              for i in range(0, len(full), SINGLE_PASS_CHARS)]
    condensed = []
    for i, chunk in enumerate(chunks):
        part = _complete(
            provider,
            "Condense this portion of the video context to at most 400 words, "
            "keeping timestamps, key on-screen text, and the flow of what was said.",
            chunk, max_tokens=800)
        condensed.append(f"## part {i + 1}\n{part}")
        print(f"  condensed chunk {i + 1}/{len(chunks)}")
    return "\n\n".join(condensed)


def _save(job: Job, kind: str, text: str) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = job.outputs_dir / f"{kind}-{stamp}.md"
    path.write_text(text)
    return path


def summarize(job: Job, provider: VisionProvider, style: str) -> Path:
    context = _chunk_context(job, provider)
    result = _complete(provider, STYLE_PROMPTS[style], context)
    return _save(job, style, result)


def ask(job: Job, provider: VisionProvider, question: str) -> tuple[str, Path]:
    context = _chunk_context(job, provider)
    instruction = (
        f"Answer this question about the video, citing timestamps where "
        f"relevant. If the context doesn't contain the answer, say so.\n"
        f"QUESTION: {question}")
    result = _complete(provider, instruction, context)
    path = _save(job, "qa", f"**Q: {question}**\n\n{result}")
    return result, path
