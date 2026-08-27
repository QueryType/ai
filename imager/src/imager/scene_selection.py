"""Per-chunk scene-candidate selection against the story bible, then reconciliation
into a final, story-ordered scene list (optionally capped by --num-scenes)."""

from __future__ import annotations

import json
import sys

from .chunking import Chunk
from .llm import call_llm_json, extract_json_array

SCENE_CANDIDATE_SYSTEM_PROMPT = """You are an art director choosing illustration \
points for a story. You have the full story bible (characters, settings, style) \
for context, but you are only looking at ONE SECTION of the story right now. \
Select the moments in THIS SECTION that would make strong standalone \
illustrations: visually distinct, recognizable without surrounding text, and \
important to this section's events. Only choose moments actually present in \
this section's text -- do not invent scenes.

Use your judgment on how many: a short, visually flat section may deserve zero; \
a pivotal, visually rich section may deserve several. Do not cluster multiple \
near-duplicate moments.

Return ONLY a JSON array, no prose, no markdown fences. Each element:
{
  "anchor": "a short (<15 word) quote or paraphrase marking where in the section this scene occurs",
  "description": "what is visually happening in this scene (subject, action, setting, mood) -- do NOT restate character appearance, that will be added separately",
  "characters_present": ["name", "..."],
  "settings_present": ["name", "..."],
  "importance": 1-5,
  "orientation": "portrait" | "landscape" | "square" -- how this scene should be framed as an image: "portrait" for a single-subject close-up/character focus, "landscape" for a wide vista, group, or action shot, "square" as a versatile default when neither clearly applies
}
"""


# Long stories chunk into many more sections than short ones, so an unbounded
# "use your judgment" per chunk compounds into far too many total images. Cap
# per-chunk count tighter for long stories (many chunks) than short ones.
_LONG_STORY_CHUNK_THRESHOLD = 5
_LONG_STORY_MAX_PER_CHUNK = 2
_SHORT_STORY_MAX_PER_CHUNK = 5


def max_scenes_per_chunk(total_chunks: int) -> int:
    return _LONG_STORY_MAX_PER_CHUNK if total_chunks > _LONG_STORY_CHUNK_THRESHOLD else _SHORT_STORY_MAX_PER_CHUNK


def select_scene_candidates(chunk: Chunk, bible: dict, llm_url: str, model: str, max_per_chunk: int, api_key: str = "not-needed") -> list[dict]:
    user_msg = (
        f"Story bible:\n{json.dumps(bible, indent=2)}\n\n"
        f"Select at most {max_per_chunk} illustration point(s) from this section -- fewer is fine, "
        f"and zero is fine for a visually flat section.\n\n"
        f"Section text (section {chunk.index}):\n{chunk.text}"
    )
    try:
        candidates = call_llm_json(llm_url, model, SCENE_CANDIDATE_SYSTEM_PROMPT, user_msg, extract_json_array, api_key=api_key)
    except ValueError as e:
        print(f"WARNING: could not parse scene candidates for chunk {chunk.id} after retries, skipping: {e}", file=sys.stderr)
        return []
    for c in candidates:
        c["chunk_id"] = chunk.id
        c["chunk_index"] = chunk.index

    if len(candidates) > max_per_chunk:
        # hard cap in case the model doesn't follow the instruction above --
        # keep the most important, then restore original (story) order
        keep_ids = {id(c) for c in sorted(candidates, key=lambda c: c.get("importance", 3), reverse=True)[:max_per_chunk]}
        candidates = [c for c in candidates if id(c) in keep_ids]
    return candidates


def reconcile_scenes(all_candidates: list[dict], num_scenes: int | None) -> list[dict]:
    # story order = chunk order, then order within the chunk as the LLM returned them
    ordered = sorted(
        enumerate(all_candidates),
        key=lambda pair: (pair[1]["chunk_index"], pair[0]),
    )
    ordered = [c for _, c in ordered]

    if num_scenes is not None and len(ordered) > num_scenes:
        # trim to target by importance, then restore story order
        by_importance = sorted(ordered, key=lambda c: c.get("importance", 3), reverse=True)
        keep = set(id(c) for c in by_importance[:num_scenes])
        ordered = [c for c in ordered if id(c) in keep]
    # (padding when under target is intentionally not attempted -- inventing scenes
    # not grounded in the text would break the "recognizable without surrounding
    # text" requirement; a lower-than-requested count is reported to the user instead.)

    for i, c in enumerate(ordered, start=1):
        c["id"] = f"{i:03d}"
    return ordered
