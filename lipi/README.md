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
├── cfg.py                  ← CLI to view/set/unset config values
├── tools/
│   └── __init__.py         ← 12 tools + OpenAI-format schemas
├── skills/
│   └── registry.py         ← skill discovery, activation, keyword matching
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
| `shell` | Run bash, stream live output (wall-clock timeout, kills hung commands) |
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

## Usage

```bash
# Interactive REPL in current project
python harness.py

# Single-shot task
python harness.py "write a pytest for utils.py"

# Single-shot from a file (avoids shell quoting issues)
python harness.py --prompt TASK.md

# Use heavy model, no streaming
python harness.py --profile analyst --no-stream

# Disable markdown rendering (plain text output)
python harness.py --no-render

# Show token/sec timing after each LLM call
python harness.py --timings

# Auto-approve file writes and dangerous commands (for autonomous loops)
python harness.py --auto-approve

# Resume a previous session
python harness.py --resume 20250606_143022

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
/compact        compact history now (summarize older turns)
/sessions       list saved sessions
/resume ID      load a past session
/context        re-inject project context
/clear          clear history (re-injects project context)
/cd PATH        change working directory
/tools          list available tools
/skills         list available agent skills
/skill NAME     activate a skill (inject into context)
/clean [N]      delete saved sessions (keep last N)
/exit           quit (also: Ctrl-D)
```

### Multiline input

- End a line with `\` to continue on the next line
- Start with `"""` to enter a block, close with `"""`

### Tab completion

Tab completes `/commands`, skill names (after `/skill `), and file paths.

## Agent Skills

Skills are structured prompt injections — markdown files that give the agent specialised knowledge or workflows without changing any code. Lipi follows the [agentskills.io](https://agentskills.io) standard.

### How skills work

Each skill lives in a directory with a `SKILL.md` file containing YAML frontmatter (name, description) and a markdown body:

```
my-skill/
  SKILL.md
```

```markdown
---
name: my-skill
description: One-line summary used for discovery and auto-activation.
---

# Skill body

Instructions injected into the agent's context when activated.
```

### Skill directories

Configured in `config.yaml` under `skill_dirs`:

```yaml
skill_dirs:
  - .skills            # per-project skills
  - ~/.lipi/skills     # global skills (available in every session)
```

Skills are discovered at startup. The count is printed on launch.

### Activation

- **Manual**: `/skill my-skill` in the REPL
- **Auto-activation**: if your message keywords overlap with a skill's description (2+ non-trivial word matches), the skill activates automatically. Common stop words are filtered out to prevent false matches.

### Installing third-party skills

Drop the skill folder into `~/.lipi/skills/` for global availability:

```bash
mkdir -p ~/.lipi/skills/frontend-design
# copy SKILL.md into it
```

### Built-in skills

Skills ship separately from the harness. Two example global skills:

- **ralph** — generates a `PROMPT.md` for autonomous Ralph loops (see below)
- **frontend-design** — guidance for distinctive UI/visual design

## Ralph loop (autonomous mode)

The Ralph loop is a technique for running Lipi autonomously in a bash loop. Each iteration starts a fresh single-shot session, re-reads the codebase, does one chunk of work, and exits. The loop repeats until a stop condition is met.

### Basic usage

Create a `PROMPT.md` describing the task, requirements, and loop rules, then run:

```bash
rm -f .done
while ! [ -f .done ]; do
  echo "=== $(date) ==="
  lipi --prompt PROMPT.md --auto-approve
  sleep 5
done
echo "Done! $(cat .done)"
```

The `--prompt` flag reads the task from a file, avoiding shell quoting issues with backticks and special characters.

### Generating a PROMPT.md

Use the built-in ralph skill in an interactive session:

```
/skill ralph
> Build a REST API for managing bookmarks
```

The skill interviews you about the task, writes a loop-ready `PROMPT.md`, and prints the exact bash command.

### Stop conditions

```bash
# Sentinel file (.done created by the agent when requirements are met)
while ! [ -f .done ]; do lipi --prompt PROMPT.md --auto-approve; sleep 5; done

# Max iterations
for i in $(seq 1 10); do lipi --prompt PROMPT.md --auto-approve; sleep 5; done

# Test suite passes
while :; do lipi --prompt PROMPT.md --auto-approve && pytest && break; sleep 5; done

