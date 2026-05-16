# Story Engine

An agentic narrative engine that writes roleplay and adventure fiction from structured scene files. Built with [Strands Agents SDK](https://strandsagents.com) — runs fully local with LM Studio, llama.cpp, or Ollama.

---

## How It Works

You write a scene file (`.md`) that describes the characters, world, writing style, and a list of plot beats. The engine runs a multi-agent pipeline that writes each beat as prose, evaluates it, and assembles the full scene output.

```
Your scene file (.md)
        │
        ▼
  OrchestratorAgent
  ┌─────────────────────────────────────────┐
  │  for each beat:                         │
  │    LoreInjector → build context         │
  │    Narrator     → write prose           │
  │    Evaluator    → quality gate          │
  │    if fail      → retry (max 3)         │
  └─────────────────────────────────────────┘
        │
        ▼
  output/your_scene.md
```

Three execution modes:
- **Autonomous** — runs to completion with no interruption
- **Interactive** — pauses after every beat for human steering
- **Semi-interactive** — pauses only at `[pause]`-marked beats

---

## Quick Start

```bash
conda activate strandsagents

# Configure your local model
cp .env.example .env
# Edit .env: set STORY_ENGINE_LOCAL_BASE_URL and model names

# Run the included example scene
python -m my_code examples/ashenveil_scene1.md

# Output lands in output/ashenveil_scene1.md
```

---

## Configuration

Edit `.env` — one file controls everything:

```env
STORY_ENGINE_PROVIDER=local
STORY_ENGINE_LOCAL_BASE_URL=http://192.168.1.5:7890/v1
STORY_ENGINE_NARRATOR_MODEL=your-model-name
STORY_ENGINE_EVALUATOR_MODEL=your-model-name
STORY_ENGINE_SUMMARISER_MODEL=your-model-name
STORY_ENGINE_ORCHESTRATOR_MODEL=your-model-name
```

Lore injection is pure Python and does not require a model setting.

Supported providers: **LM Studio**, **llama.cpp**, **Ollama**, **OpenRouter**, **Anthropic**, **AWS Bedrock**.

---

## Scene Files

A scene file is a single `.md` file with structured sections:

```markdown
[meta]
title: The Ruins of Ashenveil
mode: semi-interactive
output_file: output/ashenveil_scene1.md
output_format: prose
pov: third-person

[narrator-prompt]
You are the narrator of a dark fantasy world...

[writing-style]
Third person past tense. Literary fiction. Show don't tell.

[world-info]
Ashenveil is a crumbling empire on the edge of collapse...

[character-1]
name: Lyra Voss
role: player-character
triggers: Lyra, she, Voss
description: A deserter from the Conclave's enforcement arm...

[scene-beats]
1. Lyra watches Aldric approach the archway from the treeline.
2. She reveals herself. They speak. [pause]
3. Something stirs inside the ruins.
```

See [docs/USER_GUIDE.md](docs/USER_GUIDE.md) for full schema reference and examples.

---

## Features

- **Local-first** — works with any OpenAI-compatible backend
- **Resume support** — interrupted runs checkpoint each beat and resume where they left off
- **Keyword-triggered lore injection** — character cards injected only when relevant
- **Quality gate** — Evaluator checks beat coverage, style, and coherence; auto-retries on failure
- **Human steering** — redirect the narrator with free text, retry beats, or skip ahead
- **Model-agnostic** — swap provider and model in one config line
- **Scene Builder** — interactive CLI to generate a scene file from scratch via an 8-question interview
- **Story Importer** — convert any prose `.txt` into a scene file; LLM extracts characters, world-building, and beats automatically
- **Story Translator** — translate any large story file paragraph-by-paragraph with rolling context for name and tone continuity; supports any language and custom script/style hints

---

## Project Structure

```
story-engine/
├── my_code/
│   ├── agents/
│   │   ├── orchestrator.py     ← main loop, mode logic, checkpoint/resume
│   │   ├── narrator.py         ← writes prose per beat
│   │   ├── lore_injector.py    ← keyword-triggered context assembly
│   │   ├── evaluator.py        ← quality gate, pass/retry verdict
│   │   └── translator.py       ← TranslatorAgent factory for the translate tool
│   ├── tools/                  ← @tool functions for each agent
│   ├── models/
│   │   ├── provider.py         ← model factory (reads .env)
│   │   └── data_models.py      ← shared dataclasses
│   ├── importers/
│   │   ├── base.py             ← StoryAnalyser ABC, config, LLM helper, factory
│   │   ├── single_pass.py      ← single-call extraction (≤ 6k words)
│   │   └── chunked.py          ← multi-pass stub (not yet implemented)
│   ├── parser.py               ← scene file parser
│   ├── scene_builder.py        ← interactive scene builder CLI
│   ├── story_importer.py       ← prose → scene file importer CLI
│   ├── translate.py            ← story translation CLI
│   └── __main__.py             ← CLI entry point
├── examples/
│   └── ashenveil_scene1.md     ← working example scene
├── docs/
│   ├── USER_GUIDE.md           ← full scene file reference and engine docs
│   ├── SCENE_BUILDER.md        ← scene builder usage guide
│   ├── STORY_IMPORTER.md       ← story importer usage guide
│   └── TRANSLATOR.md           ← story translator usage guide
├── output/                     ← generated stories
├── .env.example                ← config template
└── requirements.txt
```

---

## Documentation

Full user guide: **[docs/USER_GUIDE.md](docs/USER_GUIDE.md)**

Agent architecture and workflow: **[docs/AGENT_WORKFLOW.md](docs/AGENT_WORKFLOW.md)**

Scene Builder guide: **[docs/SCENE_BUILDER.md](docs/SCENE_BUILDER.md)**

Story Importer guide: **[docs/STORY_IMPORTER.md](docs/STORY_IMPORTER.md)**

Story Translator guide: **[docs/TRANSLATOR.md](docs/TRANSLATOR.md)**

Covers: scene file reference, all section options, execution modes, interactive commands, output formats, stitching multi-scene stories, resume/checkpoints, and troubleshooting.

---

## Requirements

- Python 3.11+
- `strands-agents>=1.33.0`
- A local model server with an OpenAI-compatible API (LM Studio, llama.cpp, Ollama), or cloud API keys
- A model that supports tool/function calling (Qwen 2.5+, Llama 3.1+, Mistral function-calling variants)
