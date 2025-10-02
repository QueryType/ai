# Interrupt Timeout Configuration

## Overview

The interrupt timeout controls how long the system waits for a SPACE keypress before automatically proceeding with the next turn. This feature provides:

1. **User control**: Time window to interrupt auto-generation
2. **Server relief**: Breathing room for the LLM backend between turns
3. **Flexibility**: Configurable per scenario or via command-line

## Default Value

**5 seconds** - Provides a good balance between responsiveness and giving users time to react.

## Configuration Methods

### Method 1: Configuration File

Add `interrupt_timeout` to `conversation_config` in your JSON config:

```json
{
  "conversation_config": {
    "max_turns": 10,
    "save_conversation": true,
    "output_dir": "conversations",
    "initial_message": "Hello there, friend.",
    "interrupt_timeout": 5
  }
}
```

### Method 2: Command-Line Override

Override the config file value with the `--interrupt-timeout` flag:

```bash
# Use 3 second timeout instead of config default
python main.py --interrupt-timeout 3

# Continue conversation with 10 second timeout
python main.py --continue conversations/chat.json --add-turns 5 --interrupt-timeout 10
```

### Method 3: Default (No Configuration)

If not specified in either config or command-line, defaults to **5 seconds**.

## Configuration Priority

1. **Command-line argument** (highest priority)
2. **Config file value**
3. **Default value** (5 seconds, lowest priority)

## Use Cases

### Fast-Paced Conversations
```bash
python main.py --interrupt-timeout 2
```
Shorter timeout for rapid back-and-forth, less server breathing room.

### Thoughtful Interactions
```bash
python main.py --interrupt-timeout 10
```
Longer timeout gives more time to decide on interruption, more server relief.

### High-Load Scenarios
```json
{
  "conversation_config": {
    "interrupt_timeout": 8
  }
}
```
Configure longer timeouts in scenarios that stress the LLM server.

## Benefits

1. **Backend Relief**: Each turn gets N seconds of breathing room for the LLM server
2. **User Experience**: Configurable based on user reaction time preferences
3. **Scenario Flexibility**: Different scenarios can have different pacing requirements
4. **System Stability**: Prevents overwhelming the backend with rapid-fire requests

## Visual Indicator

During auto-mode, you'll see:
```
⏸️  Press SPACE to interrupt (5s timeout)...
```

The timeout value shown matches your configuration.

## Technical Details

- **Implementation**: Uses `select.select()` with timeout on stdin
- **Platform**: Cross-platform (uses `termios`/`tty` on Unix-like systems)
- **Non-blocking**: Doesn't hang if SPACE isn't pressed
- **Precise timing**: Timeout is accurate to within milliseconds

## Examples

### Example 1: Quick Test Run
```bash
# Fast timeout for testing
python main.py scenarios/debate/debate_config.json --interrupt-timeout 1
```

### Example 2: Production Scenario
```bash
# Balanced timeout for real conversations
python main.py --interrupt-timeout 5
```

### Example 3: Continuation with Custom Timeout
```bash
# Continue with more thinking time
python main.py --continue conversations/deep_discussion.json \
  --add-turns 10 \
  --interrupt-timeout 8
```

## See Also

- [INTERACTIVE_MODE.md](INTERACTIVE_MODE.md) - Full interactive interruption guide
- [USAGE.md](USAGE.md) - General usage instructions
- [README.md](../README.md) - Project overview