# Manual (Ctrl-C to stop)
while :; do lipi --prompt PROMPT.md --auto-approve; sleep 5; done

# Without --auto-approve: you manually confirm each file write / dangerous command
while ! [ -f .done ]; do lipi --prompt PROMPT.md; sleep 5; done
```

### Auto-approve

By default, Lipi prompts for confirmation on file writes and dangerous shell commands (e.g. `rm -rf`, `sudo`). In an autonomous loop with nobody watching, this would hang. Use `--auto-approve` to skip these prompts — each skipped confirmation prints `[auto-approved]` so you can audit the log. Locked paths (`/etc`, `~/.ssh`, `~/.zshrc`, etc.) are always blocked regardless.

### Tips

- Edit `PROMPT.md` between iterations — it's re-read each cycle
- The `sleep 5` between iterations gives you time to read output or Ctrl-C
- Each iteration gets fresh project context, so the model sees changes from previous runs

## Model profiles

Defined in `config.yaml`. Each profile specifies a server endpoint, model, context window, temperature, and max output tokens.

```yaml
profiles:
  coder:
    base_url: "http://192.168.1.2:7890/v1"
    model: "google/gemma-4-12b-qat"
    context_window: 65536       # optional — auto-detected from server
    temperature: 0.2
    max_tokens: 4096

  analyst:
    base_url: "http://192.168.1.2:7890/v1"
    model: "google/gemma-4-12b-qat"
    temperature: 0.1
    max_tokens: 8192
```

Switch profile:
- CLI: `python harness.py --profile analyst`
- In REPL: `/profile analyst`
- Persistent: `python cfg.py set harness.profile analyst`

The `context_window` field is optional. Lipi auto-detects it by querying the server (LM Studio `/api/v0/models`, llama.cpp `/slots`). Falls back to the YAML value, then to a conservative 32K default.

## Context management

Lipi actively manages the context window to prevent overflows:

- **Token estimator** — estimates token usage from message sizes, auto-calibrates against actual API-reported token counts over time
- **Tool output aging** — under context pressure, old tool results shrink in two stages: trimmed to head+tail (above `aging_start`, default 50% usage), then collapsed to a one-line stub (above `aging_stub`, default 70%). Below `aging_start` nothing is touched, so the model keeps full tool outputs while there's room
- **Budget-aware compaction** — when context hits 80%, older turns are summarized via the LLM. Keeps as many recent messages as fit in 40% of the context window (not a fixed count). Trigger manually anytime with `/compact`
- **Project context pinning** — the project overview injected at startup is never compacted away
- **Mid-turn protection** — if context exceeds 90% during a tool-call loop, the model is forced to wrap up with short responses. At 95%, the loop aborts
- **Context meter** — visual usage bar shown after every response with percentage, estimated tokens, and color coding (green < 60%, yellow 60–80%, red > 80%). Run `/ctx` for detailed stats

## Display features

- **Live markdown rendering** — during streaming, completed lines are rendered with ANSI formatting (headings, code blocks, lists, inline code) immediately. Disable with `--no-render`
- **Streaming output** — token-by-token display as the model generates. Disable with `--no-stream`
- **Spinner** — animated braille dot spinner shown while the model is thinking or tools are executing
- **Tool call display** — when `show_tool_calls` is enabled (default), each tool invocation shows the tool name, arguments, and a preview of the result

## Session management

Sessions are auto-saved to `~/.harness/sessions/` as JSON after every agent turn. Each session is identified by a timestamp ID (e.g. `20250606_143022`).

- `/sessions` — list saved sessions with message count and description
- `/resume ID` — load a past session and continue where you left off
- `/clean [N]` — delete old sessions, optionally keeping the last N

File write confirmations: when the model writes to a file, you're prompted to confirm. Type `t` to trust the path for the rest of the session (avoids repeated prompts for the same directory).

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

## Config CLI

`cfg.py` lets you view and edit `config.yaml` from the command line.

```bash
python cfg.py                              # show all config values
python cfg.py get harness.profile          # get a single value
python cfg.py set harness.show_timings true  # set a value
python cfg.py unset harness.show_timings   # revert to default

# Update base_url and model across all profiles at once
python cfg.py profile --url http://localhost:8080/v1 --model my/model

# Update just one profile
python cfg.py profile --url http://localhost:8080/v1 --only coder
```

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
