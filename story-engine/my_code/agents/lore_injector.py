"""LoreInjectorAgent — context budget manager.

Scans beat text for character trigger keywords, retrieves relevant cards,
and builds a compact lore block for narrator injection.

Stateless per beat. See AGENT_DESIGN.md §1.2.
"""

from __future__ import annotations

from strands import Agent
from strands.agent.conversation_manager.null_conversation_manager import NullConversationManager

from my_code.models.provider import get_model, system_prompt_suffix
from my_code.tools.lore_tools import build_lore_block, get_character_card, scan_for_triggers

LORE_INJECTOR_SYSTEM_PROMPT = """\
You are the Lore Injector — a context manager for a story engine.

Your job:
1. Scan the current beat text for character trigger keywords.
2. Retrieve the character cards for any matched characters.
3. Build a compact lore block combining world info + matched character cards.

Always call your tools in this order:
1. scan_for_triggers — to find which characters are relevant to this beat
2. get_character_card — once per matched character name
3. build_lore_block — to assemble the final lore context

Return ONLY the output of build_lore_block. Do not add commentary.
"""


def create_lore_injector() -> Agent:
    """Create a fresh LoreInjectorAgent instance."""
    return Agent(
        name="LoreInjector",
        system_prompt=system_prompt_suffix(LORE_INJECTOR_SYSTEM_PROMPT),
        tools=[scan_for_triggers, get_character_card, build_lore_block],
        model=get_model("lore_injector"),
        conversation_manager=NullConversationManager(),
    )
