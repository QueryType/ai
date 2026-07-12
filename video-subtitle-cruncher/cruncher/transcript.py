"""Phase 1b: transcript acquisition.

Preferred source: burned-in captions (CC) read off the sampled frames by the
local vision model. Fallback: local ASR with faster-whisper.
"""

import json
import re
import subprocess
import tempfile
from pathlib import Path

import imagehash
from PIL import Image

from .provider import VisionProvider
from .snapshot import Sample

# Fixed bands per reported caption position — asking the model for exact pixel
# coordinates is far less reliable than a generous fixed crop.
BANDS = {"bottom": (0.72, 1.0), "top": (0.0, 0.28)}
DETECT_PROBES = 5
# dhash distance at/below which two caption crops count as "unchanged"
# (no vision call needed — reuse the previous reading).
CROP_GATE = 3

DETECT_PROMPT = (
    "Look at this video frame. Is there subtitle/caption text rendered on the "
    "video itself (burned-in captions)? Ignore titles, logos, and text that is "
    "part of the scene content (slides, code, signs).\n"
    'Answer with strict JSON only, no other text: '
    '{"captions": true or false, "position": "bottom" or "top" or null}'
)

READ_PROMPT = (
    "This image is the bottom strip of a video frame. Transcribe ONLY the "
    "subtitle/caption overlay — typically short lines of plain text on a "
    "semi-transparent dark box, rendered by the player. "
    "IGNORE all other text: slide content, headings, bullet points, labels, "
    "watermarks, channel logos, UI buttons. "
    "Reply with only the caption text, nothing else. "
    "If there is no caption overlay, reply exactly: NONE"
)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _key(word: str) -> str:
    return re.sub(r"\W+", "", word).lower()


def _common_prefix(a: list[str], b: list[str]) -> int:
    p = 0
    while p < min(len(a), len(b)) and _key(a[p]) == _key(b[p]):
        p += 1
    return p


def _strip_static_prefix(prev_raw: list[str] | None, words: list[str]) -> list[str]:
    """Drop on-screen text (slide lines etc.) misread as part of the caption.

    Rolling captions overlap as prev-suffix == new-prefix; a *stable beginning*
    across consecutive readings while both tails differ is background text,
    not caption — strip it.
    """
    if not prev_raw:
        return words
    p = _common_prefix(prev_raw, words)
    if 3 <= p < min(len(prev_raw), len(words)):
        return words[p:]
    return words


def _word_overlap(prev_words: list[str], new_words: list[str]) -> int:
    """Longest k where the last k words of prev equal the first k of new
    (punctuation/case-insensitive) — how rolling captions overlap."""
    ka = [_key(w) for w in prev_words]
    kb = [_key(w) for w in new_words]
    for k in range(min(len(ka), len(kb)), 0, -1):
        if ka[-k:] == kb[:k]:
            return k
    return 0


# Close a rolling segment once it grows past this many words, so timestamps
# stay useful for alignment instead of one giant segment per speech run.
MAX_SEGMENT_WORDS = 50


def _merge_reading(segments: list[dict], text: str, start: float, end: float) -> None:
    """Fold one caption reading into the segment list.

    Handles static captions (exact repeat -> extend) and rolling captions
    (suffix/prefix overlap -> append only the novel tail).
    """
    words = text.split()
    if segments:
        prev = segments[-1]
        prev_words = prev["text"].split()
        k = _word_overlap(prev_words, words)
        if k == len(words):  # nothing new, caption still on screen
            prev["end"] = end
            return
        if k >= min(3, len(words)):  # rolling continuation
            tail = words[k:]
            if len(prev_words) + len(tail) <= MAX_SEGMENT_WORDS:
                prev["text"] = " ".join(prev_words + tail)
                prev["end"] = end
            else:  # close prev, carry only the novel tail forward
                segments.append({"start": start, "end": end,
                                 "text": " ".join(tail)})
            return
    segments.append({"start": start, "end": end, "text": text})


def detect_caption_band(samples: list[Sample],
                        provider: VisionProvider) -> tuple[float, float] | None:
    """Probe a few frames spread across the video; majority vote on the answer."""
    step = max(1, len(samples) // (DETECT_PROBES + 1))
    probes = samples[step::step][:DETECT_PROBES] or samples[:1]
    votes: dict[str, int] = {}
    for sample in probes:
        answer = provider.ask_image(sample.path, DETECT_PROMPT, max_tokens=64)
        match = re.search(r"\{.*\}", answer, re.DOTALL)
        if not match:
            continue
        try:
            parsed = json.loads(match.group())
        except json.JSONDecodeError:
            continue
        if parsed.get("captions") and parsed.get("position") in BANDS:
            votes[parsed["position"]] = votes.get(parsed["position"], 0) + 1
    if not votes:
        return None
    position = max(votes, key=votes.get)
    if votes[position] < max(2, len(probes) // 2):  # need a real majority
        return None
    return BANDS[position]


def extract_cc(samples: list[Sample], fps: float, band: tuple[float, float],
               provider: VisionProvider) -> list[dict]:
    """Read the caption band on each sample, gated by a crop hash so the model
    is only called when the caption actually changed."""
    segments: list[dict] = []
    prev_hash = None
    prev_text = ""
    prev_raw_words: list[str] | None = None
    calls = 0
    for sample in samples:
        with Image.open(sample.path) as img:
            crop = img.crop((0, int(band[0] * img.height),
                             img.width, int(band[1] * img.height)))
            crop_hash = imagehash.dhash(crop)
            if prev_hash is not None and (crop_hash - prev_hash) <= CROP_GATE:
                text = prev_text
            else:
                raw = provider.ask_image(crop, READ_PROMPT, max_tokens=200)
                calls += 1
                text = "" if _norm(raw).upper() == "NONE" else _norm(raw)
        prev_hash, prev_text = crop_hash, text

        if text:
            raw_words = text.split()
            words = _strip_static_prefix(prev_raw_words, raw_words)
            prev_raw_words = raw_words
            _merge_reading(segments, " ".join(words), sample.t, sample.t + 1 / fps)
        else:
            prev_raw_words = None
    print(f"  cc: {calls} vision calls for {len(samples)} samples, "
          f"{len(segments)} segments")
    return segments


def asr(video: Path, model_size: str = "small") -> list[dict]:
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise RuntimeError(
            "faster-whisper is not installed — pip install "
            "'video-subtitle-cruncher[asr]'") from e

    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "audio.wav"
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(video),
             "-vn", "-ac", "1", "-ar", "16000", str(wav)],
            check=True)
        model = WhisperModel(model_size, device="auto", compute_type="auto")
        raw_segments, _info = model.transcribe(str(wav))
        return [{"start": round(s.start, 2), "end": round(s.end, 2),
                 "text": _norm(s.text)} for s in raw_segments if _norm(s.text)]
