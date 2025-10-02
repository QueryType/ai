# Interactive Interruption Feature - Implementation Complete

## ✅ Feature Implemented!

The interactive interruption feature has been successfully implemented in `main.py`.

## What's New

### 1. **SPACE Key Interruption**
During automatic mode, before each LLM call, the system waits for SPACE key with a configurable timeout.

```
🤖 [AUTO MODE]
[Turn 1/10] Character: Mira
⏸️  Press SPACE to interrupt (5s timeout)...
```

### 2. **Interactive Mode**
When SPACE is pressed, you enter interactive mode and can type the message manually:

```
🎮 [INTERACTIVE MODE ACTIVATED]

Enter message for Mira (or type 'auto' to resume automatic mode):
> Your custom message here
```

### 3. **Resume Auto Mode**
Type `auto` at any interactive prompt to resume automatic generation:

```
> auto

✅ Resuming automatic mode
```

### 4. **User Tracking**
All manually entered messages are marked with `"user_provided": true` in the saved JSON.

## New Command-Line Options

### `--interrupt-timeout SECONDS`
Set custom timeout for SPACE interrupt:

```bash
python main.py --interrupt-timeout 10    # 10 second window
python main.py --interrupt-timeout 3     # 3 second window
```

### `--interactive`
Start entirely in interactive mode (manual entry for all messages):

```bash
python main.py --interactive
```

## Configuration

Add to `app.json` under `conversation_config`:

```json
{
  "conversation_config": {
    "max_turns": 10,
    "save_conversation": true,
    "output_dir": "conversations",
    "initial_message": "Hello there!",
    "interrupt_timeout": 5
  }
}
```

## Complete Usage Examples

### Example 1: Auto Mode with Default Timeout (5s)
```bash
python main.py
```
- System generates messages automatically
- 5 second window to press SPACE before each turn
- Can interrupt any turn

### Example 2: Longer Timeout for Slower Reactions
```bash
python main.py --interrupt-timeout 10
```
- 10 second window to press SPACE
- More time to decide whether to interrupt
- Better for slower LLM servers (more breathing room)

### Example 3: Start in Interactive Mode
```bash
python main.py --interactive
```
- Prompts for every message manually
- Type `auto` at any time to resume automatic
- Full control from start

### Example 4: Continue with Custom Timeout
```bash
python main.py --continue conversations/chat.json --add-turns 5 --interrupt-timeout 8
```
- Continue existing conversation
- Add 5 more turns
- 8 second interrupt timeout

## Visual Indicators

| What You See | Meaning |
|--------------|---------|
| `🤖 [AUTO MODE]` | System is generating automatically |
| `⏸️ Press SPACE...` | You CAN press SPACE now! |
| `🎮 [INTERACTIVE MODE ACTIVATED]` | Waiting for your input |
| `> _` | Cursor ready for your message |
| `✅ Manual message added` | Your message was saved |
| `✅ Resuming automatic mode` | Back to auto-generation |

## Saved Conversation Format

Messages now include `user_provided` field:

```json
{
  "turn": 3,
  "character": "a",
  "name": "Eldric",
  "message": "I think we should explore the ancient ruins.",
  "user_provided": true
}
```

- `"user_provided": true` = You typed this message
- `"user_provided": false` = LLM generated this message

## Technical Implementation

### New Methods

1. **`wait_for_space_interrupt()`**
   - Uses `termios` and `tty` for raw terminal input
   - Non-blocking with `select.select()` for timeout
   - Cleanly restores terminal settings
   - Returns `True` if SPACE pressed, `False` on timeout

2. **`get_user_message(character)`**
   - Prompts for manual message input
   - Checks for "auto" command to resume
   - Returns tuple: `(message, should_resume_auto)`

3. **Enhanced `run_conversation()`**
   - Mode tracking (`auto_mode` flag)
   - Per-turn interrupt checking
   - Visual mode indicators
   - User-provided metadata tracking

### New Imports

```python
import sys
import select
import termios
import tty
```

These enable non-blocking keyboard input detection.

## Workflow

```
START
  ↓
🤖 AUTO MODE
  ↓
Show timeout prompt (5s)
  ↓
Wait for SPACE ─┬→ Timeout → Generate with LLM → Display → Next turn
                │
                └→ SPACE pressed
                      ↓
                   🎮 INTERACTIVE MODE
                      ↓
                   Prompt for message
                      ↓
                   ┌─────┴─────┐
                   │           │
              Type "auto"   Type message
                   │           │
                   │           └→ Save with user_provided=true
                   │              Display → Next turn
                   │
                   └→ Resume AUTO MODE → Next turn
```

## Benefits

✅ **Full Control**: Interrupt any turn at any time  
✅ **Flexible**: Switch between auto and manual on the fly  
✅ **Transparent**: User-provided messages clearly marked  
✅ **Server-Friendly**: Configurable breathing room for backend  
✅ **Non-Invasive**: Clean timeout-based UX  
✅ **Recoverable**: Type "auto" to resume generation  

## Testing

Try it now:

```bash
cd /Users/ninja/Documents/code/ai/chat2chat/dual-agent-chat
python main.py --interrupt-timeout 10
```

When you see `⏸️ Press SPACE to interrupt (10s timeout)...`, press SPACE and try it out!

## See Also

- [INTERRUPT_TIMEOUT.md](INTERRUPT_TIMEOUT.md) - Detailed timeout configuration
- [USAGE.md](USAGE.md) - General usage guide
- [README.md](../README.md) - Project overview
