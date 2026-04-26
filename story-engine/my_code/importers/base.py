"""Base abstractions and shared config for story importers."""

from __future__ import annotations

import os
import re
from abc import ABC, abstractmethod

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from openai import OpenAI
except ImportError:
    raise SystemExit("ERROR: openai package not installed.  Run: pip install openai")


# ── Config ─────────────────────────────────────────────────────────────────────
# Fallback chain: STORY_IMPORTER_* → SCENE_BUILDER_* → STORY_ENGINE_*

BASE_URL: str = (
    os.getenv("STORY_IMPORTER_BASE_URL")
    or os.getenv("SCENE_BUILDER_BASE_URL")
    or os.getenv("STORY_ENGINE_LOCAL_BASE_URL", "http://localhost:8080/v1")
)
MODEL: str = (
    os.getenv("STORY_IMPORTER_MODEL")
    or os.getenv("SCENE_BUILDER_MODEL")
    or os.getenv("STORY_ENGINE_EVALUATOR_MODEL")
    or os.getenv("STORY_ENGINE_NARRATOR_MODEL", "default")
)
API_KEY: str = (
    os.getenv("STORY_IMPORTER_API_KEY")
    or os.getenv("SCENE_BUILDER_API_KEY", "none")
)
MAX_WORDS: int = int(os.getenv("STORY_IMPORTER_MAX_WORDS", "6000"))
WARN_WORDS: int = int(os.getenv("STORY_IMPORTER_WARN_WORDS", "4000"))


# ── Helpers ────────────────────────────────────────────────────────────────────

def word_count(text: str) -> int:
    return len(text.split())


def call_llm(messages: list[dict], temperature: float = 0.7) -> str:
    """Call the configured LLM endpoint and return the raw response string."""
    client = OpenAI(base_url=BASE_URL, api_key=API_KEY)
    response = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=temperature,
    )
    raw = response.choices[0].message.content.strip()
    # Strip markdown fences if the model added them
    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw.strip())
    return raw


# ── Abstract base ──────────────────────────────────────────────────────────────

class StoryAnalyser(ABC):
    """Abstract base for story-to-scene extraction strategies.

    Concrete implementations differ in how they handle the source text
    (single LLM call vs. chunked multi-pass), but all produce the same
    output dict consumed by scene_builder.assemble().
    """

    @abstractmethod
    def analyse(self, story_text: str, imagination: int, beat_count: int) -> dict:
        """Extract or generate a full scene JSON dict from prose.

        Args:
            story_text:  Raw prose from the input file.
            imagination: 0–100. Controls invention vs. extraction.
                           0  = strict: only what is explicitly in the text.
                           50 = balanced: extract + infer strongly implied details.
                          100 = free: invent anything not explicitly stated.
            beat_count:  Target number of beats to produce (3–10).

        Returns:
            A dict with all fields required by scene_builder.assemble():
            title, pov, target_length, scenario, narrator_prompt, writing_style,
            author_note_content, world_info, scene_setup (dict), characters (list),
            beats (list), writing_instructions.

        Raises:
            NotImplementedError: If the strategy is not yet implemented.
            json.JSONDecodeError: If the LLM returns malformed JSON.
        """


# ── Factory ────────────────────────────────────────────────────────────────────

def get_analyser(wc: int) -> StoryAnalyser:
    """Return the appropriate StoryAnalyser for the given word count.

    Currently routes anything above MAX_WORDS to ChunkedAnalyser, which
    raises NotImplementedError with a user-friendly message until implemented.
    """
    from my_code.importers.single_pass import SinglePassAnalyser
    from my_code.importers.chunked import ChunkedAnalyser

    if wc <= MAX_WORDS:
        return SinglePassAnalyser()
    return ChunkedAnalyser()
