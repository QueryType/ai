"""
Run batch story summarization with specified parameters.

This script provides a simple way to run batch processing programmatically
without using the interactive prompts.

Usage:
    # From the my_code directory:
    cd /path/to/my_code
    python3 -m story_summarizer.run_batch

    # Or run directly from any location:
    python3 /path/to/story_summarizer/run_batch.py
"""

import sys
from pathlib import Path

# Add parent directory to path if running directly (not as module)
if __name__ == "__main__" and __package__ is None:
    parent_dir = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(parent_dir))

from story_summarizer.batch_summarizer import process_batch


def main():
    """Run batch processing with configured parameters."""
    
    # Configure your batch processing parameters here
    input_folder = "/Users/ninja/Documents/code/ai/strandsagents/strs"
    output_folder = "/Users/ninja/Documents/code/ai/strandsagents/strs/out"
    focus_areas = None
    max_words = 3000
    model_context_limit = None  # None = auto-detect from model
    
    print("Starting batch story summarization...")
    print(f"Input:  {input_folder}")
    print(f"Output: {output_folder}")
    print(f"Focus:  {focus_areas}")
    print(f"Max words: {max_words}")
    print(f"Context limit: {'auto-detect' if model_context_limit is None else f'{model_context_limit} tokens'}\n")
    
    # Run the batch processor
    process_batch(
        input_folder=input_folder,
        output_folder=output_folder,
        focus_areas=focus_areas,
        max_words=max_words,
        model_context_limit=model_context_limit
    )


if __name__ == "__main__":
    main()
