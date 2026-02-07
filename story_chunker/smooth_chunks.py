"""Chunk Smoother - Converts chunked text into natural paragraphs."""

import re
from openai import OpenAI

from config import LLM_CONFIG


class ChunkSmoother:
    """Smoothens chunked text into natural paragraphs using LLM."""
    
    def __init__(self):
        """Initialize the smoother with LLM client."""
        self.client = OpenAI(
            base_url=LLM_CONFIG["base_url"],
            api_key=LLM_CONFIG["api_key"]
        )
        
        self.system_prompt = """You are a text smoothing assistant. Your task is to take a text chunk and rewrite it into a natural, well-flowing paragraph.

Instructions:
- Fix any truncated sentences at the beginning or end
- Improve readability and flow
- Maintain the original meaning and content
- Keep the same general length
- Return only the smoothed text, no additional commentary"""
    
    def parse_chunks_file(self, input_path: str) -> list:
        """Parse the chunks file and extract chunk data."""
        chunks = []
        
        with open(input_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Split by chunk markers
        chunk_pattern = r'\.{5} chunk(\d+) \[(.*?)\] \.{5}\n(.*?)(?=\n\.{5} chunk|\Z)'
        matches = re.findall(chunk_pattern, content, re.DOTALL)
        
        for chunk_num, subjects, chunk_text in matches:
            chunks.append({
                'num': int(chunk_num),
                'subjects': subjects,
                'text': chunk_text.strip()
            })
        
        return chunks
    
    def group_consecutive_chunks(self, chunks: list, max_group_size: int = 5) -> list:
        """Group consecutive chunks together for better consistency."""
        if not chunks:
            return []
        
        grouped = []
        current_group = [chunks[0]]
        
        for i in range(1, len(chunks)):
            # Check if consecutive and group not full
            if chunks[i]['num'] == current_group[-1]['num'] + 1 and len(current_group) < max_group_size:
                current_group.append(chunks[i])
            else:
                # Save current group and start new one
                grouped.append(current_group)
                current_group = [chunks[i]]
        
        # Add last group
        grouped.append(current_group)
        
        return grouped
    
    def smooth_chunk_group(self, chunks_group: list) -> str:
        """Use LLM to smooth a group of chunks into natural paragraph(s)."""
        # Combine text from all chunks in group
        combined_text = "\n\n".join([chunk['text'] for chunk in chunks_group])
        
        try:
            response = self.client.chat.completions.create(
                model=LLM_CONFIG["model"],
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": combined_text}
                ],
                temperature=LLM_CONFIG["temperature"],
                max_tokens=LLM_CONFIG["max_tokens"] * len(chunks_group)  # Scale tokens by group size
            )
            
            smoothed = response.choices[0].message.content.strip()
            return smoothed
            
        except Exception as e:
            print(f"Error smoothing chunk group: {e}")
            return combined_text  # Return original if error
    
    def process_chunks(self, input_path: str, output_path: str):
        """Process all chunks and create smoothed output."""
        print(f"Reading chunks from: {input_path}")
        chunks = self.parse_chunks_file(input_path)
        print(f"Found {len(chunks)} chunks")
        
        # Group consecutive chunks
        grouped_chunks = self.group_consecutive_chunks(chunks)
        print(f"Grouped into {len(grouped_chunks)} groups for smoothing")
        
        smoothed_groups = []
        
        for i, group in enumerate(grouped_chunks, 1):
            chunk_nums = [c['num'] for c in group]
            print(f"Smoothing group {i}/{len(grouped_chunks)} (chunks {chunk_nums})...", end=" ")
            
            smoothed_text = self.smooth_chunk_group(group)
            
            # Create group info
            chunk_range = f"{chunk_nums[0]}-{chunk_nums[-1]}" if len(chunk_nums) > 1 else str(chunk_nums[0])
            all_subjects = ": ".join([c['subjects'] for c in group])
            
            smoothed_groups.append({
                'chunk_range': chunk_range,
                'subjects': all_subjects,
                'text': smoothed_text
            })
            
            print("Done")
        
        # Write output
        self.write_output(smoothed_groups, output_path)
        print(f"\nSmoothed {len(chunks)} chunks in {len(grouped_chunks)} groups")
        print(f"Output written to: {output_path}")
    
    def write_output(self, groups: list, output_path: str):
        """Write smoothed groups to output file."""
        with open(output_path, 'w', encoding='utf-8') as f:
            for group_data in groups:
                f.write(f"..... chunks {group_data['chunk_range']} [{group_data['subjects']}] .....\n")
                f.write(f"{group_data['text']}\n\n")


def main(input_path: str, output_path: str):
    """Main entry point for chunk smoother."""
    smoother = ChunkSmoother()
    smoother.process_chunks(input_path, output_path)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) != 3:
        print("Usage: python smooth_chunks.py <input_chunks_file> <output_file>")
        print("Example: python smooth_chunks.py output_chunks.txt smoothed_output.txt")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2]
    
    main(input_file, output_file)
