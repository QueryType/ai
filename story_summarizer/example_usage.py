"""
Example: Using the Story Summarizer with different stories and configurations.

This script demonstrates various ways to use the Story Summarizer workflow system.
"""

import os
from story_summarizer import summarize_story


def example_1_basic_usage():
    """Example 1: Basic story summarization with default settings."""
    print("\n" + "=" * 70)
    print("EXAMPLE 1: Basic Usage")
    print("=" * 70 + "\n")
    
    story = """
    In a small village nestled between mountains, lived twin sisters Maya and Aria. 
    Maya was bold and adventurous, always seeking excitement beyond the village walls. 
    Aria was gentle and thoughtful, finding joy in the simple rhythms of village life.
    
    When a mysterious illness struck their grandmother, the village healer said only 
    a rare moonflower from the peak of Mount Silvermist could cure her. Maya immediately 
    volunteered for the dangerous journey, but Aria insisted on joining her.
    
    The journey tested them both. Maya's courage saved them from a rockslide, but it was 
    Aria's patience that helped them befriend a mountain spirit who showed them the way. 
    At the summit, they found the moonflower together, each realizing they needed the 
    other's strengths.
    
    They returned as true partners, their grandmother healed and their bond deeper than ever. 
    The village celebrated not just their success but what they had learned: that strength 
    comes in many forms, and the greatest power is in unity.
    """
    
    # Run the workflow
    result = summarize_story(story, max_words=100)
    print("Summary:\n")
    print(result['summary_text'])
    print(f"\nTitle: {result['title']}")
    print(f"Original: {result['original_words']} words → Summary: {result['summary_words']} words")


def example_2_with_focus():
    """Example 2: Summary with specific focus areas."""
    print("\n" + "=" * 70)
    print("EXAMPLE 2: Summary with Focus Areas")
    print("=" * 70 + "\n")
    
    story = """
    Detective Sarah Chen had solved hundreds of cases, but this one was personal. 
    Her mentor, Detective James Morrison, had been found dead in his office, a case 
    file open on his desk. The official ruling: suicide. Sarah knew better.
    
    James had been investigating a corruption ring within the police department. His 
    notebook contained cryptic references to "The Cardinal" and a date: October 15th.
    
    Sarah's partner, rookie detective Marcus Webb, urged caution. He was young, idealistic, 
    and trusted the system. But Sarah had learned that sometimes the system itself is broken.
    
    Following James's clues, Sarah discovered that "The Cardinal" was Captain Richard 
    Blackwood, orchestrating evidence tampering for powerful criminals. On October 15th, 
    a major arms deal was scheduled.
    
    Sarah faced an impossible choice: go through official channels and risk the evidence 
    disappearing, or break protocol and take Blackwood down herself. Marcus argued for 
    procedure, but Sarah saw the fear in his eyes—he knew she was right.
    
    In the end, Sarah went rogue. She gathered irrefutable evidence and leaked it to 
    the press simultaneously with the FBI. Blackwood was arrested, but Sarah's career 
    was over. Marcus, learning there's more to justice than rules, joined her in starting 
    a private investigation firm.
    
    James's case was closed, and though Sarah lost her badge, she had honored his legacy: 
    sometimes doing what's right means breaking what's wrong.
    """
    
    # Workflow with specific focus
    result = summarize_story(
        story=story,
        max_words=120,
        focus_areas="Sarah's moral dilemma and her relationship with Marcus"
    )
    
    print("Abridged Story:\n")
    print(result['summary_text'])
    print(f"\nTitle: {result['title']}")
    print(f"Original: {result['original_words']} words → Summary: {result['summary_words']} words")


def example_3_very_short_summary():
    """Example 3: Ultra-brief summary for quick overviews."""
    print("\n" + "=" * 70)
    print("EXAMPLE 3: Ultra-Brief Summary (50 words)")
    print("=" * 70 + "\n")
    
    story = """
    The spaceship Endeavour had been drifting for three months since the reactor failure. 
    Captain Lisa Torres had kept her crew of five alive through rationing and hope, but 
    supplies were running out.
    
    Engineer Pavel Kozlov worked around the clock, trying to restart the reactor with 
    jury-rigged parts. Medical officer Dr. Yuki Tanaka kept everyone physically and mentally 
    stable. Navigator Tom Santos plotted courses to nearby stations, but all were too far.
    
    When a distress signal arrived from a damaged mining vessel, the crew faced a choice: 
    use their remaining fuel to attempt rescue, leaving them stranded, or conserve it for 
    their own slim chance at survival.
    
    Lisa made the call: they would attempt rescue. Pavel got the engines running for one 
    last burst. They found the miners—two survivors—and brought them aboard.
    
    Just when all seemed lost, the mining company dispatched a rescue ship, having tracked 
    their vessel's emergency beacon. The Endeavour's crew had saved two lives and, in doing 
    so, saved themselves.
    
    Back on Earth, Lisa was asked if she regretted risking her crew's lives for strangers. 
    She simply replied, "We're only human if we act like it, even at the edge of the void."
    """
    
    result = summarize_story(story, max_words=50)
    
    print("Ultra-Brief Summary:\n")
    print(result['summary_text'])
    print(f"\nTitle: {result['title']}")
    print(f"Original: {result['original_words']} words → Summary: {result['summary_words']} words")


