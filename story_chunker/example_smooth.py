"""Example usage of Chunk Smoother."""

from smooth_chunks import main

if __name__ == "__main__":
    # Input: the chunked output from story_chunker
    input_file = "output_chunks.txt"
    
    # Output: smoothed version
    output_file = "smoothed_chunks.txt"
    
    print("=" * 60)
    print("Chunk Smoother - Example Usage")
    print("=" * 60)
    print(f"Input: {input_file}")
    print(f"Output: {output_file}")
    print("=" * 60)
    print()
    
    # Run the smoother
    main(input_file, output_file)
