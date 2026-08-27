"""Optional LLM enhancement of a scene's action/description sentence before
composition in prompt_gen.py.

Deliberately scoped to just the scene description -- NOT the bible's fixed
character/setting descriptors or style suffix, which stay untouched and
verbatim (see prompt_gen.py). Enhancing the whole composed prompt per scene
would let the LLM rephrase "Jeeves, a tall, impeccably groomed valet..."
differently each time it runs, silently breaking the cross-image consistency
the story bible exists to guarantee. Enhancing only the scene-specific
action/mood sentence gets the richer-prompt quality benefit without that risk.
"""

from __future__ import annotations

import sys

from .llm import call_llm

ENHANCE_SYSTEM_PROMPTS = {
    "prose": """You are a cinematic prompt writer for an AI image generator \
that reads natural-language descriptions (not tag lists). You will be given \
one sentence describing what is visually happening in a story scene. \
Rewrite it as a richer single-paragraph description: add cinematic lighting, \
camera framing/composition, and atmosphere/mood detail.

Keep the exact same subject, action, and setting -- do not invent new \
characters, objects, or events, and do not mention any proper names (fixed \
character/setting descriptions are injected separately after your text). \
Output ONLY the rewritten description, nothing else, no preamble.""",
    "tags": """You are a prompt engineer for an SDXL-family image generator \
that reads comma-separated tags. You will be given one sentence describing \
what is visually happening in a story scene. Rewrite it as a concise, \
comma-separated list of descriptive tags/phrases covering the action, \
composition, lighting, and camera framing.

Keep the exact same subject, action, and setting -- do not invent new \
characters, objects, or events, and do not mention any proper names (fixed \
character/setting descriptors are injected separately after your tags). \
Output ONLY the tag list, nothing else, no preamble.""",
}

# Appended when a scene has 2+ named characters, so the enhancer's push toward
# tight/dramatic framing doesn't crop a second character out of the shot --
# observed on real output: single-subject close-ups that lost a named
# character the composed prompt still describes.
_MULTI_SUBJECT_HINT = (
    "\n\nThis scene has multiple named characters in it. Choose a shot "
    "composition that keeps all of them visibly in frame together -- not a "
    "single-subject close-up that crops another character out."
)


def enhance_description(description: str, style: str, llm_url: str, model: str, api_key: str = "not-needed", num_characters: int = 1) -> str:
    system = ENHANCE_SYSTEM_PROMPTS.get(style, ENHANCE_SYSTEM_PROMPTS["prose"])
    if num_characters >= 2:
        system += _MULTI_SUBJECT_HINT
    try:
        enhanced = call_llm(llm_url, model, system, description, api_key=api_key, temperature=0.8).strip()
        return enhanced or description
    except RuntimeError as e:
        print(f"      WARNING: prompt enhancement failed, using original description: {e}", file=sys.stderr)
        return description
