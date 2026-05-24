# Story Engine — Multi-Character Chat App
# Project Brief for Claude Code
> Read this before starting any work.
> Also read SCHEMA.md and CHAT_SCHEMA.md for format specs.

---

## Context

This project builds a **multi-character autonomous chat** capability —
characters share a world, converse with each other, and the human can
take over any character at any time to steer the conversation.

---

## What We Are Building

A Python CLI application where:
- Multiple AI characters share a world and scenario
- They converse autonomously in a chat-style format
- A GM (Game Master) agent manages all character voices in Phase 1
- The human can take over any character at any time
- Human interventions are logged separately, invisible in the chat output
- Output is saved as a clean chat-style transcript

There exists a similar project called story-engine here: /Volumes/d/code/aiml/story-engine.
This is built upon strandsagents SDK for writing AI assisted stories. You can refer to it how the agents are built and how configurations are made, but do not take it as a guiding architecture since both use cases are different. 
Do NOT modify the existing story engine. This chat-engine is a parallel module /Volumes/d/code/aiml/chat-engine.
---

## Build Phases — Do ONE at a Time

### PHASE 1 — Single GM Agent (Build This First)
One agent plays ALL characters.
Orchestration is simple rule-based turn selection.
Human takeover is supported via CLI commands.
No per-character agents yet.

### PHASE 2 — LLM-Driven Turn Selection (Build After Phase 1 Works)
Use the model to choose who speaks next and write that character's
dialogue in one call.

### PHASE 3 — Per-Character Agents (Build After Phase 2 Works)
Each character becomes their own Strands agent.
Own system prompt, own card, own conversation history.
Orchestrator selects speaker, routes to that character's agent.

---

## Current Architecture

```
┌─────────────────────────────────────────────┐
│              CLI Entry Point                │
│  main_chat.py                               │
│  - reads input .md file                     │
│  - initialises chat session                 │
│  - manages the main chat loop               │
│  - handles human input detection            │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│       Rule Planner / Selector               │
│  orchestrator.py                            │
│  - selects next speaker in rules mode       │
│  - applies phase pacing bias                │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│              GM Agent                       │
│  gm_agent.py                                │
│  - Strands Agent                            │
│  - rules mode: writes one chosen speaker's  │
│    next line                                │
│  - llm mode: chooses next speaker and       │
│    writes that speaker's line in one call   │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│              Chat Logger                    │
│  chat_logger.py                             │
│  - appends turn to chat transcript          │
│  - logs human interventions separately      │
│  - saves both logs to output files          │
└─────────────────────────────────────────────┘
```

---

## Phase 1 Turn Selection Rules (Rule-Based)

These are applied in order. First matching rule wins.

```
Rule 1 — Direct Address
  If the last line of dialogue contains a character's name
  or a direct question → that character speaks next.

Rule 2 — Human Takeover
  If human has just spoken as a character → other characters
  react. Priority: character most likely to react to what was said.

Rule 3 — Conflict Escalation
  If the last exchange contained disagreement/tension →
  the character who was challenged speaks next.

Rule 4 — Silence / New Beat
  If no clear trigger → use round-robin through character list,
  skip characters who just spoke in last 2 turns.

Rule 5 — Fallback
  Character with lowest recent speaking count speaks next.
```

---

## Human Takeover System

### How It Works

Every N turns (configurable), the chat loop pauses and prompts:

```
──────────────────────────────────────────────────────
[Turn 8]
Aldric: "The ruins remember what the Conclave wants forgotten."
──────────────────────────────────────────────────────
> Press Enter to continue, or type a command:
```

Human options at the prompt:

| Input | Action |
|---|---|
| `Enter` (empty) | Auto-continue, GM picks next speaker |
| `[as Lyra] text` | Inject as Lyra's turn, logged as human intervention |
| `[as Aldric] text` | Inject as Aldric's turn, logged as human intervention |
| `[director] instruction` | Hidden OOC note to GM for next turn only |
| `/next Lyra` | Force Lyra to speak next (auto-generated) |
| `/pause` | Pause and keep prompting until Enter |
| `/stop` | End chat, save outputs |
| `/status` | Show turn count, speaking stats, last speaker |

### Logging

**Chat transcript** (clean output — what the chat looks like):
```
Lyra: "I don't trust him."
Aldric: "Wisdom, perhaps. Or fear."
Lyra: "It's not fear. It's pattern recognition."
Aldric: "Ah. And what pattern is that?"
```
Human-injected lines appear identical to GM-generated lines.
No markers. The chat is the chat.

**Run log** (separate file — application record):
```
[T001] SPEAKER: Lyra | GENERATOR: gm_agent | RULE: direct_address
[T002] SPEAKER: Aldric | GENERATOR: gm_agent | RULE: conflict_escalation
[T003] SPEAKER: Lyra | GENERATOR: human | INPUT: "[as Lyra] It's not fear..."
[T004] SPEAKER: Aldric | GENERATOR: gm_agent | RULE: direct_address
```

---

## Folder Structure

```
chat-engine/
├── CHAT_APP_BRIEF.md
├── CHAT_SCHEMA.md
├── examples/
│   └── ashenveil_chat1.md
├── src/
│   └── (Claude Code builds here)
├── output/
├── .env.example
└── requirements.txt
```
---

## GM Agent — Strands Implementation Notes

