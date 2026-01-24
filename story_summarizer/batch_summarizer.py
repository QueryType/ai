"""
Batch Story Summarizer: Process multiple story files from a folder.

This script reads all .txt files from an input folder, processes them using the 
Story Summarizer workflow, and saves the summaries to an output folder with the 
same filenames.

Usage:
    # From the my_code directory:
    cd /path/to/my_code
    python3 -m story_summarizer.batch_summarizer
    
    # Or use run_batch.py for programmatic execution:
    python3 -m story_summarizer.run_batch
"""

import os
import glob
from pathlib import Path

# Import from the package (must be run as module: python3 -m story_summarizer.batch_summarizer)
from story_summarizer import summarize_story


def get_txt_files(input_folder):
    """Get all .txt files from the input folder.
    
    Args:
        input_folder: Path to the folder containing story files
        
    Returns:
        List of file paths
    """
    pattern = os.path.join(input_folder, "*.txt")
    files = glob.glob(pattern)
    return sorted(files)


def process_batch(input_folder, output_folder, focus_areas=None, max_words=3000, model_context_limit=None):
    """Process all .txt files from input folder and save summaries to output folder.
    
    Args:
        input_folder: Path to folder containing story .txt files
        output_folder: Path to folder where summaries will be saved
        focus_areas: Optional focus areas for summarization (applied to all stories)
        max_words: Maximum words for each summary (default: 3000)
        model_context_limit: Model's context window size in tokens (default: auto-detect)
    """
    # Import agents to access them for clearing conversation history
    from story_summarizer.agents import (
        character_analyst,
        content_analyst,
        summary_generator,
        reconstruction_generator,
        title_generator
    )
    
    # Validate input folder
    if not os.path.exists(input_folder):
        print(f"❌ Error: Input folder '{input_folder}' does not exist.")
        return
    
    if not os.path.isdir(input_folder):
        print(f"❌ Error: '{input_folder}' is not a directory.")
        return
    
    # Create output folder if it doesn't exist
    os.makedirs(output_folder, exist_ok=True)
    print(f"✓ Output folder ready: {output_folder}")
    
    # Get all .txt files
    story_files = get_txt_files(input_folder)
    
    if not story_files:
        print(f"⚠️  No .txt files found in '{input_folder}'")
        return
    
    print(f"✓ Found {len(story_files)} story file(s) to process\n")
    
    # Process each file
    successful = 0
    failed = 0
    
    for idx, file_path in enumerate(story_files, 1):
        filename = os.path.basename(file_path)
        output_path = os.path.join(output_folder, filename)
        
        print(f"[{idx}/{len(story_files)}] Processing: {filename}")
        
        # Check if output file already exists
        if os.path.exists(output_path):
            print(f"  ⏭️  Already processed: {output_path}")
            try:
                # Read files to show stats
                with open(file_path, 'r', encoding='utf-8') as f:
                    story = f.read()
                with open(output_path, 'r', encoding='utf-8') as f:
                    output_content = f.read()
                
                # Extract title and summary (skip first line which is title)
                lines = output_content.split('\n', 2)
                title = lines[0] if lines else "Unknown"
                summary_text = lines[2] if len(lines) > 2 else ""
                
                original_word_count = len(story.split())
                summary_word_count = len(summary_text.split())
                compression_ratio = (1 - summary_word_count / original_word_count) * 100 if original_word_count > 0 else 0
                
                print(f"  📖 Title: {title}")
                print(f"  📊 Stats: {original_word_count} words → {summary_word_count} words ({compression_ratio:.1f}% reduction)\n")
                successful += 1
            except Exception as e:
                print(f"  ⚠️  Could not read stats: {e}\n")
            continue
        
        try:
            # Read the story
            with open(file_path, 'r', encoding='utf-8') as f:
                story = f.read()
            
            if not story.strip():
                print(f"  ⚠️  Skipped: File is empty")
                continue
            
            # CRITICAL: Clear conversation history from all agents to prevent context overflow
            # Each agent accumulates messages across batch processing, causing token overflow
            character_analyst.messages.clear()
            content_analyst.messages.clear()
            summary_generator.messages.clear()
            reconstruction_generator.messages.clear()
            title_generator.messages.clear()
            
            # Count original words
            original_word_count = len(story.split())
            
            # Summarize the story (includes title generation)
            print(f"  → Summarizing... (max {max_words} words)")
            result = summarize_story(
                story=story,
                max_words=max_words,
                focus_areas=focus_areas,
                model_context_limit=model_context_limit
            )
            
            # Extract results
            title = result['title']
            summary_text = result['summary_text']
            summary_word_count = result['summary_words']
            original_word_count = result['original_words']
            strength_used = result['strength_used']
            
            # Calculate compression ratio
            compression_ratio = (1 - summary_word_count / original_word_count) * 100 if original_word_count > 0 else 0
            
            # Format output with title, blank line, and summary
            output_content = f"{title}\n\n{summary_text}"
            
            # Save the summary with title
            output_path = os.path.join(output_folder, filename)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(output_content)
            
            # Print statistics
            print(f"  ✓ Saved summary to: {output_path}")
            print(f"  📖 Title: {title}")
            print(f"  📊 Stats: {original_word_count} words → {summary_word_count} words ({compression_ratio:.1f}% reduction)")
            print(f"  ⚡ Strength: {strength_used}\n")
            successful += 1
            
        except Exception as e:
            print(f"  ❌ Error processing {filename}: {e}\n")
            failed += 1
    
    # Print summary
    print("=" * 70)
    print("BATCH PROCESSING COMPLETE")
    print("=" * 70)
    print(f"Total files: {len(story_files)}")
    print(f"Successfully processed: {successful}")
    print(f"Failed: {failed}")
    print(f"Output location: {output_folder}")
    print("=" * 70)


