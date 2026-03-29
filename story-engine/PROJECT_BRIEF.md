# Story Engine — Project Brief
> Generated from design session. Read this before starting any work.

---

## What We Are Building

An **agentic story/roleplay engine** built in Python using the **Strands Agents SDK**.  
It reads a structured markdown input file and autonomously writes narrative prose —  
a scene from a roleplay or adventure story — using a multi-agent pipeline.

It is inspired by the SillyTavern + KoboldCPP workflow for AI-assisted roleplay,  
but runs as a standalone Python application with no UI dependency.

---

## Core Design Decisions

| Decision | Choice | Reason |
|---|---|---|
| Agent architecture | **Option B — Multi-agent pipeline** | More powerful, better quality control |
| Model provider | **Model-agnostic** | Support OpenRouter, Anthropic, Ollama, Bedrock via Strands |
| Execution modes | **3 modes** | Autonomous, Interactive, Semi-interactive |
| Input format | **One `.md` file per scene** | Simple, repeatable, version-controllable |
| Player input style | **Free text `>`** | Keep it simple, KoboldCPP-style |
| Pause markers | **Inline in `[scene-beats]`** | Narrative-first, not config-first |
| Multi-scene | **Separate files per scene** | Avoids complexity, use a folder/playlist for arcs |

---

## Agent Topology (Option B)

```
┌─────────────────────────────────────────────────────────────┐
│                     ORCHESTRATOR AGENT                      │
│  - Parses input .md file                                    │
│  - Reads [meta] to determine execution mode                 │
│  - Manages beat iteration and pause logic                   │
│  - Routes to appropriate sub-agents                         │
│  - Assembles final output                                   │
└──────────┬──────────────┬──────────────┬────────────────────┘
           │              │              │
           ▼              ▼              ▼
  ┌────────────────┐  ┌──────────────┐  ┌──────────────────┐
  │ LORE INJECTOR  │  │   NARRATOR   │  │    EVALUATOR     │
  │    AGENT       │  │    AGENT     │  │     AGENT        │
  │                │  │              │  │                  │
  │ - Manages all  │  │ - Writes     │  │ - Checks beat    │
  │   lorebooks    │  │   prose for  │  │   completion     │
  │ - Keyword-     │  │   each beat  │  │ - Detects drift  │
  │   triggered    │  │ - Maintains  │  │ - Scores output  │
  │   injection    │  │   narrator   │  │ - Pass/retry     │
  │ - Character    │  │   voice and  │  │   decision       │
  │   card lookup  │  │   style      │  │                  │
  └────────────────┘  └──────────────┘  └──────────────────┘
```

### Agent Responsibilities

**OrchestratorAgent**
- Entry point for all three modes
- Parses the input `.md` file into structured data
- Iterates through `[scene-beats]` one by one
- Detects `[pause]` markers and fires Strands interrupts
- Calls LoreInjector before each beat to build context
- Calls Narrator to write prose
- Calls Evaluator to check quality
- Retries beat if Evaluator fails (up to N retries)
- Assembles all beats into final output file

**LoreInjectorAgent**
- Receives current beat text + full story context
- Scans for character trigger keywords
- Returns relevant character card snippets + world info entries
- Acts as the "ST World Info engine" equivalent
- Keeps injections token-efficient (no full dumps)

**NarratorAgent**
- Receives: system prompt + writing style + scene setup + scenario + lore injection + beat instruction
- Writes one beat of prose
- Maintains voice consistency across beats via conversation history
- Does NOT make plot decisions — follows the beat instruction

**EvaluatorAgent**
- Receives: beat instruction + prose output
- Checks: Did the beat actually happen? Is it coherent with prior beats? Does it match the writing style?
- Returns: `pass` | `retry` with brief reason
- In autonomous mode: triggers automatic retry
- In interactive/semi modes: surfaces feedback to user

---

## Three Execution Modes

### Mode 1: Autonomous
```
Parse input → for each beat:
    LoreInjector → Narrator → Evaluator
    if fail → retry (max 3) → next beat
→ save output
No human involvement. Runs to completion.
```

### Mode 2: Interactive
```
Parse input → for each beat:
    LoreInjector → Narrator → Evaluator
    → PAUSE → show output to human
    → human inputs ">" free text or approves
    → if redirect: inject human input, regenerate
    → if approve: next beat
→ save output
Pauses after EVERY beat.
```

