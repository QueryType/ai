# Story Summarizer

A sophisticated multi-agent workflow system for intelligent story summarization built with Strands Agents SDK.

## Overview

The Story Summarizer uses a **sequential multi-agent workflow** to analyze and summarize stories while preserving their essence, tone, and narrative style. Each agent specializes in a specific aspect of story analysis:

### Agent Architecture

**🎭 Agent 1: Character Analyst**
- Identifies all characters (main, secondary, minor)
- Extracts character attributes and traits
- Maps relationships between characters
- Tracks character development and arcs
- **Output:** Detailed character analysis

**🎨 Agent 2: Content & Tone Analyst**
- Analyzes themes and narrative tone
- Identifies story structure and plot points
- Examines literary devices and writing techniques
- Assesses emotional arc and pacing
- **Output:** Comprehensive content analysis

**✍️ Agent 3: Summary Generator**
- Creates abridged version of the story
- Preserves original tone and narrative voice
- Maintains character dynamics
- Respects word/length limits with adaptive strength (LIGHT/MEDIUM/HEAVY)
- **Output:** Condensed story (not a description)

**📖 Agent 4: Title Generator**
- Creates concise, engaging title
- Captures the essence of the summarized story
- Generates titles in 3-8 words
- **Output:** Story title

**🔄 Agent 5: Reconstruction Generator**
- Rebuilds stories from analyses only (without original text)
- Uses character and content analyses as blueprint
- Maintains narrative consistency with analyzed elements
- **Output:** Reconstructed story based on analyses

### Data Flow

**Summarization Mode (use_reconstruction=False):**
```
Story Input → Character Analyst → Content Analyst → Summary Generator → Title Generator
                     ↓                  ↓                    ↓                  ↓
            Character Analysis  Content Analysis      Final Summary         Title
                                                   (with original story)
```

**Reconstruction Mode (use_reconstruction=True, default):**
```
Story Input → Character Analyst → Content Analyst → Reconstruction Generator → Title Generator
                     ↓                  ↓                       ↓                     ↓
            Character Analysis  Content Analysis      Reconstructed Story          Title
                                                    (from analyses only)
```

## Installation

Ensure you have the required dependencies:

```bash
pip install strands-agents>=1.0.0
pip install python-dotenv
pip install requests
```

## Configuration

The system is configured to use a local OpenAI-compatible API server (such as LM Studio or llama.cpp).

Edit [config.py](config.py) to configure your model:

```python
# Local server configuration
LOCAL_BASE = "http://10.0.0.4:8080"
LOCAL_BASE_URL = f"{LOCAL_BASE}/v1"

llm_model = OpenAIModel(
    client_args={
        "base_url": LOCAL_BASE_URL,
        "api_key": "not-needed-for-local-testing",
    },
    model_id="mistralai/magistral-small-2509",
    params={
        "max_tokens": 10240,
        "temperature": 0.7,
    }
)
```

Alternatively, use RunPod or other OpenAI-compatible providers (see comments in [config.py](config.py)).

## Usage

### Basic Usage

```python
from story_summarizer import summarize_story

# Your story text
story = """
Your story content here...
"""

# Get a summary (uses reconstruction mode by default)
result = summarize_story(story, max_words=150)
print(result['summary_text'])
print(f"Title: {result['title']}")
```

### Full Workflow with Analysis

```python
from story_summarizer import summarize_story

# Run complete workflow with reconstruction (default)
result = summarize_story(
    story=your_story_text,
    max_words=200,
    focus_areas="character relationships and emotional growth",
    use_reconstruction=True  # Default: reconstruct from analyses only
)

# Or use summarization mode (includes original story in context)
result = summarize_story(
    story=your_story_text,
    max_words=200,
    focus_areas="character relationships and emotional growth",
    use_reconstruction=False  # Summarize with original story
)

# Access results
print("Title:", result['title'])
print("Summary:", result['summary_text'])
print("Original words:", result['original_words'])
print("Summary words:", result['summary_words'])
print("Strength used:", result['strength_used'])
```

### Custom Model Configuration

Edit [config.py](config.py) to change model settings:

```python
from story_summarizer import summarize_story

# Optionally specify model context limit
result = summarize_story(
    story=your_story,
    max_words=200,
    model_context_limit=8192  # Specify manually, or None for auto-detect
)
```

## Features

✅ **Sequential Workflow** - Each agent builds context for the next  
✅ **Preserves Original Style** - Maintains tone, voice, and narrative perspective  
✅ **Adaptive Summarization Strength** - Automatic LIGHT/MEDIUM/HEAVY levels based on compression ratio  
✅ **Flexible Length Control** - Specify exact word limits with ±5% accuracy targets  
✅ **Focus Areas** - Direct the summary to emphasize specific aspects  
✅ **Dual Workflow Modes** - Reconstruction (analyses-only) or Summarization (with original)  
✅ **Batch Processing** - Process entire folders of stories automatically  
✅ **Context Management** - Auto-detection of model context limits with smart truncation  
✅ **Structured Analysis** - Detailed character and content insights  
✅ **Compression Metrics** - Track original vs. summary word counts  

