"""TranslatorAgent — translates story prose paragraph by paragraph.

Stateless per invocation. Rolling context (last 2 translated paragraphs)
is injected manually into each prompt to preserve name/tone continuity.

Model: reuses the summariser endpoint (STORY_ENGINE_SUMMARISER_BASE_URL).
"""

from __future__ import annotations

from strands import Agent
from strands.agent.conversation_manager.null_conversation_manager import NullConversationManager

from my_code.models.provider import get_model, system_prompt_suffix

_SYSTEM_PROMPT = """\
You are a professional literary translator. You translate story prose faithfully,
preserving tone, style, character voice, and narrative flow.

## Rules

- Translate only what is given — do not summarise, expand, or skip sentences.
- Preserve paragraph breaks exactly as in the source.
- Keep character names, place names, and invented terms unchanged unless a
  standard transliteration exists in the target language.
- Match the register and mood of the original (formal/informal, tense, POV).
- If prior translated context is provided, use it only to maintain consistency
  of names, tense, and style — do not retranslate it.
- Output ONLY the translated text. No explanations, no commentary, no preamble.
"""


def create_translator(source_lang: str, target_lang: str, hint: str | None = None) -> Agent:
    """Create a fresh TranslatorAgent for one paragraph."""
    lang_directive = (
        f"Source language: {source_lang}.\n"
        f"Target language: {target_lang}.\n"
        f"Your entire response must be in {target_lang}."
    )
    extra = f"\n\n## Additional instructions\n\n{hint}" if hint else ""
    prompt = system_prompt_suffix(f"{_SYSTEM_PROMPT}\n{lang_directive}{extra}")
    return Agent(
        name="Translator",
        system_prompt=prompt,
        tools=[],
        model=get_model("summariser"),
        conversation_manager=NullConversationManager(),
    )
