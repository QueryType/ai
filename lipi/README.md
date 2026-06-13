```
  ██╗     ██╗ ██████╗  ██╗
  ██║     ██║ ██╔══██╗ ██║
  ██║     ██║ ██████╔╝ ██║
  ██║     ██║ ██╔═══╝  ██║
  ███████╗██║ ██║      ██║
  ╚══════╝╚═╝ ╚═╝      ╚═╝
  local agentic coding harness
```

A tight, hackable agentic loop for local LLMs. No framework — plain Python
you can read and modify in an afternoon. Point it at any OpenAI-compatible
server (llama-server, LM Studio, MLX) and get a tool-calling coding agent
with shell access, file editing, web search, vision, and more.

## Quick start

```bash
conda activate lipi
pip install -r requirements.txt

# Make sure your local LLM server is running
python harness.py
```

## How it works

```
You type → agent builds prompt → sends to local LLM →
LLM calls tools (shell, files, search, vision, DuckDB, ...) →
results fed back → loop until done → final answer printed
```

## File map

```
lipi/
├── harness.py              ← REPL entry point (run this)
├── agent.py                ← agentic loop: prompt → tool calls → loop
├── config.yaml             ← model profiles, limits, toggles
├── config.py               ← loads config.yaml, exports cfg + PROFILES
├── tools/
│   └── __init__.py         ← 12 tools + OpenAI-format schemas
├── context/
│   ├── packer.py           ← project overview builder
│   ├── init_md.py          ← .Lipi.md generator (/init command)
│   ├── memory.py           ← context compaction, aging, session save/load
│   └── tokens.py           ← local token estimator with auto-calibration
└── prompts/
    └── system.md           ← system prompt (cache-stable)
```

## Tools

| Tool | What it does |
|---|---|
| `shell` | Run bash, stream live output |
| `read_file` | Read any file (with optional line range) |
| `write_file` | Write/create a file |
| `patch_file` | Surgical text replacement (fuzzy whitespace matching) |
| `patch_lines` | Replace a line range by number (preferred for edits) |
| `insert_lines` | Insert content before a line number |
| `list_files` | Glob file listing, skips noise dirs |
| `web_search` | Tavily search with AI answer synthesis |
| `fetch_url` | Fetch URL → clean text via Tavily extract |
| `vision` | Analyse image via vision model |
| `python_repl` | Execute Python in-process |
| `duckdb_query` | SQL on local DuckDB database |

## Model profiles

Defined in `config.yaml`. Each profile specifies a server endpoint, model, context window, temperature, and max output tokens.

```yaml
profiles:
  coder:
    base_url: "http://192.168.1.4:7890/v1"
    model: "google/gemma-4-12b-qat"
    context_window: 65536       # optional — auto-detected from server
    temperature: 0.2
    max_tokens: 4096

  analyst:
    base_url: "http://192.168.1.4:7890/v1"
    model: "google/gemma-4-12b-qat"
    temperature: 0.1
    max_tokens: 8192
```

Switch profile:
- CLI: `python harness.py --profile analyst`
- In REPL: `/profile analyst`

The `context_window` field is optional. Lipi auto-detects it by querying the server (LM Studio `/api/v0/models`, llama.cpp `/slots`). Falls back to the YAML value, then to a conservative 32K default.

## Context management

Lipi actively manages the context window to prevent overflows:

- **Token estimator** — estimates token usage from message sizes, auto-calibrates against actual API-reported token counts over time
- **Tool output aging** — old tool results shrink in two stages: first trimmed to head+tail, then collapsed to a one-line stub
- **Budget-aware compaction** — when context hits 80%, older turns are summarized via the LLM. Keeps as many recent messages as the budget allows (not a fixed count)
- **Project context pinning** — the project overview injected at startup is never compacted away
- **Mid-turn protection** — if context exceeds 90% during a tool-call loop, the model is forced to wrap up. At 95%, the loop aborts
- **Context meter** — usage shown after every response; run `/ctx` for detailed stats

## Usage

```bash
# Interactive REPL in current project
python harness.py

# Single-shot task
python harness.py "write a pytest for utils.py"

# Resume a previous session
python harness.py --resume 20250606_143022

# Use heavy model, no streaming
python harness.py --profile analyst --no-stream

# List / clean sessions
python harness.py --sessions
python harness.py --clean-sessions 5    # keep last 5
```

## REPL commands

```
/help           show help
/init           generate/update .Lipi.md for this project
/profile NAME   switch model profile
/ctx            show context window usage
/sessions       list saved sessions
/resume ID      load a past session
/context        re-inject project context
/clear          clear history (keep system prompt)
/cd PATH        change working directory
/tools          list available tools
/clean [N]      delete saved sessions (keep last N)
/exit           quit (also: Ctrl-D)
```

## Project context file (.Lipi.md)

Run `/init` in the REPL to generate a `.Lipi.md` — a living context document for the project. It has two kinds of content:

**Generated mechanically** (refreshed every `/init`):
- Project structure (directory tree)
- Work in progress (git branch, uncommitted changes, commits ahead of main)
- Recent activity (last 10 commits)
- TODOs/FIXMEs (scanned from source files)

**LLM-generated or maintained**:
- **Description** — a short paragraph about the project, written by the LLM on first `/init` (falls back to a placeholder if the server is down — re-run `/init` later to fill it in)
- **Architecture** — patterns and structure the LLM discovers as it works
- **Conventions** — coding style and project conventions
- **Key decisions** — non-obvious design choices and their rationale
- **Notes** — anything else worth remembering across sessions

The LLM updates these sections organically as it works. Editable sections are preserved across `/init` runs — only mechanical sections are regenerated. The file is automatically loaded into context at session start.

## Adding a new tool

1. Write a Python function in `tools/__init__.py`
2. Add it to `TOOL_FUNCTIONS` dict
3. Add an OpenAI-format schema to `TOOL_SCHEMAS` list
4. Mention it in `prompts/system.md`

No framework registration, no decorators.

## Prefix caching

The system prompt (`prompts/system.md`) is loaded once at startup and never
modified. This lets llama-server cache it — after the first call, the system
prompt costs zero tokens to re-process.

Dynamic context (working directory, project tree) goes into a USER message
via `context/packer.py`, keeping the system prompt cache-stable.

## Server tips

For llama-server with agentic workloads:

```bash
llama-server \
  --model /path/to/model.gguf \
  --ctx-size 32768 \
  --parallel 2 \
  --batch-size 2048 \
  --cache-reuse 256 \
  --n-gpu-layers 999 \
  --host 0.0.0.0 --port 8080
```

`--cache-reuse 256` enables prefix caching.
