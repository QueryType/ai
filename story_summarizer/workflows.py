"""
Workflow implementations for the Story Summarizer system.
"""

from .agents import (
    character_analyst,
    content_analyst,
    summary_generator,
    reconstruction_generator,
    title_generator
)
from .utils import determine_summarization_strength, get_model_context_limit, estimate_token_count
from .config import llm_model


# ============================================================================
# Helper Functions
# ============================================================================

def _generate_title(text: str) -> str:
    """Generate a title from story or summary text."""
    words = text.split()
    excerpt = ' '.join(words[:800]) if len(words) > 800 else text
    title_response = title_generator(f"Create a concise, engaging title for this story:\n\n{excerpt}")
    title = title_response.message["content"][0]["text"].strip()
    return title.strip('"').strip("'")


def _handle_no_summarization(story: str, word_count: int) -> dict:
    """Handle case where story is already within target length."""
    print("✓ Story is already within target length - preserving original content\n")
    print("📖 Generating title...")
    title = _generate_title(story)
    print("✓ Title generation complete\n")
    
    return {
        'summary': None,
        'title': title,
        'summary_text': story,
        'original_words': word_count,
        'summary_words': word_count,
        'strength_used': 'NONE'
    }


def _run_character_analysis(story: str, use_reconstruction: bool) -> tuple:
    """Run character analysis step."""
    print("📊 Step 1/3: Character Analyst analyzing story...") 

    response = character_analyst(f"""Analyze the characters in this story:
    STORY BEGIN
    {story}
    END STORY 
    Identify all characters, their attributes, relationships.""")
    
    analysis_text = response.message["content"][0]["text"]
    print("✓ Character analysis complete\n")
    
    '''
    print("=" * 70)
    print("📊 CHARACTER ANALYSIS OUTPUT:")
    print("=" * 70)
    print(analysis_text)
    print("=" * 70 + "\n")
    '''
    return response, analysis_text


def _run_content_analysis(story: str, use_reconstruction: bool) -> tuple:
    """Run content and tone analysis step."""
    print("🎨 Step 2/3: Content Analyst analyzing theme and tone...")

    response = content_analyst(f"""Analyze the theme, tone, and narrative style of this story. 
    BEGIN STORY
    {story}
    END STORY
    Provide analysis of themes, tone, plot structure.""")
    
    analysis_text = response.message["content"][0]["text"]
    print("✓ Content analysis complete\n")
    '''
    print("=" * 70)
    print("🎨 CONTENT & TONE ANALYSIS OUTPUT:")
    print("=" * 70)
    print(analysis_text)
    print("=" * 70 + "\n")
    '''
    return response, analysis_text


def _estimate_context_tokens(story: str, char_text: str, content_text: str, use_reconstruction: bool) -> int:
    """Estimate token usage (rough: 1 word ≈ 1.3 tokens)."""
    estimated_tokens = estimate_token_count(char_text + content_text)
    if use_reconstruction:
        print(f"  ℹ️  Estimated context tokens (analyses only): {estimated_tokens}"  )
        return estimated_tokens #int((len(char_text.split()) + len(content_text.split())) * 1.3 + 500)
    return int((len(story.split()) + len(char_text.split()) + len(content_text.split())) * 1.3 + 500)


def _prepare_story_for_context(story: str, estimated_tokens: int, safe_limit: int) -> str:
    """Abbreviate story if it exceeds context limit."""
    if estimated_tokens <= safe_limit:
        return story
    
    print(f"  ⚠️  Context optimization: Using abbreviated story (estimated {estimated_tokens} tokens, limit {safe_limit})")
    words = story.split()
    first_end = int(len(words) * 0.4)
    last_start = int(len(words) * 0.8)
    
    return (
        ' '.join(words[:first_end]) +
        '\n\n[... middle section omitted for context length ...]\n\n' +
        ' '.join(words[last_start:])
    )


def _build_reconstruction_prompt(char_text: str, content_text: str, adjusted_target: int, strength_desc: str, focus_areas: str = None) -> str:
    """Build prompt for reconstruction mode."""

    focus = f"\n\nSPECIAL FOCUS: {focus_areas}" if focus_areas else ""
    
    return f"""Reconstruct a complete story based on these analyses.
            CRITICAL: TARGET WORD COUNT = {adjusted_target} words
            RECONSTRUCTION LEVEL: {strength_desc}
            Your output MUST be close to {adjusted_target} words. Count carefully.

            CHARACTER ANALYSIS:
            {char_text}

            CONTENT & TONE ANALYSIS:
            {content_text}

            Based on these analyses, write a complete narrative story that:
            - Matches the tone, style, and narrative voice described
            - Includes the characters with their traits and relationships
            - Follows the plot structure and themes outlined
            - Maintains consistency with all analytical details{focus}

            Write the story now:"""