def example_4_comparing_different_lengths():
    """Example 4: Same story with different summary lengths."""
    print("\n" + "=" * 70)
    print("EXAMPLE 4: Different Summary Lengths")
    print("=" * 70 + "\n")
    
    story = """
    The library had stood for two hundred years, a sanctuary of knowledge in the heart 
    of the city. Its head librarian, Eleanor Hart, had dedicated forty years to preserving 
    its magic. Now, the city council wanted to tear it down for a parking garage.
    
    Young activist Kai Chen organized protests, bringing hundreds to defend the library. 
    But Eleanor knew protests wouldn't be enough. She needed to prove the library's value.
    
    She opened the archives to the public, revealing rare manuscripts and local history 
    collections. She hosted community events, bringing people together. Most importantly, 
    she showed how the library had been a lifeline for countless individuals—including 
    Kai himself, who had spent his childhood there while his mother worked multiple jobs.
    
    The turning point came when Eleanor unearthed documents proving the library sat on 
    historic land protected by a century-old preservation order. The council had to back down.
    
    On the library's 200th anniversary, Eleanor retired, passing the torch to Kai, who 
    had discovered his calling: not just saving one library, but fighting for community 
    spaces everywhere. Eleanor's legacy lived on, not in the building alone, but in the 
    young activist she had inspired.
    """
    
    print("50-word version:")
    result_short = summarize_story(story, max_words=50)
    print(result_short['summary_text'])
    print(f"Title: {result_short['title']} | Words: {result_short['summary_words']}")
    
    print("\n" + "-" * 70 + "\n")
    
    print("100-word version:")
    result_medium = summarize_story(story, max_words=100)
    print(result_medium['summary_text'])
    print(f"Title: {result_medium['title']} | Words: {result_medium['summary_words']}")


def example_5_from_file(file_path=None):
    """Example 5: Load and summarize a story from a txt file."""
    print("\n" + "=" * 70)
    print("EXAMPLE 5: Summarize from File")
    print("=" * 70 + "\n")
    
    # Default file path if none provided
    if file_path is None:
        file_path = "sample_story.txt"
    
    # Check if file exists
    if not os.path.exists(file_path):
        print(f"⏭️  Skipping: File '{file_path}' not found.")
        print(f"   To run this example, create a file at: {file_path}")
        return
    
    # Load the story from file
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            story = f.read().strip()
        
        if not story:
            print(f"⏭️  Skipping: File '{file_path}' is empty.")
            return
        
        print(f"📄 Loaded story from: {file_path}")
        print(f"📊 File size: {len(story)} characters, {len(story.split())} words\n")
        
        # Summarize the story
        result = summarize_story(
            story=story,
            max_words=150,
            focus_areas="main plot and character development"
        )
        
        print("\n" + "-" * 70)
        print("RESULTS:")
        print("-" * 70)
        print(f"\nTitle: {result['title']}")
        print(f"\nSummary ({result['summary_words']} words):\n")
        print(result['summary_text'])
        print(f"\n📊 Compression: {result['original_words']} → {result['summary_words']} words ({result['strength_used']} strength)")
        
    except Exception as e:
        print(f"❌ Error reading or processing file: {e}")


def main():
    """Run all examples."""
    print("\n" + "=" * 70)
    print("STORY SUMMARIZER - USAGE EXAMPLES")
    print("=" * 70)
    
    # Run examples
    try:
        example_1_basic_usage()
        #example_2_with_focus()
        example_3_very_short_summary()
        #example_4_comparing_different_lengths()
        # example_5_from_file()
        
        print("\n" + "=" * 70)
        print("All examples completed successfully!")
        print("=" * 70 + "\n")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
