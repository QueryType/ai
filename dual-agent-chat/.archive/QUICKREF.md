# Quick Reference Card

## Installation & Setup

```bash
cd dual-agent-chat
pip install -r requirements.txt
```

## Running the App

```bash
# Default scenario (Fantasy Tavern)
python main.py

# Custom scenario
python main.py scenarios/debate/debate_config.json

# Any config file
python main.py path/to/your/config.json
```

## File Structure at a Glance

```
dual-agent-chat/
├── main.py                    # Run this!
├── app.json                   # Default config
├── config_loader.py           # Loads configs
├── message_manager.py         # Handles messages
├── llm_client.py             # Talks to LLM
├── scenarios/                # Your scenarios here
└── conversations/            # Saved conversations
```

## Creating a New Scenario

### 1. Create folder
```bash
mkdir -p scenarios/my_scenario
```

### 2. Create three markdown files

**world.md** - The setting
```markdown
# Setting Name
## Setting
Describe the location and time
## Atmosphere
Describe the mood and feeling
## Rules of Engagement
Any special rules or constraints
```

**character_a.md** - First character
```markdown
# Character: Name
## Basic Information
- Name, role, age
## Personality
Key traits
## Speaking Style
How they talk
```

**character_b.md** - Second character
(Same format as character_a.md)

### 3. Create config JSON

```json
{
  "scenario_name": "My Scenario",
  "world_info_file": "scenarios/my_scenario/world.md",
  "character_a_file": "scenarios/my_scenario/character_a.md",
  "character_b_file": "scenarios/my_scenario/character_b.md",
  "character_a_name": "Alice",
  "character_b_name": "Bob",
  "starting_character": "a",
  "llm_config": {
    "api_base_url": "http://localhost:1234/v1",
    "model": "local-model",
    "temperature": 0.8,
    "max_tokens": 200
  },
  "conversation_config": {
    "max_turns": 10,
    "save_conversation": true,
    "output_dir": "conversations"
  }
}
```

### 4. Run it
```bash
python main.py scenarios/my_scenario/config.json
```

## Configuration Quick Reference

### Temperature
- `0.1-0.3` - Very focused, deterministic
- `0.5-0.7` - Balanced
- `0.8-1.0` - Creative, varied
- `1.1-2.0` - Very creative, unpredictable

### Max Tokens
- `50-100` - Brief responses
- `150-250` - Normal conversation
- `300-500` - Detailed responses

### Common LLM Server URLs

| Server | Default URL |
|--------|-------------|
| LM Studio | `http://localhost:1234/v1` |
| Ollama | `http://localhost:11434/v1` |
| Text Generation WebUI | `http://localhost:5000/v1` |
| OpenAI | `https://api.openai.com/v1` |

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Connection error | Check LLM server is running |
| Wrong URL | Update `api_base_url` in config |
| Responses too short | Increase `max_tokens` |
| Responses too long | Decrease `max_tokens` |
| Too repetitive | Increase `temperature` |
| Too random | Decrease `temperature` |
| Not saving | Check `save_conversation: true` |

## Saved Conversations

Location: `conversations/`  
Format: JSON  
Filename: `ScenarioName_YYYYMMDD_HHMMSS.json`

View with:
```bash
cat conversations/*.json | jq
```

## Module Functions

### config_loader.py
```python
loader = ConfigLoader("app.json")
loader.load()  # Load all files
loader.world_info  # Access world info
loader.character_a_info  # Access character A
```

### message_manager.py
```python
manager = MessageManager(world, char_a, char_b, name_a, name_b)
manager.add_turn('a', "Hello")  # Add message
manager.get_messages_for_character('a')  # Get formatted messages
```

### llm_client.py
```python
client = LLMClient(config)
response = client.chat_completion(messages)
client.test_connection()  # Test API
```

## Command Line Usage

```bash
# Run with default config
python main.py

# Run with custom config
python main.py my_config.json

# Test individual components
python config_loader.py
python message_manager.py
python llm_client.py
```

## Tips for Better Conversations

1. **Make characters distinct** - Different personalities, speaking styles
2. **Set clear context** - Good world info helps grounding
3. **Balance temperature** - 0.7-0.8 is usually good
4. **Adjust max_tokens** - Match desired response length
5. **Use initial_message** - Start strong with a good opener
6. **Experiment** - Try different settings and scenarios!

## Example Scenarios Included

| Scenario | Characters | Tone | Config |
|----------|-----------|------|--------|
| Fantasy Tavern | Merchant & Herbalist | Friendly | app.json |
| Philosophy Debate | AI Optimist & Skeptic | Intellectual | scenarios/debate/debate_config.json |

## Getting Help

- **README.md** - Architecture overview
- **USAGE.md** - Detailed instructions
- **ARCHITECTURE.md** - Technical diagrams
- **TODO.md** - Development status
- **PROJECT_SUMMARY.md** - Complete summary

## One-Minute Start

```bash
# 1. Start LM Studio (or other LLM server)
# 2. In terminal:
cd dual-agent-chat
python main.py
# 3. Watch your agents converse!
```

That's it! 🎭
