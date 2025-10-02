# Quick Start Guide

## Prerequisites

1. **Python 3.7+** installed
2. **LLM Server** running (e.g., LM Studio, Ollama, or any OpenAI-compatible server)

## Installation

```bash
cd dual-agent-chat
pip install -r requirements.txt
```

## Running Your First Conversation

### Step 1: Start Your LLM Server

Make sure you have an LLM server running. Examples:

**LM Studio:**
- Open LM Studio
- Load a model
- Start the server (default: http://localhost:1234)

**Ollama:**
```bash
ollama serve
# Server runs on http://localhost:11434
```

### Step 2: Configure the Application

Edit `app.json` to match your setup:

```json
{
  "llm_config": {
    "api_base_url": "http://localhost:1234/v1",  // Your LLM server URL
    "model": "local-model",                       // Your model name
    "temperature": 0.8,
    "max_tokens": 200
  }
}
```

### Step 3: Run the Application

```bash
python main.py
```

That's it! The two agents will start conversing.

## Creating Custom Scenarios

### Quick Method: Duplicate and Edit

1. Copy the example scenario:
```bash
cp -r scenarios/fantasy_tavern scenarios/my_scenario
```

2. Edit the files:
   - `world.md` - Describe the setting and rules
   - `character_a.md` - Define first character
   - `character_b.md` - Define second character

3. Create a new config file:
```bash
cp app.json my_scenario.json
```

4. Update `my_scenario.json` to point to your files:
```json
{
  "scenario_name": "My Custom Scenario",
  "world_info_file": "scenarios/my_scenario/world.md",
  "character_a_file": "scenarios/my_scenario/character_a.md",
  "character_b_file": "scenarios/my_scenario/character_b.md",
  ...
}
```

5. Run with your config:
```bash
python main.py  # Uses app.json by default
# or modify main.py to use: DualAgentChat("my_scenario.json")
```

## Configuration Options

### LLM Settings

```json
"llm_config": {
  "api_base_url": "http://localhost:1234/v1",  // API endpoint
  "api_key": "not-needed",                      // API key (if required)
  "model": "local-model",                        // Model name
  "temperature": 0.8,                            // Creativity (0.0-2.0)
  "max_tokens": 200,                             // Response length
  "top_p": 0.95,                                 // Nucleus sampling
  "frequency_penalty": 0.0,                      // Reduce repetition
  "presence_penalty": 0.0                        // Encourage new topics
}
```

### Conversation Settings

```json
"conversation_config": {
  "max_turns": 10,                               // Number of turns
  "save_conversation": true,                     // Save to file?
  "output_dir": "conversations",                 // Save location
  "initial_message": "Hello..."                  // Starting message (optional)
}
```

## Tips for Great Conversations

1. **World Info**: Keep it concise but descriptive. Include:
   - Setting/location
   - Time/atmosphere
   - Any special rules or context

2. **Character Cards**: Make them distinct:
   - Clear personality traits
   - Speaking style/mannerisms
   - Background and motivations
   - What makes them unique

3. **Temperature**: 
   - Lower (0.3-0.6) = More focused, consistent
   - Medium (0.7-0.9) = Good balance
   - Higher (1.0-1.5) = More creative, unpredictable

4. **Max Tokens**:
   - 50-100: Short, snappy responses
   - 150-250: Moderate conversation
   - 300-500: Detailed responses

## Troubleshooting

### "Connection error"
- Make sure your LLM server is running
- Check the `api_base_url` in `app.json`
- Verify the port number is correct

### Responses are too short/long
- Adjust `max_tokens` in `llm_config`
- Modify character cards to encourage desired length

### Characters sound too similar
- Make character cards more distinct
- Increase differences in personality and speaking style
- Adjust temperature for more variety

### Out of memory errors
- Reduce `max_turns`
- Lower `max_tokens`
- Use a smaller model

## Example Scenarios

### Fantasy Tavern (Included)
Two characters meet in a medieval tavern setting.

### Detective Interview
```
World: Police interrogation room
Character A: Seasoned detective
Character B: Mysterious witness
```

### Sci-Fi First Contact
```
World: Diplomatic meeting on space station
Character A: Human ambassador
Character B: Alien diplomat
```

### Comedy Duo
```
World: Comedy club green room
Character A: Optimistic new comedian
Character B: Cynical veteran comedian
```

## Advanced Usage

### Multiple Configurations

Create different JSON files for different scenarios:

```bash
python -c "from main import DualAgentChat; DualAgentChat('scenario1.json').run()"
```

### Viewing Saved Conversations

Conversations are saved in `conversations/` as JSON files. View with:

```bash
cat conversations/*.json | jq
```

## Next Steps

- Experiment with different temperature settings
- Try various character combinations
- Create your own unique scenarios
- Share interesting conversations!

## Need Help?

Check the [README.md](README.md) for architecture details and [TODO.md](TODO.md) for development status.
