"""
Story Summarizer: A multi-agent workflow for intelligent story summarization.

This is the main entry point. The implementation has been refactored into modules:
- config.py: Model configuration and constants
- agents.py: All agent definitions
- utils.py: Utility functions
- workflows.py: Workflow implementations
"""

from .workflows import summarize_story, reconstruct_story_from_analysis


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
        max_words=3000,
        focus_areas="the transformation of both characters and their healing journey"
    )
    
    print("\n" + "=" * 70)
    print("WORKFLOW COMPLETE")
    print("=" * 70)
    
    print(f"\n📖 Title: {result['title']}")
    print(f"\n📝 Abridged Story:\n")
    print(result['summary_text'])
    
    # Calculate metrics
    original_words = result['original_words']
    summary_words = result['summary_words']
    compression = (1 - summary_words / original_words) * 100 if original_words > 0 else 0
    
    print(f"\n📈 Metrics:")
    print(f"   Original: {original_words} words")
    print(f"   Summary: {summary_words} words")
    print(f"   Compression: {compression:.1f}% reduction")
    print(f"   Strength used: {result['strength_used']}")


if __name__ == "__main__":
    main()

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
        max_words=3000,
        focus_areas="the transformation of both characters and their healing journey"
    )
    
    print("\n" + "=" * 70)
    print("WORKFLOW COMPLETE")
    print("=" * 70)
    
    print(f"\n📖 Title: {result['title']}")
    print(f"\n📝 Abridged Story:\n")
    print(result['summary_text'])
    
    # Calculate metrics
    original_words = result['original_words']
    summary_words = result['summary_words']
    compression = (1 - summary_words / original_words) * 100 if original_words > 0 else 0
    
    print(f"\n📈 Metrics:")
    print(f"   Original: {original_words} words")
    print(f"   Summary: {summary_words} words")
    print(f"   Compression: {compression:.1f}% reduction")
    print(f"   Strength used: {result['strength_used']}")


if __name__ == "__main__":
    main()
