# Story Summarizer

A sophisticated multi-agent workflow system for intelligent story summarization built with Strands Agents SDK.

## Overview

The Story Summarizer uses a **sequential 4-agent workflow** to analyze and summarize stories while preserving their essence, tone, and narrative style. Each agent specializes in a specific aspect of story analysis:

### Agent Architecture

**🎭 Agent 1: Character Analyst**
- Identifies all characters (main, secondary, minor)
- Extracts character attributes and traits
- Maps relationships between characters
- Tracks character development and arcs
- **Output:** Structured JSON with character data

**🎨 Agent 2: Content & Tone Analyst**
- Analyzes themes and narrative tone
- Identifies story structure and plot points
- Examines literary devices and writing techniques
- Assesses emotional arc and pacing
- **Output:** Structured JSON with content analysis

**✍️ Agent 3: Summary Generator**
- Creates abridged version of the story
- Preserves original tone and narrative voice
- Maintains character dynamics
- Respects word/length limits
- **Output:** Condensed story (not a description)

**📖 Agent 4: Title Generator**
- Creates concise, engaging title
- Captures the essence of the summarized story
- Generates titles in 3-8 words
- **Output:** Story title

### Data Flow

```
Story Input → Character Analyst → Content Analyst → Summary Generator → Title Generator
                     ↓                  ↓                    ↓                  ↓
              Character Map      Content Analysis      Final Summary         Title
```

## Installation

Ensure you have the required dependencies:

```bash
pip install strands-agents>=1.0.0
pip install strands-agents-tools>=0.2.0
pip install python-dotenv
```

## Configuration

Create a `.env` file in the `story_summarizer` directory. You can copy `.env.example` as a starting point:

```bash
cp .env.example .env
```

Then edit `.env` with your configuration:

```env
# OpenAI API Configuration (for local server)
OPENAI_BASE_URL=http://localhost:7890/v1
OPENAI_API_KEY=not-needed

# Model Configuration
MODEL_ID=mistralai/magistral-small-2509
MAX_TOKENS=10240
TEMPERATURE=0.7

# Batch Processing Configuration (optional - for run_batch.py)
INPUT_FOLDER=./input
OUTPUT_FOLDER=./output
FOCUS_AREAS=focus on the theme and summarize in 1500 words, do not add your own interpretation.
MAX_WORDS=1500
```

**Security Note:** Update `OPENAI_BASE_URL` to point to your local OpenAI-compatible API server. Never commit your `.env` file to version control.

## Usage

### Basic Usage

```python
from story_summarizer import StorySummarizer

# Initialize the summarizer
summarizer = StorySummarizer()

# Your story text
story = """
Your story content here...
"""

# Get a quick summary
summary = summarizer.quick_summary(story, max_words=150)
print(summary)
```

### Full Workflow with Analysis

```python
from story_summarizer import StorySummarizer

summarizer = StorySummarizer()

# Run complete workflow
result = summarizer.summarize(
    story=your_story_text,
    max_words=200,
    focus_areas="character relationships and emotional growth"
)

# Access different components
print("Characters:", result['character_analysis'])
print("Content:", result['content_analysis'])
print("Summary:", result['summary'])
print("Metadata:", result['metadata'])
```

### Custom Model Configuration

```python
summarizer = StorySummarizer(
    model_id="your-model-id",
    region_name="your-region"
)
```

## Features

✅ **Sequential Workflow** - Each agent builds context for the next  
✅ **Preserves Original Style** - Maintains tone, voice, and narrative perspective  
✅ **Flexible Length Control** - Specify exact word limits for summaries  
✅ **Focus Areas** - Direct the summary to emphasize specific aspects  
✅ **Structured Analysis** - JSON-formatted character and content insights  
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
# Run the main example in story_summarizer.py
python story_summarizer.py

# Run multiple usage examples
python example_usage.py
```

## Project Structure

```
story_summarizer/
├── __init__.py           # Package initialization
├── story_summarizer.py   # Main workflow implementation
├── example_usage.py      # Usage examples
└── README.md            # This file
```

## How It Works

1. **Character Analysis Phase**
   - Agent 1 receives the full story
   - Extracts and structures all character information
   - Creates a comprehensive character map

2. **Content Analysis Phase**
   - Agent 2 receives the story + character context
   - Analyzes themes, tone, and narrative elements
   - Identifies key plot points and literary devices

3. **Summary Generation Phase**
   - Agent 3 receives story + both analyses + user constraints
   - Generates abridged version maintaining original style
   - Respects word limits while preserving essence

4. **Title Generation Phase**
   - Agent 4 receives the generated summary
   - Creates a concise, engaging title
   - Captures the essence of the story in 3-8 words

## Best Practices

- **Story Length**: Works best with stories of 150-2000 words
- **Summary Ratio**: Aim for 20-50% of original length
- **Focus Areas**: Be specific about what to emphasize
- **Tone Preservation**: The system works hard to maintain original voice

## Customization

You can modify agent prompts in `story_summarizer.py` to:
- Change analysis depth or focus
- Adjust output format requirements
- Modify summarization style
- Add additional analysis dimensions

## Requirements

- Python 3.8+
- Strands Agents SDK
- AWS Bedrock access with Claude models
- Environment variables configured

## License

Part of the Strands Agents SDK ecosystem.

## Support

For issues or questions:
- Strands Agents Documentation: https://strandsagents.com/latest/documentation/
- GitHub: https://github.com/strands-agents/sdk-python

---

Built with ❤️ using [Strands Agents SDK](https://strandsagents.com/)
