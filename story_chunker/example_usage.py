"""Example usage of Story Chunker."""

from story_chunker import main

# Example 1: Basic usage
if __name__ == "__main__":
    # Path to your story file
    story_path = "path/to/your/story.txt"
    
    # Subjects to extract
    subjects = ["human values"]
    
    # Output file
    output_path = "output_chunks.txt"
    
    print("=" * 60)
    print("Story Chunker - Example Usage")
    print("=" * 60)
    print(f"Story: {story_path}")
    print(f"Subjects: {subjects}")
    print(f"Output: {output_path}")
    print("=" * 60)
    print()
    
    # Run the chunker
    main(story_path, subjects, output_path)
