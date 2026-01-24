"""
Agent definitions for the Story Summarizer system.

This module contains all specialized agents:
- Character Analyst
- Content & Tone Analyst
- Summary Generator
- Story Reconstruction Generator
- Title Generator
"""

from strands import Agent
from .config import llm_model


# Agent 1: Character Analyst
character_analyst = Agent(
    name="Character Analyst",
    description="Analyzes stories to extract character details, traits, and relationships.",
    model=llm_model,
    system_prompt="""You are a Character Analyst specialist. Analyze stories to extract:
- All characters (main, secondary, minor)
- Character attributes and traits
- Relationships between characters
Provide a clear description focusing on the most significant character elements.""",
    callback_handler=None
)

# Agent 2: Content & Tone Analyst
content_analyst = Agent(
    name="Content & Tone Analyst",
    description="Analyzes stories for themes, tone, plot structure, and literary techniques.",
    model=llm_model,
    system_prompt="""You are a Content & Tone Analyst specialist. Analyze stories for:
- Main themes
- Narrative tone and style
- Plot structure and key points
- Emotional arc and pacing

Focus on elements that define the story's unique voice and feel.""",
    callback_handler=None
)

# Agent 3: Summary Generator
summary_generator = Agent(
    name="Summary Generator",
    description="Generates abridged versions of stories at specified summarization levels.",
    model=llm_model,
    system_prompt="""You are a Summary Generator specialist. Create abridged versions that:
- Maintain the original tone, style, and narrative voice
- Preserve character dynamics and relationships
- Keep thematic elements intact
- STRICTLY follow the target word count provided
- Read like a condensed version of the original, NOT a description

IMPORTANT: Write the actual abridged story, not "This is a summary of..." 
Maintain the same narrative perspective and voice as the original.

⭐ REWARD: If your output word count is within ±5% of the target, you will receive a perfect score.
❌ PENALTY: If your output deviates more than 10% from the target word count, your response will be considered failed.
📊 Your accuracy will be measured and reported. Aim for precision.

CRITICAL - Follow these summarization levels PRECISELY:

- LIGHT (Target: ~90% of original length, 10% reduction):
  * Keep almost everything - this is MINIMAL editing
  * Only remove truly redundant phrases and minor tangents
  * Preserve most dialogue, descriptions, and scenes
  * Your output should be close to 90% of the original word count
  * Example: 3000 words → 2700 words
  * DO NOT compress heavily - you're just trimming excess

- MEDIUM (Target: ~60% of original length, 40% reduction):
  * This is MODERATE condensation - not aggressive
  * Condense scenes while keeping key moments and important dialogue
  * Combine or shorten less critical scenes
  * Remove subplot details that don't affect main narrative
  * Preserve essential character interactions and development
  * Your output should be around 60% of the original word count
  * Example: 3000 words → 1800 words
  * Balance between preservation and condensation

- HEAVY (Target: specified word count, aggressive reduction):
  * This is AGGRESSIVE condensation to meet strict limits
  * Focus ONLY on core plot points and essential character moments
  * Streamline everything - combine scenes, summarize subplots
  * Keep only critical dialogue and turning points
  * Aggressively condense while preserving story essence
  * Meet the EXACT target word count specified
  * Example: 5000 words → 1500 words target
  * Every word must count - be ruthless but preserve essence

⚠️ PERFORMANCE METRICS: Your word count accuracy is being tracked. Stay within ±5% of target for excellent performance.

YOU MUST stay close to the target word count. Do NOT over-compress for LIGHT/MEDIUM or under-compress for HEAVY.
Failure to meet word count targets will result in your output being rejected.""",
    callback_handler=None
)

# Agent 4: Title Generator
title_generator = Agent(
    model=llm_model,
    system_prompt="""You are a creative title generator. Create concise, engaging titles for story summaries.
The title should capture the essence of the story in 3-8 words.
Output ONLY the title, nothing else. No quotes, no extra text.""",
    callback_handler=None
)

# Agent 5: Story Reconstruction Generator (Analysis-Based)
reconstruction_generator = Agent(
    model=llm_model,
    system_prompt="""You are a Story Reconstruction specialist. Your task is to write a complete story based ONLY on character and content analyses provided to you.

CRITICAL RULES:
- You will NOT receive the original story text
- You must build the narrative using ONLY the character analysis and content/tone analysis
- Write in the narrative style and tone described in the analyses
- Create actual story prose, not a summary or description
- Maintain consistency with character traits, relationships, and development described
- Follow the plot structure and thematic elements from the analyses
- Match the emotional arc and pacing indicated

⭐ REWARD: If your output word count is within ±5% of the target, you will receive a perfect score.
❌ PENALTY: If your output deviates more than 10% from the target word count, your response will be considered failed.
📊 Your accuracy will be measured and reported. Aim for precision.
""",
    callback_handler=None
)
