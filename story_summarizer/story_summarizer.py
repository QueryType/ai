"""
Story Summarizer: A multi-agent workflow for intelligent story summarization.

This module implements a 3-agent workflow system following the Strands workflow pattern:
1. Character Analyst Agent - Extracts characters, attributes, and relationships
2. Content & Tone Analyst Agent - Analyzes theme, tone, and narrative style
3. Summary Generator Agent - Creates abridged version maintaining original style

Each agent's output is passed directly to the next agent as input.
"""

from strands import Agent
from strands.models.openai import OpenAIModel
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure the OpenAI model hosted on a local server
llm_model = OpenAIModel(
    client_args={
        "base_url": os.getenv("OPENAI_BASE_URL", "http://localhost:7890/v1"),
        "api_key": os.getenv("OPENAI_API_KEY", "not-needed"),
    },
    # **model_config
    model_id=os.getenv("MODEL_ID", "mistralai/magistral-small-2509"),
    params={
        "max_tokens": int(os.getenv("MAX_TOKENS", "10240")),
        "temperature": float(os.getenv("TEMPERATURE", "0.7")),
    }
)

# Create specialized agents for the workflow
# Agent 1: Character Analyst
character_analyst = Agent(
    model=llm_model,
    system_prompt="""You are a Character Analyst specialist. Analyze stories to extract:
- All characters (main, secondary, minor)
- Character attributes and traits
- Relationships between characters
- Character development and arcs

Provide a clear, structured analysis focusing on the most significant character elements.""",
    callback_handler=None
)

# Agent 2: Content & Tone Analyst
content_analyst = Agent(
    model=llm_model,
    system_prompt="""You are a Content & Tone Analyst specialist. Analyze stories for:
- Main themes
- Narrative tone and style
- Plot structure and key points
- Literary devices and techniques
- Emotional arc and pacing

Focus on elements that define the story's unique voice and feel.""",
    callback_handler=None
)

# Agent 3: Summary Generator
summary_generator = Agent(
    model=llm_model,
    system_prompt="""You are a Summary Generator specialist. Create abridged versions that:
- Maintain the original tone, style, and narrative voice
- Preserve character dynamics and relationships
- Keep thematic elements intact
- Respect specified word limits
- Read like a condensed version of the original, NOT a description

IMPORTANT: Write the actual abridged story, not "This is a summary of..." 
Maintain the same narrative perspective and voice as the original.""",
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


def summarize_story(story: str, max_words: int = 500, focus_areas: str = None):
    """
    Sequential workflow for story summarization.
    Each agent's output becomes the input for the next agent.
    
    Args:
        story: The full story text to summarize
        max_words: Maximum word count for the summary (default: 500)
        focus_areas: Optional specific areas to emphasize
        
    Returns:
        The final abridged story
    """
    
    print("🎭 Starting Story Summarization Workflow (4 steps)...\n")
    
    # Step 1: Character Analysis
    print("📊 Step 1/3: Character Analyst analyzing story...")
    character_analysis = character_analyst(f"""Analyze the characters in this story:

{story}

Identify all characters, their attributes, relationships, and development.""")
    print("✓ Character analysis complete\n")
    
    # Step 2: Content & Tone Analysis (receives character analysis output)
    print("🎨 Step 2/3: Content Analyst analyzing theme and tone...")
    content_analysis = content_analyst(f"""Analyze the theme, tone, and narrative style of this story.

STORY:
{story}

Provide analysis of themes, tone, plot structure, and literary devices.""")
    print("✓ Content analysis complete\n")
    
    # Step 3: Summary Generation (receives both previous outputs)
    print("✍️  Step 3/3: Summary Generator creating abridged version...")
    focus_instruction = f"\n\nSPECIAL FOCUS: {focus_areas}" if focus_areas else ""
    
    final_summary = summary_generator(f"""Create an abridged version of this story (maximum {max_words} words).

ORIGINAL STORY:
{story}

CHARACTER ANALYSIS:
{character_analysis}

CONTENT & TONE ANALYSIS:
{content_analysis}

Create a condensed narrative that maintains the original tone and voice, preserves character dynamics, and keeps thematic elements intact.{focus_instruction}

Write the abridged story now:""")
    print("✓ Summary generation complete\n")
    
    # Step 4: Generate title
    print("📖 Step 4/4: Title Generator creating title...")
    summary_text = final_summary.message["content"][0]["text"]
    title_response = title_generator(f"Create a concise, engaging title for this story summary:\n\n{summary_text}")
    title = title_response.message["content"][0]["text"].strip()
    # Remove quotes if present
    title = title.strip('"').strip("'")
    print("✓ Title generation complete\n")
    
    return {
        'summary': final_summary,
        'title': title,
        'summary_text': summary_text
    }


def main():
    """Example usage of the story summarizer workflow."""
    
    # Sample story for testing
    sample_story = """
    The old lighthouse keeper, Marcus, had lived alone on the rocky shore for thirty years. 
    His only companion was a stray cat named Whiskers who appeared one stormy night and never left. 
    Marcus was a gruff man, scarred by a tragedy in his youth that drove him to seek solitude.
    
    One autumn morning, a young artist named Elena arrived, seeking inspiration for her paintings. 
    She was running from her own demons—a failed marriage and a crisis of creative identity. 
    Despite Marcus's initial coldness, Elena persisted, returning day after day with her easel.
    
    Gradually, Marcus found himself opening up. He showed her the secret cove where seals basked, 
    the cliff where eagles nested. Elena's paintings captured not just the landscape but the soul 
    of this lonely place. In turn, she helped Marcus see beauty where he had seen only isolation.
    
    When winter storms threatened to destroy the old lighthouse, it was Elena who rallied the 
    town to save it. Marcus, for the first time in decades, felt part of a community again. 
    And Elena discovered that sometimes you have to lose yourself to find what you're really 
    searching for.
    
    As spring arrived, Elena prepared to leave, but both knew they had saved each other. 
    The lighthouse still stood, now a symbol not of isolation but of connection, watched over 
    by an old keeper who had learned to hope again, and visited by an artist who had found 
    her voice.
    """
    
    print("=" * 70)
    print("Story Summarizer - Sequential Workflow Example")
    print("=" * 70 + "\n")
    
    # Run the workflow
    result = summarize_story(
        story=sample_story,
        max_words=150,
        focus_areas="the transformation of both characters and their healing journey"
    )
    
    print("\n" + "=" * 70)
    print("WORKFLOW COMPLETE")
    print("=" * 70)
    
    print(f"\n📖 Title: {result['title']}")
    print(f"\n📝 Abridged Story:\n")
    print(result['summary_text'])
    
    # Calculate metrics
    original_words = len(sample_story.split())
    summary_words = len(result['summary_text'].split())
    compression = (1 - summary_words / original_words) * 100
    
    print(f"\n📈 Metrics:")
    print(f"   Original: {original_words} words")
    print(f"   Summary: {summary_words} words")
    print(f"   Compression: {compression:.1f}% reduction")


if __name__ == "__main__":
    main()
