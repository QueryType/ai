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
- scenario          : 2–4 paragraphs describing the SITUATION BEFORE THE SCENE OPENS — who the characters
                      are, why they are where they are, what each character wants or fears, and what
                      led them to this moment; do NOT describe events from the prose itself; this is
                      read once by the narrator before beat 1 to understand context and motivation
- narrator_prompt   : written as direct instructions to the narrator; must state POV and tense; must
                      name which characters the narrator controls vs does not (e.g. "you control all
                      characters except the player character"); must include at least one prohibition
                      ("never summarise", "do not break character", "do not make decisions for the player");
                      capture any distinctive voice or thematic framing evident in the prose; aim for
                      60–120 words
- writing_style     : the HOW of the prose — sentence rhythm (short/percussive vs long/flowing), dialogue
                      format (quotes? italics?), sensory emphasis (which senses dominate), pacing cues,
                      show-don't-tell rules, and any distinctive stylistic choices visible in the source;
                      aim for 60–120 words
- author_note_content : one persistent thematic reminder, 1–2 sentences max
- world_info        : STRICTLY under 300 words — be comprehensive: include ALL named factions, locations,
                      supernatural/divine rules, social hierarchies, and world-specific lore visible in the
                      source; aim for 100–250 words; injected every beat so keep it dense and specific
- scene_setup       : specific, sensory — location, time of day/season, emotional atmosphere
- characters        : every named or clearly distinct character;
                      triggers are comma-separated keywords used to MATCH MENTIONS OF THIS CHARACTER
                      IN PROSE — include: full name, surname or short name, epithets and titles from the
                      prose (e.g. "the sun's son", "the charioteer's son", "the archer"), pronouns
                      (she/he/they/her/him), and role descriptors — aim for 6–12 triggers per character
                      (e.g. "Lyra, Voss, she, her, the scout, the woman, the deserter") —
                      do NOT include personality traits, objects, or abstract concepts;
                      description must include physical appearance (age, build, clothing, weapons/tools);
                      personality minimum 20 words describing traits and drives;
                      backstory minimum 20 words on history relevant to this scene;
                      speech_style must describe HOW they speak (cadence, habit, tone), not what they say
- beats             : exactly {beat_count} beats; title SHORT ALL-CAPS (e.g. THE DESCENT); instruction is
                      directional — WHAT happens in this beat (who does what, what changes, what is at
                      stake), not HOW to write it; 3–5 sentences, 25–60 words each — do not abbreviate;
                      set pause:true for beats that are natural player-agency moments: first direct contact
                      between characters, any beat where a decision must be made, a confrontation or
                      standoff, a moment of revelation the player must respond to — typically 2–3 beats
                      in a 5-beat scene will have pause:true
- writing_instructions : scene-specific creative direction read once at scene start; be comprehensive —
                      extract ALL creative directives visible in the prose's execution; must include
                      (1) where and how to open the scene, (2) at least one explicit avoidance directive
                      ("avoid X", "don't Y", "never Z"), and (3) any character-specific or beat-specific
                      writing rules; aim for 80–200 words

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
