# Viewing Saved Conversations

All conversations are saved as JSON files in the `conversations/` directory.

## 📖 Quick Reference

### List All Conversations
```bash
python view_conversation.py
```
Shows all saved conversations with metadata.

### View Specific Conversation
```bash
# By number (from list)
python view_conversation.py 1

# By filename
python view_conversation.py conversations/Fantasy_Tavern_Conversation_20251002_134944.json

# View most recent
python view_conversation.py --latest
```
Displays the entire conversation at once.

### 🎮 Interactive Mode (Turn-by-Turn) ⭐ NEW!
```bash
# View by number, one turn at a time
python view_conversation.py 1 -i

# View specific file interactively
python view_conversation.py conversations/Fantasy_Tavern_Conversation_20251002_134944.json --interactive

# View latest interactively
python view_conversation.py --latest -i
```

**In interactive mode:**
- ✅ Displays one turn at a time
- ✅ Press any key to continue to the next turn
- ✅ Perfect for slowly reading through conversations
- ✅ Great for presentations or careful analysis
- ✅ Helps you focus on each exchange

**Example flow:**
```
[Turn 1] Eldric:
  Hello there, friend...

💬 Press any key to continue...  ← Press any key

[Turn 2] Mira:
  *Mira looks up with a smile*...

💬 Press any key to continue...  ← Press any key
```

### Export to Markdown
```bash
python view_conversation.py conversations/Fantasy_Tavern_Conversation_20251002_134944.json --md
```
Creates a `.md` file for easy sharing.

### Get Help
```bash
python view_conversation.py --help
```
Shows all available options.

## 🔧 Alternative Methods

### Using jq (Pretty JSON)
```bash
# View entire conversation
cat conversations/*.json | jq

# View just the messages
cat conversations/*.json | jq '.conversation[] | "\(.name): \(.message)"'

# View specific turn
cat conversations/*.json | jq '.conversation[5]'
```

### Using Python's json.tool
```bash
python -m json.tool conversations/Fantasy_Tavern_Conversation_20251002_134944.json
```

### Open in Editor
```bash
# VS Code
code conversations/Fantasy_Tavern_Conversation_20251002_134944.json

# Vim
vim conversations/Fantasy_Tavern_Conversation_20251002_134944.json

# Any text editor
open -a TextEdit conversations/Fantasy_Tavern_Conversation_20251002_134944.json
```

## 📝 Conversation Viewer Features

The `view_conversation.py` script provides:

✅ **Readable formatting** - Clean display with turn numbers  
✅ **Metadata display** - Shows scenario, characters, date  
✅ **List view** - Browse all saved conversations  
✅ **Quick access** - View by number or filename  
✅ **Interactive mode** - Read turn-by-turn with keypress continuation  
✅ **Markdown export** - Convert to .md format  
✅ **Latest view** - Quickly check most recent conversation  

## 📤 Export Formats

### Markdown Export
```bash
python view_conversation.py conversations/my_conversation.json --md
# Creates: my_conversation.md
```

The Markdown file includes:
- Scenario header
- Metadata (date, characters, turns)
- Formatted conversation with turn headers
- Easy to read in any text editor or Markdown viewer

## 💡 Tips

**Quick view latest conversation:**
```bash
python view_conversation.py --latest
```

**Browse and select:**
```bash
python view_conversation.py  # List all
python view_conversation.py 1  # View #1
```

**Read slowly (interactive mode):**
```bash
python view_conversation.py 1 -i  # Press any key after each turn
```

**Export for sharing:**
```bash
python view_conversation.py conversations/interesting_chat.json --md
# Share the .md file - it's human-readable!
```

**Search conversations:**
```bash
grep -l "specific phrase" conversations/*.json
```

**Count conversations:**
```bash
ls conversations/*.json | wc -l
```
