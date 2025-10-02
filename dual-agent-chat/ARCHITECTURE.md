# Architecture Diagram

## System Flow

```
┌─────────────────────────────────────────────────────────────┐
│                     DUAL AGENT CHAT                          │
│                                                              │
│  ┌────────────┐    ┌─────────────┐    ┌─────────────┐     │
│  │ app.json   │───▶│ Config      │    │   LLM       │     │
│  │            │    │ Loader      │    │   Client    │     │
│  │ - Settings │    │             │    │             │     │
│  │ - Paths    │    │ Loads:      │    │ - API calls │     │
│  └────────────┘    │ - World MD  │    │ - Retries   │     │
│                    │ - Char A MD │    │ - Timeout   │     │
│  ┌────────────┐    │ - Char B MD │    └─────────────┘     │
│  │ world.md   │───▶│             │           ▲              │
│  └────────────┘    └─────────────┘           │              │
│  ┌────────────┐           │                  │              │
│  │character_  │───────────┘                  │              │
│  │  a.md      │                              │              │
│  └────────────┘                              │              │
│  ┌────────────┐                              │              │
│  │character_  │───────────┐                  │              │
│  │  b.md      │           │                  │              │
│  └────────────┘           ▼                  │              │
│                    ┌─────────────┐           │              │
│                    │  Message    │───────────┘              │
│                    │  Manager    │                          │
│                    │             │                          │
│                    │ ┌─────────┐ │                          │
│                    │ │ Single  │ │                          │
│                    │ │ Message │ │                          │
│                    │ │  List   │ │                          │
│                    │ └─────────┘ │                          │
│                    │             │                          │
│                    │ - Build sys │                          │
│                    │   prompt    │                          │
│                    │ - Switch    │                          │
│                    │   roles     │                          │
│                    └─────────────┘                          │
│                           ▲                                 │
│                           │                                 │
│                    ┌─────────────┐                          │
│                    │    Main     │                          │
│                    │ Application │                          │
│                    │             │                          │
│                    │ - Turn loop │                          │
│                    │ - Logging   │                          │
│                    │ - Save JSON │                          │
│                    └─────────────┘                          │
│                           │                                 │
│                           ▼                                 │
│                    ┌─────────────┐                          │
│                    │conversations│                          │
│                    │   /*.json   │                          │
│                    └─────────────┘                          │
└─────────────────────────────────────────────────────────────┘
```

## Message Flow: Role Switching Example

### Turn 1: Character A (Eldric) speaks

```
System Prompt: [World Info] + [Eldric's Character Card]

Messages:
  ┌────────────────────────────────────┐
  │ role: "assistant"                  │
  │ content: "Hello there!"            │  ← Eldric's message
  └────────────────────────────────────┘

Sent to LLM → Gets response
```

### Turn 2: Character B (Mira) speaks

```
System Prompt: [World Info] + [Mira's Character Card]  ← CHANGED!

Messages (ROLES SWITCHED):
  ┌────────────────────────────────────┐
  │ role: "user"                       │  ← SWITCHED from "assistant"
  │ content: "Hello there!"            │  ← Eldric's message (now "user")
  └────────────────────────────────────┘
  ┌────────────────────────────────────┐
  │ role: "assistant"                  │  ← NEW message
  │ content: "Greetings to you."       │  ← Mira's response
  └────────────────────────────────────┘

Sent to LLM → Gets response
```

### Turn 3: Character A (Eldric) speaks again

```
System Prompt: [World Info] + [Eldric's Character Card]  ← CHANGED BACK!

Messages (ROLES SWITCHED BACK):
  ┌────────────────────────────────────┐
  │ role: "assistant"                  │  ← SWITCHED from "user"
  │ content: "Hello there!"            │  ← Eldric's 1st message
  └────────────────────────────────────┘
  ┌────────────────────────────────────┐
  │ role: "user"                       │  ← SWITCHED from "assistant"
  │ content: "Greetings to you."       │  ← Mira's message (now "user")
  └────────────────────────────────────┘
  ┌────────────────────────────────────┐
  │ role: "assistant"                  │  ← NEW message
  │ content: "Nice evening, isn't it?" │  ← Eldric's 2nd response
  └────────────────────────────────────┘

Sent to LLM → Gets response
```

## Key Insight: Always "Assistant"

Each character always sees themselves as the "assistant" (responder), and the other character's messages appear as "user" (prompts).

This is achieved by:
1. Switching system prompt to current speaker's character
2. Flipping all role labels when speaker changes
3. Maintaining single conversation history

Result: **50% memory savings** with perfect context maintenance! 🎯

## Component Responsibilities

| Component | Responsibility |
|-----------|----------------|
| `config_loader.py` | Load and validate all configuration and content files |
| `message_manager.py` | Manage single message list with role switching logic |
| `llm_client.py` | Handle API communication with retry/timeout logic |
| `main.py` | Orchestrate conversation flow and save results |

## Data Flow

```
Start
  │
  ├─▶ Load Config (JSON + Markdown files)
  │
  ├─▶ Initialize Message Manager
  │
  ├─▶ Initialize LLM Client
  │
  ├─▶ Optional: Add initial message
  │
  └─▶ Conversation Loop:
      │
      ├─▶ Get messages for current character
      │   └─▶ Build system prompt (world + character)
      │   └─▶ Switch roles if needed
      │
      ├─▶ Send to LLM API
      │
      ├─▶ Receive response
      │
      ├─▶ Add to conversation history
      │
      ├─▶ Switch to other character
      │
      └─▶ Repeat until max_turns
  │
  └─▶ Save conversation to JSON
  │
End
```

## Why This Design?

### Traditional Approach (2 lists):
```
Agent A's list: [system_a, msg1, msg2, msg3, ...]
Agent B's list: [system_b, msg1, msg2, msg3, ...]
```
Memory usage: **2x** the conversation history

### Our Approach (1 list):
```
Shared list: [msg1, msg2, msg3, ...]
System prompt: Built dynamically per character
Roles: Flipped dynamically per character
```
Memory usage: **1x** the conversation history ✅

### Benefits:
- 💾 **50% less memory**
- 🎯 **Same context for both**
- 🔄 **Automatic perspective switching**
- 🧠 **Natural conversation flow**