def _build_summarization_prompt(story: str, char_text: str, content_text: str, 
                               adjusted_target: int, original_words: int,
                               strength_desc: str, focus_areas: str = None) -> str:
    """Build prompt for summarization mode."""
    focus = f"\n\nSPECIAL FOCUS: {focus_areas}" if focus_areas else ""
    
    return f"""Create an abridged version of this story.
            CRITICAL: TARGET WORD COUNT = {adjusted_target} words
            ORIGINAL LENGTH: {original_words} words
            STRENGTH LEVEL: {strength_desc}
            
            IMPORTANT: Your output MUST be close to {adjusted_target} words. Count carefully and DO NOT over-compress or under-compress.

            ORIGINAL STORY:
            {story}

            CHARACTER ANALYSIS:
            {char_text}

            CONTENT & TONE ANALYSIS:
            {content_text}

            Create a condensed narrative that maintains the original tone and voice, preserves character dynamics, and keeps thematic elements intact.{focus}

            Write the abridged story now:"""


# ============================================================================
# Main Workflow
# ============================================================================

def summarize_story(story: str, max_words: int = 3000, focus_areas: str = None, 
                   model_context_limit: int = None, use_reconstruction: bool = True):
    """
    Sequential workflow for story summarization with adaptive strength.
    
    Args:
        story: The full story text to summarize
        max_words: Maximum word count for the summary (default: 3000)
        focus_areas: Optional specific areas to emphasize
        model_context_limit: Model's context window size (default: auto-detect)
        use_reconstruction: True = reconstruct from analyses only, False = summarize with original (default: True)
        
    Returns:
        dict: Contains 'summary', 'title', 'summary_text', 'original_words', 'summary_words', 'strength_used'
    """
    # Initialize
    if model_context_limit is None:
        model_context_limit = get_model_context_limit()

    original_word_count = len(story.split())
    strength_name, strength_description, adjusted_target = determine_summarization_strength(
        original_word_count, max_words
    )
    
    # Print workflow info
    workflow_type = "Story Reconstruction" if use_reconstruction else "Story Summarization"
    print(f"🎭 Starting {workflow_type} Workflow...\n")
    if use_reconstruction:
        print("📋 Method: Reconstruct from analyses only (original story NOT provided to generator)\n")
    print(f"📊 Original story: {original_word_count} words")
    print(f"🎯 Target: {max_words} words")
    print(f"⚡ Summarization strength: {strength_name}")
    print(f"📝 Adjusted target: {adjusted_target} words\n")
    
    # Handle case where no summarization is needed
    if strength_name == "NONE":
        return _handle_no_summarization(story, original_word_count)
    
    # Step 1 & 2: Run analyses
    character_analysis, char_analysis_text = _run_character_analysis(story, use_reconstruction)
    content_analysis, content_analysis_text = _run_content_analysis(story, use_reconstruction)
    
    # Step 3: Generate summary or reconstruction
    generator_agent = reconstruction_generator if use_reconstruction else summary_generator
    generator_label = "Reconstruction Generator" if use_reconstruction else "Summary Generator"
    action_label = "creating story from analyses" if use_reconstruction else "creating abridged version"
    
    print(f"✍️  Step 3/3: {generator_label} {action_label}...")
    
    # Estimate context and prepare story
    estimated_tokens = _estimate_context_tokens(story, char_analysis_text, content_analysis_text, use_reconstruction)
    safe_limit = int(model_context_limit * 0.85)
    
    story_for_prompt = story
    if not use_reconstruction and estimated_tokens > safe_limit:
        story_for_prompt = _prepare_story_for_context(story, estimated_tokens, safe_limit)
    
    # Build appropriate prompt
    if use_reconstruction:
        prompt = _build_reconstruction_prompt(
            char_analysis_text, content_analysis_text, adjusted_target, 
            strength_description, focus_areas
        )
    else:
        prompt = _build_summarization_prompt(
            story_for_prompt, char_analysis_text, content_analysis_text,
            adjusted_target, original_word_count, strength_description, focus_areas
        )
    try:
        final_summary = generator_agent(prompt)
        completion_label = "Story reconstruction" if use_reconstruction else "Summary generation"
        print(f"✓ {completion_label} complete\n")
    except Exception as e:
        print(f"❌ Error during {generator_label.lower()}: {e}")
        raise e

    # Step 4: Generate title
    print("📖 Step 4/4: Title Generator creating title...")
    summary_text = final_summary.message["content"][0]["text"]
    title = _generate_title(summary_text)
    print("✓ Title generation complete\n")
    
    summary_word_count = len(summary_text.split())
    
    return {
        'summary': final_summary,
        'title': title,
        'summary_text': summary_text,
        'original_words': original_word_count,
        'summary_words': summary_word_count,
        'strength_used': strength_name
    }


# ============================================================================
# Legacy Workflow (Deprecated - Use summarize_story with use_reconstruction=True)
# ============================================================================

def reconstruct_story_from_analysis(story: str, max_words: int = 3000, focus_areas: str = None, 
                                   model_context_limit: int = None):
    """
    DEPRECATED: Use summarize_story() with use_reconstruction=True instead.
    
    This function is maintained for backwards compatibility.
    """
    return summarize_story(
        story=story,
        max_words=max_words,
        focus_areas=focus_areas,
        model_context_limit=model_context_limit,
        use_reconstruction=True
    )
