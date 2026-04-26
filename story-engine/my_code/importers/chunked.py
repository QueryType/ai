"""ChunkedAnalyser — multi-pass story analyser for long prose.

NOT YET IMPLEMENTED. Raises NotImplementedError with a user-friendly message.

─────────────────────────────────────────────────────────────────
DESIGN SPEC (for future implementation)
─────────────────────────────────────────────────────────────────

Entry condition:
    word_count(story_text) > STORY_IMPORTER_MAX_WORDS

High-level pipeline:

    Pass 1 — Chunked extraction
        Split the story into overlapping chunks (~1500 words, ~200-word overlap).
        For each chunk, make one LLM call to extract a partial JSON:
            {
              "characters_sighted": [{"name": "...", "role_hint": "...", "description_fragment": "..."}],
              "events": [{"summary": "...", "characters_involved": [...], "position_hint": "early|mid|late"}],
              "settings": [{"location": "...", "time": "...", "atmosphere_fragment": "..."}],
              "style_notes": "..."
            }
        Chunks may be processed sequentially or in parallel
        (gate behind STORY_IMPORTER_PARALLEL_CHUNKS env var).

    Pass 2 — Merge
        Deduplicate characters by name and known aliases.
        Resolve pronoun chains across chunk boundaries (best-effort heuristic:
            the most recently introduced named character owns the pronoun).
        Union world-building/setting details; deduplicate by semantic similarity.
        Sort events chronologically by position_hint, preserving chunk order
            within each tier (early → mid → late).

    Pass 3 — Synthesis
        One final LLM call receives the merged extraction (characters, events, world)
        and produces the full scene JSON in the same schema as SinglePassAnalyser.
        The imagination parameter applies here using the same three-tier clause.
        The beat_count target is enforced in the synthesis prompt.

    Pass 4 — Beat mapping (handled inside synthesis prompt)
        N beats are distributed proportionally across the ordered event list.
        Early events → early beats; late events → late beats.
        The synthesis prompt receives the event list in order and is instructed
        to map them to the requested beat count.

Configuration env vars to add when implementing:
    STORY_IMPORTER_CHUNK_WORDS     — target words per chunk (default: 1500)
    STORY_IMPORTER_CHUNK_OVERLAP   — overlap between adjacent chunks in words (default: 200)
    STORY_IMPORTER_PARALLEL_CHUNKS — "true" to extract chunks concurrently (default: false)

Known edge cases to handle:
    - A character introduced late in the story may appear as a pronoun only in
      earlier chunks if the author uses a flashback structure.
    - Very short chunks (< 500 words) may not give the LLM enough context for
      meaningful extraction — enforce a minimum chunk size.
    - Synthesis LLM call may be large if many chunks produced many events; may
      need its own context-size guard.
"""

from __future__ import annotations

from my_code.importers.base import StoryAnalyser, MAX_WORDS


class ChunkedAnalyser(StoryAnalyser):
    """Multi-pass story analyser for prose longer than STORY_IMPORTER_MAX_WORDS.

    NOT YET IMPLEMENTED — see module docstring for the full design spec.
    """

    def analyse(self, story_text: str, imagination: int, beat_count: int) -> dict:
        wc = len(story_text.split())
        raise NotImplementedError(
            f"Story is {wc:,} words — long-story mode is not yet implemented.\n"
            f"  Single-pass limit: {MAX_WORDS:,} words (STORY_IMPORTER_MAX_WORDS).\n"
            f"  Tip: trim the input to a single chapter or scene and re-run."
        )