### Mode 3: Semi-Interactive
```
Parse input → for each beat:
    LoreInjector → Narrator → Evaluator
    if beat has [pause] marker:
        → PAUSE → show output to human
        → human inputs ">" or approves
    else:
        → auto-continue if Evaluator passes
→ save output
Pauses only at [pause]-marked beats.
```

---

## How Strands SDK Maps to Our Needs

| Our Need | Strands Primitive |
|---|---|
| Agent with tools | `Agent(system_prompt=..., tools=[...])` |
| Custom tool functions | `@tool` decorator |
| Pause for human input | `event.interrupt()` via `BeforeToolCallEvent` hook |
| Resume after input | `agent(interrupt_responses=[...])` |
| Long story context | `SummarizingConversationManager` |
| Lifecycle hooks | `HookProvider` + `BeforeToolCallEvent` / `AfterModelInvocationEvent` |
| Multi-agent routing | `Agent-as-Tool` pattern (sub-agents as tools of orchestrator) |
| Model swap | `model=` param — swap Bedrock/Anthropic/OpenAI/Ollama |

---

## Model Provider Strategy

Use Strands' model-agnostic interface. Target providers in priority order:

1. **OpenRouter** (via LiteLLM or OpenAI-compatible endpoint) — for DeepSeek V3.2, Grok etc.
2. **Anthropic direct** — Claude Sonnet/Opus
3. **Ollama** — local models for dev/testing
4. **Amazon Bedrock** — production/enterprise path

Provider is set via environment variable or config, not hardcoded.

```python
# Example model swap — one line change
from strands.models import BedrockModel, AnthropicModel
from strands.models.openai import OpenAIModel  # for OpenRouter

model = OpenAIModel(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.environ["OPENROUTER_API_KEY"],
    model_id="deepseek/deepseek-v3.2"
)
```

---

## Key Technical References

- **Strands SDK repo**: https://github.com/strands-agents/sdk-python
- **Strands docs**: https://strandsagents.com
- **Strands samples**: https://github.com/strands-agents/samples
- **Strands interrupt docs**: https://strandsagents.com/docs/user-guide/concepts/interrupts/
- **Strands multi-agent**: Graph, Swarm, Agent-as-Tool patterns in SDK

---

## Project Folder Structure (Target)

```
story-engine/
├── PROJECT_BRIEF.md          ← this file
├── SCHEMA.md                 ← input file format spec
├── AGENT_DESIGN.md           ← detailed agent/tool map (to be created)
├── examples/
│   └── ashenveil_scene1.md   ← example input file
├── src/
│   ├── main.py               ← entry point, reads input, routes mode
│   ├── parser.py             ← parses .md input into structured data
│   ├── agents/
│   │   ├── orchestrator.py
│   │   ├── narrator.py
│   │   ├── lore_injector.py
│   │   └── evaluator.py
│   ├── tools/
│   │   ├── lore_tools.py
│   │   ├── narrative_tools.py
│   │   ├── eval_tools.py
│   │   └── io_tools.py
│   ├── models/
│   │   └── provider.py       ← model-agnostic provider factory
│   └── modes/
│       ├── autonomous.py
│       ├── interactive.py
│       └── semi_interactive.py
├── output/                   ← generated story output goes here
├── .env.example              ← API keys template
└── requirements.txt
```

---

## What Has NOT Been Decided Yet

- Exact tool signatures (inputs/outputs) — to be designed in AGENT_DESIGN.md
- Retry strategy for Evaluator failures (count, backoff)
- Output format details (headers, scene breaks, metadata)
- Whether Evaluator uses a separate/cheaper model
- Session persistence between runs (Strands SessionManager)

---

## First Task for Claude Code

```
Read PROJECT_BRIEF.md and SCHEMA.md.
Then create src/AGENT_DESIGN.md documenting:
1. All four agents with full responsibility descriptions
2. Every @tool function — name, inputs, outputs, which agent owns it
3. Three execution mode flowcharts as ASCII diagrams
4. How Strands interrupts wire to our pause system
5. Data flow between agents (what each passes to the next)
Do NOT write any Python code yet.
```
