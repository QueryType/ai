"""Story Chunker - Extract specific subjects from story text files."""

import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Set
from openai import OpenAI

from config import NO_CHUNK_SIZE, CHUNK_SIZE, LLM_CONFIG, SYSTEM_PROMPT, PARALLEL


class StoryChunker:
    """Chunks stories and extracts specific subjects using LLM."""
    
    def __init__(self):
        """Initialize the story chunker with LLM client."""
        self.client = OpenAI(
            base_url=LLM_CONFIG["base_url"],
            api_key=LLM_CONFIG["api_key"]
        )
    
    def read_story(self, file_path: str) -> str:
        """Read the story file."""
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    
    def chunk_text(self, text: str) -> List[str]:
        """Split text into chunks based on configuration."""
        if len(text) <= NO_CHUNK_SIZE:
            return [text]
        
        chunks = []
        for i in range(0, len(text), CHUNK_SIZE):
            chunks.append(text[i:i + CHUNK_SIZE])
        
        return chunks
    
    def check_subjects_in_chunk(self, chunk: str, subjects: List[str]) -> List[str]:
        """Use LLM to check if chunk contains any of the specified subjects."""
        user_prompt = f"""Text chunk:
{chunk}

Subjects to check: {', '.join(subjects)}

Analyze the text and return which subjects (if any) are present."""
        
        try:
            response = self.client.chat.completions.create(
                model=LLM_CONFIG["model"],
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=LLM_CONFIG["temperature"],
                max_tokens=LLM_CONFIG["max_tokens"],
                response_format={"type": "json_object"}  # Phase 2: force JSON output
            )
            
            result_text = response.choices[0].message.content
            
            # Handle empty/None responses
            if not result_text or not result_text.strip():
                print("Warning: Empty LLM response")
                return self._fallback_substring_match(chunk, subjects)
            
            result_text = result_text.strip()
            
            # Phase 3: Try direct JSON parse first, then regex extraction
            matches = self._parse_json_response(result_text)
            if matches is not None:
                return matches
            
            # Phase 4: Fallback to substring matching
            print(f"Warning: Could not parse response, using substring fallback")
            return self._fallback_substring_match(chunk, subjects)
                
        except Exception as e:
            print(f"Error calling LLM: {e}")
            return self._fallback_substring_match(chunk, subjects)
    
    def _parse_json_response(self, result_text: str) -> List[str] | None:
        """Try to parse JSON from LLM response. Returns matches list or None if unparseable."""
        # Attempt 1: Direct parse
        try:
            result = json.loads(result_text)
            return result.get("matches", [])
        except json.JSONDecodeError:
            pass
        
        # Attempt 2: Extract JSON object via regex (handles markdown fences, preamble, etc.)
        json_match = re.search(r'\{[^{}]*"matches"[^{}]*\}', result_text, re.DOTALL)
        if json_match:
            try:
                result = json.loads(json_match.group())
                return result.get("matches", [])
            except json.JSONDecodeError:
                pass
        
        # Attempt 3: Broader regex for any JSON object
        json_match = re.search(r'\{.*\}', result_text, re.DOTALL)
        if json_match:
            try:
                result = json.loads(json_match.group())
                return result.get("matches", [])
            except json.JSONDecodeError:
                pass
        
        return None  # Signal that parsing failed entirely
    
    def _fallback_substring_match(self, chunk: str, subjects: List[str]) -> List[str]:
        """Phase 4: Degraded fallback - simple case-insensitive substring match."""
        chunk_lower = chunk.lower()
        matches = [s for s in subjects if s.lower() in chunk_lower]
        if matches:
            print(f"  [substring fallback] Found: {', '.join(matches)}")
        return matches
    
    def _process_batch(self, batch: List[tuple], subjects: List[str], total: int) -> List[dict]:
        """Process a batch of (index, chunk) tuples in parallel threads."""
        results = {}  # index -> matches
        
        with ThreadPoolExecutor(max_workers=len(batch)) as executor:
            future_to_idx = {
                executor.submit(self.check_subjects_in_chunk, chunk, subjects): idx
                for idx, chunk in batch
            }
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    results[idx] = future.result()
                except Exception as e:
                    print(f"Error processing chunk {idx}: {e}")
                    results[idx] = []
        
        # Print results and collect matches in order
        matched = []
        for idx, chunk in batch:
            matches = results.get(idx, [])
            if matches:
                print(f"Chunk {idx}/{total}: Found matches: {', '.join(matches)}")
                matched.append({
                    "chunk_num": idx,
                    "matches": matches,
                    "content": chunk
                })
            else:
                print(f"Chunk {idx}/{total}: No matches")
        return matched
    
    def process_story(self, story_path: str, subjects: List[str], output_path: str):
        """Process story file and extract chunks matching subjects."""
        # Read the story
        print(f"Reading story from: {story_path}")
        text = self.read_story(story_path)
        print(f"Story length: {len(text)} characters")
        
        # Chunk the text
        chunks = self.chunk_text(text)
        total = len(chunks)
        print(f"Created {total} chunks (parallel={PARALLEL})")
        
        # Build indexed list: [(1, chunk), (2, chunk), ...]
        indexed_chunks = list(enumerate(chunks, 1))
        
        # Process in batches of PARALLEL size
        matched_chunks = []
        for batch_start in range(0, len(indexed_chunks), PARALLEL):
            batch = indexed_chunks[batch_start:batch_start + PARALLEL]
            batch_indices = f"{batch[0][0]}-{batch[-1][0]}"
            print(f"\nBatch [{batch_indices}] of {total}...")
            matched = self._process_batch(batch, subjects, total)
            matched_chunks.extend(matched)
        
        # Write output
        self.write_output(matched_chunks, output_path)
        print(f"\nProcessed {total} chunks, found {len(matched_chunks)} matching chunks")
        print(f"Output written to: {output_path}")
    
    def write_output(self, matched_chunks: List[dict], output_path: str):
        """Write matched chunks to output file."""
        with open(output_path, 'w', encoding='utf-8') as f:
            for chunk_data in matched_chunks:
                matches_str = ", ".join(chunk_data["matches"])
                f.write(f"..... chunk{chunk_data['chunk_num']} [{matches_str}] .....\n")
                f.write(f"{chunk_data['content']}\n\n")


def main(story_path: str, subjects: List[str], output_path: str):
    """Main entry point for story chunker."""
    chunker = StoryChunker()
    chunker.process_story(story_path, subjects, output_path)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 4:
        print("Usage: python story_chunker.py <story_file> <output_file> <subject1> [subject2] ...")
        print("Example: python story_chunker.py story.txt output.txt nature 'naughty child' 'too good to be true'")
        sys.exit(1)
    
    story_file = sys.argv[1]
    output_file = sys.argv[2]
    subjects_list = sys.argv[3:]
    
    main(story_file, subjects_list, output_file)