## Example Output

For a 200-word story:

```
📊 Step 1/3: Analyzing characters and relationships...
✓ Character analysis complete

🎨 Step 2/3: Analyzing content, theme, and tone...
✓ Content analysis complete

✍️ Step 3/3: Generating abridged summary...
✓ Summary generation complete

� Step 4/4: Generating title...
✓ Title generation complete

📈 Metadata:
   Original: 200 words
   Summary: 75 words
   Compression: 37.5%

📖 Title: [Engaging story title]

📝 Abridged Story:
[Condensed narrative that reads like the original story...]
```

## Running Examples

The package includes comprehensive examples:

```bash
# Run the main example
python -m story_summarizer.story_summarizer

# Run multiple usage examples
python -m story_summarizer.example_usage

# Run batch processing
python -m story_summarizer.run_batch
```

## Project Structure

```
story_summarizer/
├── __init__.py           # Package initialization & exports
├── config.py             # Model configuration & constants
├── agents.py             # All agent definitions
├── workflows.py          # Workflow implementations
├── utils.py              # Utility functions
├── story_summarizer.py   # Main entry point example
├── example_usage.py      # Usage examples
├── batch_summarizer.py   # Batch processing module
├── run_batch.py          # Batch processing runner
└── README.md             # This file
```

## How It Works

1. **Character Analysis Phase**
   - Agent 1 receives the full story
   - Extracts and structures all character information
   - Creates comprehensive character analysis

2. **Content Analysis Phase**
   - Agent 2 receives the story
   - Analyzes themes, tone, and narrative elements
   - Identifies key plot points and literary devices

3. **Adaptive Strength Calculation**
   - System determines LIGHT (10% reduction), MEDIUM (40% reduction), or HEAVY (custom target)
   - Adjusts target word count with ±5% accuracy goals
   - Optimizes for context window constraints

4. **Summary/Reconstruction Generation Phase**
   - **Reconstruction Mode (default):** Agent 5 receives only analyses, rebuilds story
   - **Summarization Mode:** Agent 3 receives story + analyses, creates abridged version
   - Maintains original style and narrative voice
   - Respects adaptive word limits

5. **Title Generation Phase**
   - Agent 4 receives the generated output
   - Creates a concise, engaging title
   - Captures the essence of the story in 3-8 words

## Handling Long Stories

The system is designed to handle stories that exceed typical context windows:

**Key Strategies:**

1. **Auto Context Detection** - Automatically queries LM Studio/llama.cpp for exact context limits
2. **Accurate Token Counting** - Uses model's actual tokenizer, not approximations
3. **Reconstruction Mode (Default)** - Only passes analyses to the generator, not the full story
   - Example: A 10,000-word story → ~500-1000 words of analysis context
   - This allows processing stories 10-20x larger than the context window
4. **Smart Truncation** (Summarization mode) - If story + analyses exceed 85% of context, keeps first 40% and last 20% of story with clear marking
5. **Adaptive Strength** - Automatically adjusts compression level based on story length

**Practical Limits:**
- Character/Content analysts must process the full story (constrained by their context window)
- With reconstruction mode: Can handle stories up to ~80% of model's context window
- Typical 8K context model: Stories up to ~6,000-7,000 words
- Typical 32K context model: Stories up to ~25,000-28,000 words

## Best Practices

- **Story Length**: Works best with stories of 150-2000 words, but can handle much longer
- **Summary Ratio**: Aim for 20-50% of original length for optimal results
- **Focus Areas**: Be specific about what to emphasize
- **Tone Preservation**: The system works hard to maintain original voice
- **Workflow Mode**: Use reconstruction mode (default) for better context efficiency with long stories
- **Batch Processing**: Use `batch_summarizer.py` for processing multiple stories
- **Context Limits**: System auto-detects limits; manually specify if needed

## Customization

You can modify agent prompts in [agents.py](agents.py) to:
- Change analysis depth or focus
- Adjust output format requirements
- Modify summarization style
- Add additional analysis dimensions

Edit [config.py](config.py) to:
- Change model endpoints
- Adjust temperature and token limits
- Configure different OpenAI-compatible providers

Modify [workflows.py](workflows.py) to:
- Adjust adaptive strength thresholds
- Change context management strategies
- Add custom workflow steps

## Requirements

- Python 3.8+
- Strands Agents SDK
- OpenAI-compatible local LLM server (LM Studio, llama.cpp, RunPod, etc.)
- `python-dotenv` for environment variables
- `requests` for API communication

## License

Part of the Strands Agents SDK ecosystem.

## Support

For issues or questions:
- Strands Agents Documentation: https://strandsagents.com/latest/documentation/
- GitHub: https://github.com/strands-agents/sdk-python

---

Built with ❤️ using [Strands Agents SDK](https://strandsagents.com/)