def main():
    """Interactive command-line interface for batch processing."""
    print("\n" + "=" * 70)
    print("STORY SUMMARIZER - BATCH PROCESSOR")
    print("=" * 70 + "\n")
    
    # Get input folder
    input_folder = input("Enter the input folder path (containing .txt story files): ").strip()
    if input_folder.startswith('"') and input_folder.endswith('"'):
        input_folder = input_folder[1:-1]  # Remove quotes if present
    
    # Get output folder
    output_folder = input("Enter the output folder path (where summaries will be saved): ").strip()
    if output_folder.startswith('"') and output_folder.endswith('"'):
        output_folder = output_folder[1:-1]  # Remove quotes if present
    
    # Get focus areas (optional)
    print("\nOptional: Enter focus areas for summarization")
    print("(e.g., 'character development and moral themes')")
    focus_areas = input("Focus areas (press Enter to skip): ").strip()
    if not focus_areas:
        focus_areas = None
    
    # Get max words
    print("\nOptional: Enter maximum words for each summary")
    max_words_input = input("Max words (press Enter for default 3000): ").strip()
    if max_words_input:
        try:
            max_words = int(max_words_input)
        except ValueError:
            print("Invalid number, using default 3000")
            max_words = 3000
    else:
        max_words = 3000
    
    # Get model context limit
    print("\nOptional: Enter model context limit in tokens")
    print("(Leave blank to auto-detect from model)")
    print("Common values: 32768, 128000, 200000")
    context_limit_input = input("Context limit (press Enter for auto-detect): ").strip()
    if context_limit_input:
        try:
            model_context_limit = int(context_limit_input)
        except ValueError:
            print("Invalid number, will auto-detect")
            model_context_limit = None
    else:
        model_context_limit = None
    
    # Confirm and process
    print("\n" + "-" * 70)
    print("CONFIGURATION:")
    print(f"  Input folder:  {input_folder}")
    print(f"  Output folder: {output_folder}")
    print(f"  Focus areas:   {focus_areas if focus_areas else '(none)'}")
    print(f"  Max words:     {max_words}")
    print(f"  Context limit: {model_context_limit if model_context_limit else 'auto-detect'}")
    print("-" * 70 + "\n")
    
    confirm = input("Proceed with batch processing? (y/n): ").strip().lower()
    if confirm != 'y':
        print("Operation cancelled.")
        return
    
    print()
    
    # Process the batch
    try:
        process_batch(
            input_folder=input_folder,
            output_folder=output_folder,
            focus_areas=focus_areas,
            max_words=max_words,
            model_context_limit=model_context_limit
        )
    except Exception as e:
        print(f"\n❌ Batch processing error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
