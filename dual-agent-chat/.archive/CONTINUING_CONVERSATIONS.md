# Continuing Existing Conversations

This feature allows you to continue an existing conversation by adding more turns to it, while preserving the original conversation in a new file.

## 🎯 How It Works

1. **Load existing conversation** - Reads the conversation JSON file
2. **Restore conversation state** - Rebuilds the message history
3. **Create new file** - Clones the conversation to a new file with "_continued" suffix
4. **Continue conversation** - Adds N additional turns
5. **Save incrementally** - Each new turn is appended to the new file

## 📖 Usage

### Basic Continuation

```bash
# Continue a conversation with 5 more turns
python main.py --continue conversations/Fantasy_Tavern_Conversation_20251002_134944.json --add-turns 5
```

### With Custom Config

```bash
# Use a different config when continuing
python main.py my_config.json --continue conversations/my_chat.json --add-turns 10
```

## 🔍 Example Workflow

### Step 1: Check existing conversation
```bash
python view_conversation.py
```

Output:
```
1. Fantasy_Tavern_Conversation_20251002_134944.json
   Scenario: Fantasy Tavern Conversation
   Time: 20251002_134944
   Turns: 11
```

### Step 2: Continue the conversation
```bash
python main.py --continue conversations/Fantasy_Tavern_Conversation_20251002_134944.json --add-turns 5
```

Output:
```
📋 Configuration: app.json
🔄 Continuing from: conversations/Fantasy_Tavern_Conversation_20251002_134944.json
➕ Adding 5 turns

🚀 Initializing Dual Agent Chat System...
============================================================
✅ Configuration loaded successfully: Fantasy Tavern Conversation
...
✅ All components initialized

📂 Loading existing conversation: conversations/Fantasy_Tavern_Conversation_20251002_134944.json
✅ Loaded conversation with 11 existing turns
🔄 Restoring conversation state...
✅ Conversation state restored

📋 Cloning 11 existing turns to new file
💾 Conversation will be saved to: conversations/Fantasy_Tavern_Conversation_continued_20251002_150530.json

🔄 Continuing Conversation...
============================================================
📊 Existing turns: 11
➕ Adding: 5 more turns
👤 Next speaker: Mira
============================================================

[Turn 12/16] Mira is thinking...
💬 Mira: [response]

[Turn 13/16] Eldric is thinking...
💬 Eldric: [response]
...
```

### Step 3: View the new conversation
```bash
python view_conversation.py --latest
```

## 📋 New File Structure

When continuing, the new file includes additional metadata:

```json
{
  "scenario": "Fantasy Tavern Conversation",
  "original_timestamp": "20251002_134944",
  "continued_timestamp": "20251002_150530",
  "continued_from": "conversations/Fantasy_Tavern_Conversation_20251002_134944.json",
  "characters": {
    "a": "Eldric",
    "b": "Mira"
  },
  "conversation": [
    ... all original turns ...
    ... new turns appended ...
  ]
}
```

## ✅ Features

- **Original preserved** - The original conversation file is never modified
- **State restoration** - Conversation context is fully restored
- **Auto next speaker** - Determines who speaks next based on last turn
- **Incremental save** - Each new turn is saved immediately
- **Clear tracking** - New file includes reference to original
- **Turn numbering** - Continues turn numbers from original (11, 12, 13...)

## 🛡️ Safety Features

1. **No modification of original** - Original conversation file remains untouched
2. **New file creation** - Creates `*_continued_TIMESTAMP.json` 
3. **Validation** - Checks that conversation file is valid before proceeding
4. **Error handling** - Graceful failure if file not found or invalid

## 💡 Tips

### Adjust LLM settings when continuing
You can use a different config file to change temperature, max_tokens, etc.:

```bash
python main.py experimental_config.json --continue conversations/my_chat.json --add-turns 5
```

### Continue multiple times
You can continue a continued conversation:

```bash
# First continuation
python main.py --continue conversations/chat_20251002_134944.json --add-turns 5
# Creates: chat_continued_20251002_150530.json

# Second continuation (from the first continuation)
python main.py --continue conversations/chat_continued_20251002_150530.json --add-turns 3
# Creates: chat_continued_20251002_153015.json
```

### View conversation history
Use the viewer to see which conversations are continuations:

```bash
python view_conversation.py
```

## ⚠️ Requirements

- `--continue` requires `--add-turns` to be specified
- The conversation file must exist and be valid JSON
- The conversation must have at least one turn

## 🚫 Error Examples

```bash
# Missing --add-turns
python main.py --continue conversations/my_chat.json
# Error: --add-turns is required when using --continue

# Using --add-turns without --continue
python main.py --add-turns 5
# Error: --add-turns can only be used with --continue

# File not found
python main.py --continue conversations/nonexistent.json --add-turns 5
# Error: Conversation file not found
```

## 📊 Use Cases

1. **Explore different paths** - Continue from the same point multiple times
2. **Long conversations** - Split long conversations into manageable chunks
3. **A/B testing** - Try different settings on the same conversation start
4. **Story branching** - Create different endings from the same beginning
5. **Iterative refinement** - Keep adding to conversations until satisfied

## 🔧 Advanced Usage

### Continue with different characters
The characters are loaded from the original conversation, but you can adjust their behavior using a different config:

```bash
# Use config with different temperature/parameters
python main.py variant_config.json --continue conversations/my_chat.json --add-turns 5
```

### Batch continuation
```bash
# Continue multiple conversations
for conv in conversations/*.json; do
  python main.py --continue "$conv" --add-turns 3
done
```

## 📝 Notes

- The conversation state (message history and roles) is fully restored
- The next speaker is automatically determined from the last turn
- Turn numbers continue from where the original left off
- All new turns are saved incrementally to prevent data loss
- The original file is NEVER modified - you can always go back
