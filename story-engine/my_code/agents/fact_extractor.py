"""FactExtractorAgent — extracts atomic entity facts from one beat's prose.

Single-shot, no tools, stateless. Uses the summariser model (port 8081, 9B) —
structured JSON extraction, not prose generation, so the narrator's model
and KV cache are never touched. Design: docs/STORY_MEMORY_SPEC.md (Phase 1).
"""

from __future__ import annotations

import json
import logging

from strands import Agent
from strands.agent.conversation_manager.null_conversation_manager import NullConversationManager

from my_code.models.provider import get_model, system_prompt_suffix

logger = logging.getLogger(__name__)

FACT_EXTRACTOR_SYSTEM_PROMPT = """\
You are a continuity fact extractor for a multi-agent story engine. You read one
beat of story prose and extract atomic facts about entities (characters, objects,
locations) that a later scene — possibly many files later — will need to recall.

## Output Format

Return ONLY a valid JSON array of fact objects, each with these exact keys:

[
  {
    "entity": "Canonical name for the entity, e.g. 'dagger' not 'the rusted dagger in his hand'",
    "relation": "Short snake_case relation, e.g. found_by, description, location, state, owns",
    "value": "The fact itself, concise and concrete",
    "aliases": ["other ways this entity might be referred to later, e.g. 'the blade'"]
  }
]

## Rules

- Extract only concrete, checkable facts: who has/found/lost something, physical
  descriptions, locations, relationships, state changes. Do NOT extract mood,
  prose style, or vague narrative commentary.
- One fact per object. Do not combine multiple facts into one value.
- entity must be a short canonical noun phrase (1-3 words), reused consistently —
  if this entity was likely introduced earlier under a different name, use the
  most specific concrete name mentioned in THIS beat and list other phrasings
  from this beat as aliases.
- aliases: only include phrasings that actually appear in this beat's text, not
  invented synonyms.
- If a beat introduces no durable facts (pure atmosphere, dialogue with no new
  information), return an empty array: []
- Return ONLY the JSON array. No preamble, no commentary, no markdown fences.
"""


def create_fact_extractor() -> Agent:
    return Agent(
        name="FactExtractor",
        system_prompt=system_prompt_suffix(FACT_EXTRACTOR_SYSTEM_PROMPT),
        tools=[],
        model=get_model("summariser"),
        conversation_manager=NullConversationManager(),
    )


def call_fact_extractor(beat_prose: str) -> list[dict]:
    """Extract facts from one beat's prose. Never raises — returns [] and logs
    a FACT EXTRACTOR FALLBACK warning on any failure, so a bad extraction
    never fails the beat that produced it (see orchestrator.py beat loop).
    """
    agent = create_fact_extractor()
    try:
        result = str(agent(beat_prose))
    except Exception as exc:
        logger.warning("FACT EXTRACTOR FALLBACK: %s raised mid-call — skipping extraction", type(exc).__name__)
        return []

    json_start = result.find("[")
    json_end = result.rfind("]") + 1
    if json_start < 0 or json_end <= json_start:
        logger.warning("FACT EXTRACTOR FALLBACK: no JSON array in output — skipping extraction. raw=%r", result[:200])
        return []

    try:
        facts = json.loads(result[json_start:json_end])
    except json.JSONDecodeError:
        logger.warning("FACT EXTRACTOR FALLBACK: JSON parse failed — skipping extraction. raw=%r", result[json_start:json_end][:200])
        return []

    if not isinstance(facts, list):
        logger.warning("FACT EXTRACTOR FALLBACK: parsed JSON is not a list — skipping extraction")
        return []

    valid = [f for f in facts if isinstance(f, dict) and "entity" in f and "relation" in f and "value" in f]
    if len(valid) != len(facts):
        logger.warning("FACT EXTRACTOR: dropped %d malformed fact entries", len(facts) - len(valid))
    return valid
