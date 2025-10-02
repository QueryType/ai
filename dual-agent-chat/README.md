# Dual Agent Chat

A lightweight, configuration-driven system for running conversations between two AI agents with advanced interactive controls.

## 🌟 Key Features

- **Memory-Efficient Architecture**: Single message list with role switching (50% memory savings)
- **Configuration-Driven**: All settings in JSON + Markdown files
- **OpenAI-Compatible**: Works with any OpenAI-compatible API (LM Studio, Ollama, etc.)
- **Interactive Control**: Press SPACE to interrupt and manually enter messages
- **Conversation Continuation**: Resume and extend existing conversations
- **Turn-by-Turn Viewer**: Review conversations interactively

## 🚀 Quick Start

### Installation

```bash
# Clone or navigate to the project
cd dual-agent-chat

# Install dependencies
pip install -r requirements.txt
```

### Configure Your LLM Server

Edit `app.json` to point to your LLM server:

```json
{
  "llm_config": {
    "api_base_url": "http://localhost:1234/v1",
    "model": "your-model-name"
  }
}
```

### Run Your First Conversation

```bash
# Start with the default Fantasy Tavern scenario
python main.py

# Use a different scenario
python main.py scenarios/debate/debate_config.json
```

## 💡 How It Works

### The Innovation: Role Switching

Instead of maintaining two separate message histories (doubling memory), we use a single message list:

1. **System Prompt**: Dynamically built as `world_info + active_character_card`
2. **Role Flip**: All messages switch between `user` ↔ `assistant` when speakers change
3. **Context Preserved**: Full conversation history maintained with 50% less memory

```
Turn 1 (Alice speaks):
  system: [World + Alice's card]
  assistant: "Hello!"

Turn 2 (Bob speaks):
  system: [World + Bob's card]    ← Changed!
  user: "Hello!"                   ← Role flipped!
  assistant: "Hi there."
```

## 🎮 Advanced Features

### Interactive Interruption

Press SPACE during generation to take manual control:

```bash
python main.py --interrupt-timeout 10
```

When you see `⏸️ Press SPACE to interrupt (10s timeout)...`, press SPACE to enter your own message. Type `auto` to resume automatic generation.

[Full Guide →](docs/FEATURES.md#interactive-interruption)

### Continue Conversations

Add more turns to existing conversations:

```bash
python main.py --continue conversations/my_chat.json --add-turns 5
```

[Full Guide →](docs/FEATURES.md#conversation-continuation)

### View Conversations

Interactive turn-by-turn viewing:

```bash
# List all conversations
python view_conversation.py

# View specific conversation interactively
python view_conversation.py 1 -i
```

[Full Guide →](docs/FEATURES.md#viewing-conversations)

## 📁 Project Structure

```
dual-agent-chat/
├── README.md                   # You are here
├── main.py                     # Main application
├── view_conversation.py        # Conversation viewer
├── app.json                    # Default configuration
├── config_loader.py            # Config handling
├── message_manager.py          # Message list & role switching
├── llm_client.py              # LLM API client
├── requirements.txt            # Python dependencies
├── docs/                       # Documentation
│   ├── USAGE.md               # Comprehensive usage guide
│   ├── ARCHITECTURE.md        # Technical details
│   └── FEATURES.md            # All features explained
├── scenarios/                  # Example scenarios
│   ├── fantasy_tavern/        # Default: Medieval tavern
│   └── debate/                # Philosophy debate
└── conversations/              # Saved conversations (auto-created)
```

## 📋 Command Reference

### Basic Usage

```bash
# Default scenario
python main.py

# Custom scenario
python main.py scenarios/debate/debate_config.json

# Start in interactive mode
python main.py --interactive
```

### Continuation

```bash
# Continue with 5 more turns
python main.py --continue conversations/chat.json --add-turns 5

# Continue with custom timeout
python main.py --continue conversations/chat.json --add-turns 10 --interrupt-timeout 8
```

### Viewing

```bash
# List all conversations
python view_conversation.py

# View conversation #1
python view_conversation.py 1

# Interactive mode (press Enter for each turn)
python view_conversation.py 1 -i

# Export to markdown
python view_conversation.py 1 --export
```

### Options

```bash
--interrupt-timeout N     # Seconds to wait for SPACE interrupt (default: 5)
--interactive            # Start in fully interactive mode
--continue FILE          # Continue from existing conversation
--add-turns N            # Number of turns to add (with --continue)
```

## 🎭 Example Scenarios

### Fantasy Tavern (Default)

Two travelers meet in a medieval tavern:
- **Eldric**: A merchant storyteller
- **Mira**: A herbalist healer

```bash
python main.py
```

### Philosophical Debate

University students debate AI consciousness:
- **Alex**: Believes AI can achieve consciousness
- **Sam**: Skeptical of AI consciousness

```bash
python main.py scenarios/debate/debate_config.json
```

## 🛠️ Creating Custom Scenarios

1. Create a scenario directory:
   ```bash
   mkdir -p scenarios/my_scenario
   ```

2. Create three markdown files:
   - `world.md` - Setting, context, rules
   - `character_a.md` - First character's card
   - `character_b.md` - Second character's card

3. Create `my_scenario_config.json`:
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
       "model": "your-model",
       "temperature": 0.8,
       "max_tokens": 200
     },
     "conversation_config": {
       "max_turns": 10,
       "save_conversation": true,
       "output_dir": "conversations",
       "interrupt_timeout": 5
     }
   }
   ```

4. Run your scenario:
   ```bash
   python main.py scenarios/my_scenario/my_scenario_config.json
   ```

## 📚 Documentation

- **[Usage Guide](docs/USAGE.md)** - Comprehensive how-to with examples
- **[Architecture](docs/ARCHITECTURE.md)** - Technical design and implementation
- **[Features](docs/FEATURES.md)** - Detailed feature documentation

## 🔧 Requirements

- Python 3.7+
- OpenAI-compatible LLM server (LM Studio, Ollama, vLLM, etc.)
- Dependencies: `requests` (see `requirements.txt`)

## 🤝 Contributing

This is a clean, well-documented codebase. Feel free to:
- Add new scenarios
- Enhance features
- Improve documentation
- Report issues

## 📄 License

Open source - use freely for your projects.

## 🎯 Design Philosophy

**Simple & Powerful**: Built from the ground up with:
- Clean, readable code
- Comprehensive documentation
- Configuration over code
- Memory efficiency
- User control (interactive interruption)

---

**Ready to get started?** → [Read the Usage Guide](docs/USAGE.md)
