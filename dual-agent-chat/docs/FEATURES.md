# Features Guide

Complete guide to all features in Dual Agent Chat.

## Table of Contents

- [Interactive Interruption](#interactive-interruption)
- [Conversation Continuation](#conversation-continuation)
- [Viewing Conversations](#viewing-conversations)
- [Configuration System](#configuration-system)

---

## Interactive Interruption

Take manual control during automatic conversation generation.

### Overview

Press SPACE during the "thinking" phase to interrupt automatic generation and manually enter a message. You can switch back to automatic mode at any time by typing `auto`.

### Basic Usage

```bash
# Start with 5 second interrupt window (default)
python main.py

# Custom timeout
python main.py --interrupt-timeout 10

# Start entirely in interactive mode
python main.py --interactive
```

### How It Works

#### Auto Mode (Default)

The system generates messages automatically, but shows an interrupt prompt before each LLM call:

```
🤖 [AUTO MODE]
[Turn 3/10] Character: Mira
⏸️  Press SPACE to interrupt (5s timeout)...
```

**Options:**
- **Press SPACE within timeout** → Enter interactive mode
- **Wait for timeout** → LLM generates message automatically

#### Interactive Mode

When you press SPACE (or start with `--interactive`), you'll see:

```
🎮 [INTERACTIVE MODE ACTIVATED]

Enter message for Mira (or type 'auto' to resume automatic mode):
> _
```

**Options:**
- **Type your message** → Your message is added to the conversation
- **Type `auto`** → Resume automatic generation

### Configuration

#### In app.json

Add `interrupt_timeout` to `conversation_config`:

```json
{
  "conversation_config": {
    "max_turns": 10,
    "interrupt_timeout": 5,
    "save_conversation": true,
    "output_dir": "conversations"
  }
}
```

#### Via Command Line

Override the config file value:

```bash
python main.py --interrupt-timeout 10
```

**Priority:** CLI argument > config file > default (5 seconds)

### Use Cases

#### Quick Interrupt (2-3 seconds)
```bash
python main.py --interrupt-timeout 2
```
Fast-paced conversations, minimal server breathing room.

#### Thoughtful Control (8-10 seconds)
```bash
python main.py --interrupt-timeout 10
```
More time to decide, better for high-latency servers.

#### Full Manual Control
```bash
python main.py --interactive
```
Every message manually entered (type `auto` to switch to automatic).

### Visual Indicators

| Indicator | Meaning |
|-----------|---------|
| `🤖 [AUTO MODE]` | Automatic generation active |
| `⏸️ Press SPACE to interrupt (Xs timeout)...` | Interrupt window open - press SPACE now! |
| `🎮 [INTERACTIVE MODE ACTIVATED]` | Waiting for your input |
| `> _` | Cursor ready for your message |
| `✅ Manual message added` | Your message was saved |
| `✅ Resuming automatic mode` | Switched back to auto |

### Saved Conversations

Manual messages are marked with `"user_provided": true`:

```json
{
  "turn": 5,
  "character": "a",
  "name": "Eldric",
  "message": "I think we should explore the ruins.",
  "user_provided": true
}
```

This lets you identify which messages were manually entered vs. LLM-generated.

### Benefits

- **Full Control**: Interrupt any turn at any time
- **Flexible**: Switch between auto and manual on the fly
- **Transparent**: User-provided messages clearly marked
- **Server-Friendly**: Configurable breathing room for backend
- **Non-Invasive**: Clean timeout-based UX

---

## Conversation Continuation

Resume and extend existing conversations while preserving the original.

### Overview

The continuation feature allows you to add more turns to an existing conversation. The original conversation file is never modified—instead, a new file is created with all the history plus the new turns.

### Basic Usage

```bash
# Continue a conversation with 5 more turns
python main.py --continue conversations/my_chat.json --add-turns 5

# Continue with custom config
python main.py my_config.json --continue conversations/my_chat.json --add-turns 10

# Continue with interrupt timeout
python main.py --continue conversations/my_chat.json --add-turns 5 --interrupt-timeout 8
```

### How It Works

1. **Load**: Reads the existing conversation JSON file
2. **Restore**: Rebuilds the complete message history and state
3. **Clone**: Creates new file with `_continued_` suffix
4. **Continue**: Adds N additional turns
5. **Save**: Each new turn appended incrementally

### File Naming

```
Original:
conversations/Fantasy_Tavern_Conversation_20251002_134944.json

Continued:
conversations/Fantasy_Tavern_Conversation_continued_20251002_150036.json
```

### Metadata Tracking

Continued conversations include special metadata:

```json
{
  "scenario": "Fantasy Tavern Conversation",
  "original_timestamp": "20251002_134944",
  "continued_timestamp": "20251002_150036",
  "continued_from": "conversations/Fantasy_Tavern_Conversation_20251002_134944.json",
  "characters": {
    "a": "Eldric",
    "b": "Mira"
  },
  "conversation": [...]
}
```

### Example Workflow

```bash
# 1. Start a conversation
python main.py
# Creates: conversations/Fantasy_Tavern_Conversation_20251002_140000.json
# Result: 10 turns

# 2. Continue it with 5 more turns
python main.py --continue conversations/Fantasy_Tavern_Conversation_20251002_140000.json --add-turns 5
# Creates: conversations/Fantasy_Tavern_Conversation_continued_20251002_141500.json
# Result: Original 10 + 5 new = 15 total turns

# 3. Continue again
python main.py --continue conversations/Fantasy_Tavern_Conversation_continued_20251002_141500.json --add-turns 5
# Creates: conversations/Fantasy_Tavern_Conversation_continued_20251002_142000.json
# Result: 15 + 5 = 20 total turns
```

### Important Notes

- **Original Preserved**: The original conversation file is never modified
- **State Restored**: Complete message history and speaker order preserved
- **Seamless**: The conversation continues naturally from where it left off
- **Combinable**: Can combine with `--interrupt-timeout` and `--interactive`

### Command Requirements

- `--continue` requires `--add-turns` (must specify how many turns to add)
- `--add-turns` requires `--continue` (can't be used alone)

---

## Viewing Conversations

View and explore saved conversations with multiple display modes.

### Overview

All conversations are saved as JSON files in `conversations/`. The viewer provides multiple ways to explore them.

### Basic Usage

```bash
# List all conversations
python view_conversation.py

# View specific conversation
python view_conversation.py 1                    # By number from list
python view_conversation.py conversations/my_chat.json  # By filename

# View most recent
python view_conversation.py --latest
```

### Display Modes

#### 1. List Mode (Default)

Shows all saved conversations with metadata:

```bash
python view_conversation.py
```

Output:
```
📚 Saved Conversations
================================================

1. Fantasy_Tavern_Conversation_20251002_134944.json
   Scenario: Fantasy Tavern Conversation
   Date: 2025-10-02 13:49:44
   Turns: 11
   Characters: Eldric, Mira

2. Fantasy_Tavern_Conversation_20251002_151839.json
   Scenario: Fantasy Tavern Conversation
   Date: 2025-10-02 15:18:39
   Turns: 5
   Characters: Eldric, Mira
```

#### 2. View Mode

Display entire conversation at once:

```bash
python view_conversation.py 1
```

Output:
```
================================================
CONVERSATION: Fantasy Tavern Conversation
================================================
Date: 2025-10-02 13:49:44
Characters: Eldric, Mira
Turns: 11
================================================

💬 Eldric: Hello there, friend. What brings you to this tavern tonight?

💬 Mira: Greetings, traveler. I'm just passing through...

[... full conversation ...]
```

#### 3. Interactive Mode ⭐

View conversation turn-by-turn (press Enter to continue):

```bash
python view_conversation.py 1 -i
# or
python view_conversation.py 1 --interactive
```

Output:
```
================================================
Turn 1/11
================================================

💬 Eldric: Hello there, friend. What brings you to this tavern tonight?

Press Enter to continue (or 'q' to quit)...
```

**Controls:**
- **Enter** - Show next turn
- **q** - Quit viewing

#### 4. Export to Markdown

Convert conversation to markdown file:

```bash
python view_conversation.py 1 --export
```

Creates `conversations/Fantasy_Tavern_Conversation_20251002_134944.md`:

```markdown
# Fantasy Tavern Conversation

**Date:** 2025-10-02 13:49:44
**Characters:** Eldric, Mira
**Turns:** 11

---

## Turn 1

**Eldric:** Hello there, friend. What brings you to this tavern tonight?

## Turn 2

**Mira:** Greetings, traveler. I'm just passing through...

[...]
```

### Advanced Options

```bash
# List with custom directory
python view_conversation.py --list conversations/

# View latest conversation interactively
python view_conversation.py --latest -i

# View and export
python view_conversation.py 1 --export
```

### Command Reference

```
usage: view_conversation.py [options] [conversation]

Options:
  -h, --help            Show help message
  -l, --list            List all conversations
  -i, --interactive     Interactive turn-by-turn mode
  -v, --view            View entire conversation
  --latest              View most recent conversation
  --export              Export to markdown

Arguments:
  conversation          Number from list or path to JSON file
```

### Use Cases

**Quick Review:**
```bash
python view_conversation.py --latest
```

**Detailed Analysis:**
```bash
python view_conversation.py 1 -i
```

**Share Conversation:**
```bash
python view_conversation.py 1 --export
```

---

## Configuration System

Flexible configuration through JSON and Markdown files.

### Configuration Files

#### app.json (Main Config)

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
    "api_key": "not-needed",
    "model": "my-model",
    "temperature": 0.8,
    "max_tokens": 200,
    "top_p": 0.95,
    "frequency_penalty": 0.0,
    "presence_penalty": 0.0
  },
  
  "conversation_config": {
    "max_turns": 10,
    "save_conversation": true,
    "output_dir": "conversations",
    "initial_message": "Hello!",
    "interrupt_timeout": 5
  }
}
```

#### world.md (Setting)

Describes the world, setting, and context:

```markdown
# Medieval Tavern Setting

You are in a cozy medieval tavern called "The Wandering Ale"...

## Rules
- Keep responses conversational and in-character
- Stay true to the medieval setting
```

#### character_a.md / character_b.md (Character Cards)

Defines character personality, background, and behavior:

```markdown
# Eldric the Storyteller

## Background
A traveling merchant with tales from distant lands...

## Personality
- Friendly and outgoing
- Loves sharing stories
- Curious about others

## Speaking Style
- Warm and welcoming
- Uses colorful descriptions
```

### Multiple Scenarios

Create different scenarios without changing code:

```bash
# Fantasy tavern
python main.py

# Philosophy debate
python main.py scenarios/debate/debate_config.json

# Your custom scenario
python main.py scenarios/my_scenario/config.json
```

### LLM Settings

#### Temperature
Controls randomness (0.0 = deterministic, 1.0 = very creative)
```json
"temperature": 0.8
```

#### Max Tokens
Maximum response length
```json
"max_tokens": 200
```

#### Penalties
Reduce repetition:
```json
"frequency_penalty": 0.4,
"presence_penalty": 0.3
```

### Conversation Settings

#### Max Turns
Number of exchanges:
```json
"max_turns": 10
```

#### Initial Message
Starting message (optional):
```json
"initial_message": "Hello there, friend."
```

#### Interrupt Timeout
SPACE interrupt window (seconds):
```json
"interrupt_timeout": 5
```

### Best Practices

1. **Keep character cards focused** - Clear personality, speaking style
2. **Add speaking guidelines** - Reduce repetition
3. **Adjust max_tokens** - 150-200 for natural conversation
4. **Set penalties** - frequency_penalty: 0.4, presence_penalty: 0.3
5. **Test scenarios** - Run with small max_turns first

---

## Tips & Tricks

### Reducing Repetition

Add to character cards:

```markdown
## Speaking Guidelines
- Keep responses brief (2-3 sentences)
- Vary sentence structure
- Avoid repeating the same phrases
- React naturally to the other character
```

### Better Conversations

```json
{
  "temperature": 0.85,
  "max_tokens": 150,
  "frequency_penalty": 0.4,
  "presence_penalty": 0.3
}
```

### Debugging

```bash
# Short test conversation
python main.py --interrupt-timeout 1  # Quick interrupts for testing

# Interactive mode for control
python main.py --interactive  # Manual control over each message
```

### Server-Friendly Settings

```json
{
  "interrupt_timeout": 10,    // More breathing room
  "max_tokens": 150,          // Shorter responses = faster
  "max_turns": 5              // Shorter conversations for testing
}
```

---

**Need more help?** Check out the [Usage Guide](USAGE.md) or [Architecture](ARCHITECTURE.md) documentation.
