"""
Run batch story summarization with specified parameters.

This script provides a simple way to run batch processing programmatically
without using the interactive prompts.
"""

import os
from batch_summarizer import process_batch


def main():
    """Run batch processing with configured parameters."""

    # Configure your batch processing parameters here
    # Use environment variables or update these paths as needed
    input_folder = os.getenv("INPUT_FOLDER", "./input")
    output_folder = os.getenv("OUTPUT_FOLDER", "./output")
    focus_areas = os.getenv("FOCUS_AREAS", "focus on the theme and summarize in 1500 words, do not add your own interpretation.")
    max_words = int(os.getenv("MAX_WORDS", "1500"))
    
    print("Starting batch story summarization...")
    print(f"Input:  {input_folder}")
    print(f"Output: {output_folder}")
    print(f"Focus:  {focus_areas}")
    print(f"Max words: {max_words}\n")
    
    # Run the batch processor
    process_batch(
        input_folder=input_folder,
        output_folder=output_folder,
        focus_areas=focus_areas,
        max_words=max_words
    )


if __name__ == "__main__":
    main()
