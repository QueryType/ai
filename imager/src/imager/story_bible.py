"""Map-reduce pass: per-chunk mini-summaries -> one merged StoryBible.

The bible is the single source of truth for character/setting/style
descriptors that every scene prompt injects verbatim, which is how we get
consistency across images without any image-conditioning machinery.
"""

from __future__ import annotations

import sys

from .chunking import Chunk
from .llm import call_llm_json, extract_json_object

CHUNK_SUMMARY_SYSTEM_PROMPT = """You are a careful literary reader building notes \
for an illustrator. You will be given ONE SECTION of a larger story (not the \
whole thing). Read it closely and extract only what is grounded in this \
section's text.

Return ONLY a JSON object, no prose, no markdown fences:
{
  "section_summary": "2-4 sentences: what happens in this section",
  "characters": [
    {"name": "...", "aliases": ["..."], "appearance": "concrete visual description: build, hair, clothing, distinguishing features -- no plot/personality info"}
  ],
  "settings": [
    {"name": "...", "description": "concrete visual description of this place"}
  ],
  "visual_motifs": ["recurring visual element or symbol seen in this section"]
}

If a character or setting recurs from earlier sections, still describe their \
appearance here as you see it in THIS section (the merge step will reconcile \
duplicates). Be concrete and visual, not abstract."""

BIBLE_MERGE_SYSTEM_PROMPT = """You are a continuity editor for an illustrated \
edition of a story. You will be given a list of per-section notes (JSON), each \
produced independently while reading through the story in order. Merge them \
into ONE consistent story bible.

For each character/setting that appears in multiple sections' notes, reconcile \
into a single fixed, concrete visual description that must be used verbatim in \
every illustration of them (physical build, hair, clothing, distinguishing \
features -- resolve any contradictions by picking the most detailed/frequent \
version). Also define ONE global art style descriptor for the whole story.

Return ONLY a JSON object, no prose, no markdown fences:
{
  "synopsis": "3-5 sentence overview of the whole story's arc",
  "tone": "short phrase describing overall mood/tone",
  "characters": [
    {"name": "...", "aliases": ["..."], "fixed_appearance": "one fixed sentence, always used verbatim"}
  ],
  "settings": [
    {"name": "...", "fixed_desc": "one fixed sentence, always used verbatim"}
  ],
  "global_style": {
    "descriptor_suffix": "a short, comma-separated phrase to append to every image prompt, e.g. 'digital painting, warm cinematic lighting, muted earth-tone palette'"
  },
  "negative_defaults": "comma-separated negative-prompt terms appropriate for this story's style, e.g. 'text, watermark, extra limbs, disfigured hands'"
}

For global_style.descriptor_suffix: even for a period-set story, avoid words \
like "etching", "engraving", "lithograph", "woodcut", or "illuminated \
manuscript" -- image models strongly associate these with captioned book \
plates/broadsides and will render garbled pseudo-text/caption blocks into the \
image. Convey the era through medium + palette instead (e.g. "sepia-toned \
oil painting", "vintage photograph, muted daguerreotype tones", "period \
illustration style" without "etching") -- these read as era-appropriate \
without triggering caption hallucinations."""


def summarize_chunk(chunk: Chunk, llm_url: str, model: str, api_key: str = "not-needed") -> dict:
    try:
        return call_llm_json(llm_url, model, CHUNK_SUMMARY_SYSTEM_PROMPT, chunk.text, extract_json_object, api_key=api_key)
    except ValueError as e:
        print(f"WARNING: chunk {chunk.id} bible summary unparseable, skipping (contributes nothing): {e}", file=sys.stderr)
        return {"section_summary": "", "characters": [], "settings": [], "visual_motifs": []}


def merge_bible(chunk_summaries: list[dict], llm_url: str, model: str, api_key: str = "not-needed") -> dict:
    import json
    user_msg = "Per-section notes, in story order:\n\n" + json.dumps(chunk_summaries, indent=2)
    bible = call_llm_json(llm_url, model, BIBLE_MERGE_SYSTEM_PROMPT, user_msg, extract_json_object, api_key=api_key, temperature=0.3)
    bible.setdefault("characters", [])
    bible.setdefault("settings", [])
    bible.setdefault("global_style", {"descriptor_suffix": ""})
    bible.setdefault("negative_defaults", "")
    return bible