```python
from strands import Agent

# GM agent receives a fully assembled prompt per turn
# It does NOT maintain conversation history across turns
# (history is managed externally by ChatLogger and passed in full)

gm_agent = Agent(
    system_prompt=build_gm_system_prompt(world_info, all_character_cards),
    model=get_model_from_config(),  # model-agnostic factory
)

# Per-turn call in rules mode:
response = gm_agent(build_turn_prompt(
  chat_history=logger.get_history(),
  next_speaker=selected_speaker,
  speaker_card=character_cards[selected_speaker],
  director_note=pending_director_note,
))

# Per-turn call in llm mode:
response = gm_agent(build_selected_turn_prompt(
  chat_history=logger.get_history(),
  available_speakers=character_names,
  director_note=pending_director_note,
))
```

The GM system prompt structure:
```
You are the Game Master of [world name].
You write dialogue for multiple characters in a shared chat.
Each turn, you may be told which character speaks next,
or you may be asked to choose the next speaker from the available cast.
Write ONLY that character's dialogue — nothing else.
Format: [Character Name]: "dialogue here"
Stay true to each character's voice and card.
Never break character. Never add narration or stage directions.
[world info block]
[cast overview]
```

---

## Turn Prompt Structure (Per Turn)

```
CHAT HISTORY SO FAR:
[last N turns of transcript — configurable, default 20]

NEXT SPEAKER: Lyra Voss
LYRA'S CARD: [Lyra's character card]
TONE HINT: [optional — e.g. "she's suspicious, keep it clipped"]
DIRECTOR NOTE: [optional OOC human instruction, hidden from transcript]

Write Lyra's next line only.
```

---

## Output Format

### Chat Transcript (clean)
```markdown
# Ashenveil — The Ruins Encounter
*Session started: 2026-04-21*

---

Lyra: "You're going in there alone. That's either brave or stupid."
Aldric: "I've been called both. Neither has stopped me."
Lyra: "The Conclave has this place flagged. You know that."
Aldric: "Do they? And yet here you are as well."
Lyra: "I'm here because of you."
Aldric: "Then perhaps we have more in common than you think."

---
*Session ended: Turn 24 | Stopped by: user command*
```

### Run Log (application record)
```markdown
# Run Log — ashenveil_chat1
*Session: 2026-04-21T14:32:00*

[T001] SPEAKER: Lyra | GEN: gm | RULE: opening_turn | TOKENS: 142
[T002] SPEAKER: Aldric | GEN: gm | RULE: direct_address | TOKENS: 98
[T003] SPEAKER: Lyra | GEN: gm | RULE: conflict_escalation | TOKENS: 115
[T004] SPEAKER: Lyra | GEN: human | INPUT: "[as Lyra] I'm here because of you."
[T005] SPEAKER: Aldric | GEN: gm | RULE: direct_address | TOKENS: 87
[T006] SPEAKER: Aldric | GEN: gm | RULE: direct_address | TOKENS: 94

SESSION END | Total turns: 24 | Human interventions: 3 | Total tokens: 2847
```

---

## Configuration in Input File

See CHAT_SCHEMA.md for full format.
Key fields that drive Phase 1 behaviour:

```markdown
[chat-config]
max_turns: 30
pause_every: 5          # prompt human every N turns
history_window: 20      # how many turns to include in GM context
opening_speaker: Lyra   # who speaks first (or "auto")
```

---

## Model Provider

Reuse the model-agnostic factory from the story engine.
If that doesn't exist yet, create:

```python
# src/chat/models/provider.py
import os
from strands.models.openai import OpenAIModel
from strands.models.anthropic import AnthropicModel

def get_model():
    provider = os.environ.get("MODEL_PROVIDER", "openrouter")
    if provider == "openrouter":
        return OpenAIModel(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.environ["OPENROUTER_API_KEY"],
            model_id=os.environ.get("MODEL_ID", "deepseek/deepseek-v3.2")
        )
    elif provider == "anthropic":
        return AnthropicModel(
            model_id=os.environ.get("MODEL_ID", "claude-sonnet-4-6")
        )
    # add ollama, bedrock etc. as needed
```

---

## What Has NOT Been Decided Yet (Defer to Later Phases)

- Per-character agent isolation (Phase 3)
- LLM-driven turn selection prompt design (Phase 2)
- Dramatic flow monitor / stall detection (Phase 3)
- Session persistence / resume capability
- Web UI (out of scope for now)

---

## First Task for Claude Code

```
Read CHAT_APP_BRIEF.md and CHAT_SCHEMA.md.
Then implement Phase 1 only:

1. src/chat/parser.py
   - Parse the chat .md input format defined in CHAT_SCHEMA.md
   - Return a structured Python dict/dataclass
   - Write a quick test against examples/ashenveil_chat1.md

2. src/chat/chat_logger.py
   - ChatLogger class
   - append_turn(speaker, text, generator, rule)
   - get_history(n=20) → last N turns as formatted string
   - save_transcript(path) → clean chat output
   - save_runlog(path) → application log

3. src/chat/orchestrator.py
   - ChatOrchestrator class
   - select_next_speaker(chat_history, characters) → str
   - Implement the 5 rules from CHAT_APP_BRIEF.md in order
   - get_tone_hint() → optional string

4. src/chat/gm_agent.py
   - GMAgent class wrapping a Strands Agent
   - build_system_prompt(world_info, character_cards) → str
   - build_turn_prompt(history, speaker, card, tone, director_note) → str
   - generate(turn_prompt) → str (the dialogue line)

5. src/chat/main_chat.py
   - CLI entry point: python -m src.chat.main_chat examples/ashenveil_chat1.md
   - Main chat loop
   - Human input handling (all commands from CHAT_APP_BRIEF.md)
   - Wire everything together

Build in this order. Test each component before moving to the next.
Do not start Phase 2 work until Phase 1 runs end-to-end.
```
