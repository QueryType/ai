"""SinglePassAnalyser — extract scene JSON from prose in one LLM call.

Suitable for stories up to STORY_IMPORTER_MAX_WORDS (default: 6,000 words).
The full story text is passed in a single request with no chunking.
"""

from __future__ import annotations

import json

from my_code.importers.base import StoryAnalyser, call_llm


# ── Imagination-level system prompt clause ─────────────────────────────────────

def _imagination_clause(imagination: int) -> str:
    if imagination <= 20:
        return (
            "EXTRACTION MODE: STRICT\n"
            "Extract only what is explicitly stated in the source text. "
            "For any field where information is absent or unclear, use a minimal honest "
            "placeholder — do not invent. Character names, backstory, and world details "
            "must come from the text. "
            "Beats must map directly to events that occur in the story — do not create "
            "beats for implied or future events. "
            "The writing_style must mirror the source prose's actual style, not reinvent it."
        )
    if imagination <= 79:
        return (
            "EXTRACTION MODE: BALANCED\n"
            "Extract what is explicit and infer what is strongly implied by context. "
            "You may fill reasonable gaps in character backstory, motivation, or world-building "
            "when the text provides enough context for a credible inference. "
            "Beats may reorganise or slightly reframe the story's event structure. "
            "The writing_style should be inspired by the source prose but can be articulated more fully."
        )
    return (
        "EXTRACTION MODE: FREE\n"
        "Extract what is explicit, infer what is implied, and freely invent compelling details "
        "for everything else. You may create names, histories, world-building, and additional beats "
        "that go beyond the source text, as long as they feel tonally consistent with it. "
        "Treat the source as a creative springboard, not a constraint. "
        "The writing_style and narrator_prompt should be fully realised, not merely descriptive."
    )


# ── Prompts ────────────────────────────────────────────────────────────────────

_SYSTEM = """\
You are a story structure analyst. Given a prose story, you extract or generate a complete
Story Engine scene JSON that can be used to re-run or extend the story.

{imagination_clause}

Field rules:
- title             : short, evocative; infer from the story or invent if free mode
- pov               : infer from the narrative voice (third-person / first-person / second-person / third-person-limited)
- target_length     : estimate total desired output words — use 1500 / 3500 / 6000 / 9000
- scenario          : 2–4 paragraphs orienting the narrator to what is active at scene open; read once only
- narrator_prompt   : who the narrator is, tense, POV control rules, what it must/must not do
- writing_style     : sentence rhythm, dialogue format, sensory emphasis — the HOW of the prose
- author_note_content : one persistent thematic reminder, 1–2 sentences max
- world_info        : STRICTLY under 300 words — setting, lore, rules that create pressure; injected every beat
- scene_setup       : specific, sensory — location, time of day/season, emotional atmosphere
- characters        : every named or clearly distinct character; triggers must cover name variants, pronouns, role titles
- beats             : exactly {beat_count} beats; title SHORT ALL-CAPS (e.g. THE DESCENT); instruction is
                      directional — WHAT happens in this beat, not HOW to write it; 2–4 sentences each
- writing_instructions : scene-specific creative direction read once at scene start; where to open, what to avoid

Return ONLY valid JSON. No markdown fences. No explanation outside the JSON."""

_USER = """\
SOURCE STORY:
{story_text}

Return this JSON (all fields required):
{{
  "title": "...",
  "pov": "third-person|first-person|second-person|third-person-limited",
  "target_length": 3500,
  "scenario": "...",
  "narrator_prompt": "...",
  "writing_style": "...",
  "author_note_content": "...",
  "world_info": "...",
  "scene_setup": {{
    "location": "...",
    "time": "...",
    "atmosphere": "..."
  }},
  "characters": [
    {{
      "name": "...",
      "role": "player-character|npc|antagonist|neutral",
      "triggers": "comma, separated, keywords",
      "description": "...",
      "personality": "...",
      "backstory": "...",
      "speech_style": "..."
    }}
  ],
  "beats": [
    {{
      "title": "SHORT ALL-CAPS TITLE",
      "instruction": "2–4 sentences of directional beat guidance",
      "pause": false
    }}
  ],
  "writing_instructions": "..."
}}"""


# ── Analyser ───────────────────────────────────────────────────────────────────

class SinglePassAnalyser(StoryAnalyser):
    """Extract scene JSON from prose in a single LLM call.

    The full story text is sent in one request. The imagination parameter
    controls a system-prompt clause that shifts the LLM between strict
    extraction and free invention for missing details.

    Suitable for stories up to STORY_IMPORTER_MAX_WORDS (default: 6,000 words).
    For longer stories, use ChunkedAnalyser (not yet implemented).
    """

    def analyse(self, story_text: str, imagination: int, beat_count: int) -> dict:
        system = _SYSTEM.format(
            imagination_clause=_imagination_clause(imagination),
            beat_count=beat_count,
        )
        user = _USER.format(story_text=story_text)
        raw = call_llm([
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ])
        return json.loads(raw)
