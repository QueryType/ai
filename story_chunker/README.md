# Story Chunker

Extract specific topics, themes, or subjects from your story files. Got a long novel and want to pull out all the parts about nature, love, or mystery? Story Chunker uses AI to find and extract exactly what you're looking for.

## What Does It Do?

Story Chunker helps you:
- **Find specific content** in large text files (stories, books, articles)
- **Extract relevant passages** based on topics or themes you specify
- **Polish the results** into smooth, readable paragraphs (optional)

Perfect for researchers, writers, educators, or anyone working with large text files who needs to find and extract specific content.

## Quick Start

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Set up your AI connection:**
   Edit `config.py` and point to your local LLM endpoint (like LM Studio, Ollama, etc.):
   ```python
   base_url = "http://localhost:1234/v1"
   ```

3. **Extract content from your story:**
   ```bash
   python story_chunker.py my_story.txt results.txt "nature" "adventure"
   ```

4. **Want smoother output? Run the polisher:**
   ```bash
   python smooth_chunks.py results.txt polished_results.txt
   ```

That's it!

## Usage Guide

### Finding Content by Topic

Tell Story Chunker what topics you're looking for, and it will extract all relevant passages:

```bash
python story_chunker.py story.txt output.txt "topic1" "topic2" "topic3"
```

**Real examples:**
```bash
# Extract passages about nature and wildlife
python story_chunker.py jungle_book.txt nature_passages.txt "nature" "animals"

# Find romantic scenes
python story_chunker.py novel.txt romance.txt "love" "romance" "relationships"

# Extract specific themes
python story_chunker.py essay.txt themes.txt "human values" "moral dilemmas"
```

**Using it in your Python code:**
```python
from story_chunker import main

main("my_story.txt", ["nature", "adventure"], "output.txt")
```

### Polishing Your Results (Optional)

The extracted passages might have rough edges where they were cut from the original text. The smoother fixes this:

```bash
python smooth_chunks.py output.txt polished_output.txt
```

**In your Python code:**
```python
from smooth_chunks import main

main("output.txt", "polished_output.txt")
```

## Configuration

Open `config.py` to adjust:

- **Chunk size**: How the tool splits large files (default works for most cases)
- **LLM connection**: Your local AI server address and settings
- **Performance**: Enable parallel processing for faster results

## Requirements

- Python 3.7+
- A local LLM server (LM Studio, Ollama, or similar)
- The OpenAI Python library (for API compatibility)

## Examples

**Extract passages about specific characters:**
```bash
python story_chunker.py novel.txt character_moments.txt "Sherlock Holmes" "Dr. Watson"
```

**Find educational content:**
```bash
python story_chunker.py textbook.txt examples.txt "case study" "real-world example"
```

**Extract emotional scenes:**
```bash
python story_chunker.py story.txt emotions.txt "sadness" "joy" "tension"
```

The tool saves results showing which chunks matched which topics, so you always know where the content came from.
5. Chunk ranges show grouped chunks, subjects show all matched topics

## Example Workflows

See `example_usage.py` and `example_smooth.py` for complete working examples.

## Files

- `story_chunker.py` - Main chunking and extraction script
- `smooth_chunks.py` - Post-processing script to smooth extracted chunks
- `config.py` - Configuration settings
- `example_usage.py` - Example for story chunker
- `example_smooth.py` - Example for chunk smoother
- `requirements.txt` - Python dependencies
