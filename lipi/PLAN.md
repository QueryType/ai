# Lipi — Feature Plan

## 0. Hardening round (started 2026-07-11)

Fixes and small features from a code review. Each item is independent.

- [x] **P1 — shell timeout actually fires** (`tools/__init__.py: shell`). The stdout read
  loop blocks before `proc.wait(timeout=)` is reached, so silent hangs never time out
  (deadly in ralph loops). Read from a background thread, enforce a wall-clock deadline,
  kill the process group, return partial output + `[timed out]` marker.
- [x] **P2 — `/profile` re-detects context window** (`agent.py`, `harness.py`). Extract
  `Agent.switch_profile(name)` that rebuilds the client AND re-runs context window
  detection; today a switch keeps the old window and miscalibrates compaction.
- [x] **P3 — `python_repl` double-execution** (`tools/__init__.py`). Last line is exec'd
  then eval'd again → side effects run twice, second time outside the stdout redirect.
  Use `ast.parse`; split off a trailing `ast.Expr` so each statement runs exactly once.
- [x] **P4 — gate tool-output aging on context pressure** (`context/memory.py`,
  `agent.py`, `config.yaml`). Aging currently runs unconditionally and mutates history
  (and saved sessions) even at low usage. New config: `aging_start` (default 0.5) for
  stage-1 trim, `aging_stub` (default 0.7) for stage-2 stub; below `aging_start`, no aging.
- [x] **P5 — `/compact` command** (`harness.py`). Manual compaction trigger using the
  existing `compact()`, printing the context meter before/after.
- [x] **Bonus A — `/clear` re-injects project context** and resets `turn_count`.
- [x] **Bonus B — empty-turn retry nudge**: on an empty model turn, append a short user
  message ("your last response was empty…") instead of resending an identical prompt.

---

## 1. MCP Tool Support (stdio + streamable HTTP)

### Integration surface
Tool system is clean: `TOOL_FUNCTIONS` dict + `TOOL_SCHEMAS` list. MCP tools merge into both at startup. No changes to `_run_loop` or `_call_llm`.

### What to build

**MCP client layer** (`mcp/client.py`, ~300-400 lines):
- **stdio**: subprocess with JSON-RPC over stdin/stdout. `initialize` handshake → `tools/list` → `tools/call`.
- **Streamable HTTP**: HTTP POST + SSE. Same JSON-RPC protocol, different wire.
- Both transports share a common `MCPClient` interface.

**Schema translation**: MCP `inputSchema` → OpenAI function-calling `parameters`. Mostly 1:1 dict reshape.

**Config** in `config.yaml`:
```yaml
mcp_servers:
  filesystem:
    transport: stdio
    command: npx
    args: ["@modelcontextprotocol/server-filesystem", "/tmp"]
  remote-tools:
    transport: http
    url: http://localhost:3001/mcp
```

**Startup wiring**: at agent init, iterate MCP servers → connect → `tools/list` → convert schemas → merge into `TOOL_SCHEMAS`/`TOOL_FUNCTIONS`. Each MCP tool becomes a closure calling `tools/call` on its client.

**Lifecycle**: stdio servers need process start/kill. `MCPManager` class owns connections, cleans up on exit.

### Effort breakdown
| Piece | Effort |
|-------|--------|
| JSON-RPC framing | Small (~50 lines) |
| stdio transport | Medium |
| Streamable HTTP transport | Medium |
| Schema translation | Small |
| Config + startup | Small |
| Process lifecycle | Medium |
| Error handling | Medium |

### Decision: roll our own (no `mcp` SDK)
The official `mcp` Python SDK is async (`anyio`/`httpx`/`pydantic`) — too heavy for Lipi's plain-Python ethos. Roll own for stdio (simple), add `httpx` only for HTTP transport if needed.

**Total: ~400-500 new lines, zero changes to core agent loop.**

---

## 2. Agent Skills Support (agentskills.io standard) ✅ DONE

### What it is

Agent Skills is an open standard (originally from Anthropic, now cross-agent). A skill is a **folder with a `SKILL.md` file** — YAML frontmatter (name, description) + markdown instructions. Supported by Claude Code, Cursor, VS Code Copilot, Gemini CLI, OpenCode, etc.

```
.skills/code-review/
├── SKILL.md          # Required: frontmatter + instructions
├── scripts/          # Optional: executable code
├── references/       # Optional: extra docs loaded on demand
└── assets/           # Optional: templates, data files
```

### SKILL.md format

```markdown
---
name: code-review             # required, must match folder name, lowercase+hyphens
description: |                # required, max 1024 chars — tells the agent WHEN to use it
  Review code changes for bugs, security issues, and style.
  Use when asked to review a PR, diff, or code changes.
license: MIT                  # optional
compatibility: Requires git   # optional, max 500 chars
metadata:                     # optional, arbitrary key-value
  author: user
  version: "1.0"
allowed-tools: Bash Read      # optional, experimental — restrict tool access
---

## Instructions (markdown body)

Step-by-step instructions the agent follows when the skill activates.
Can reference bundled files: see [reference](references/REFERENCE.md)
Can tell agent to run scripts: `scripts/check.sh`
```

### How it works: progressive disclosure

1. **Discovery** — at startup, scan skill directories, load ONLY `name` + `description` from each SKILL.md frontmatter (~100 tokens per skill). Injected into system/user context so the LLM knows what's available.
2. **Activation** — when a user's task matches a skill description, the agent reads the full SKILL.md body into context (<5000 tokens recommended).
3. **Execution** — agent follows the instructions, optionally reading referenced files or running bundled scripts.

### What Lipi needs

**1. Skill discovery & registry** (`skills/registry.py`, ~120 lines):
- At startup, scan configured skill directories for `*/SKILL.md` files
- Parse YAML frontmatter only (name + description) — `yaml.safe_load` on the frontmatter block
- Build a registry: `{name: {description, path, loaded: False}}`
- Generate a skill summary block injected into context (like `context/packer.py` does for project context)

**2. Skill activation** (~60 lines):
- When the LLM decides to use a skill (or user types `/skill-name`), read the full SKILL.md body
- Inject it as a user message: `[Skill activated: {name}]\n{body}`
- Optionally load referenced files from `references/`, `scripts/`, `assets/` on demand
- Track which skills are active to avoid re-injection

**3. Skill directories config** in `config.yaml`:
```yaml
skill_dirs:
  - .skills              # project-local skills
  - ~/.lipi/skills       # user-global skills
```

**4. REPL integration** (~40 lines in `harness.py`):
- `/skills` command — list available skills with descriptions
- `/skill NAME` — manually activate a skill (force-load into context)
- Tab completion for skill names
- Skills also activate automatically via LLM matching (the LLM sees the skill index in context and can decide to use one)

**5. Tool filtering** (optional, ~30 lines):
- If `allowed-tools` is set, temporarily narrow `TOOL_SCHEMAS` during skill execution
- Context manager that swaps the schema list and restores after

**6. Skill index in context** (~30 lines):
- At session start, inject a compact block listing all discovered skills:
  ```
  [Available skills]
  • code-review — Review code changes for bugs, security issues, and style.
  • deploy-check — Verify deployment readiness and run pre-deploy checks.
  ```
- This goes via `context/packer.py` or a similar injection point
- ~100 tokens per skill, so 20 skills ≈ 2K tokens — fine for context budget

### What Lipi does NOT need (keep it light)

- No skill marketplace/registry server — just local folders
- No skill versioning/dependency resolution — KISS
- No sandboxing beyond existing shell/write guards — Lipi already has `_confirm` and `_confirm_write`
- No special "skill execution mode" — skills just inject instructions, the normal agent loop handles the rest

### Effort breakdown

| Piece | Effort | Lines |
|-------|--------|-------|
| YAML frontmatter parser | Small | ~30 |
| Skill directory scanner | Small | ~40 |
| Skill registry + index generation | Small | ~50 |
| Context injection (discovery) | Small | ~30 |
| Activation (full body load) | Small | ~60 |
| REPL commands (/skills, /skill) | Small | ~40 |
| Tool filtering (allowed-tools) | Small | ~30 |
| Config additions | Trivial | ~5 |

### Key design note

Skills are just **structured prompt injection** — the agent loop doesn't change at all. Discovery adds ~100 tokens per skill to context. Activation adds the full SKILL.md body as a user message. The LLM then follows those instructions using existing tools. This is the lightest possible integration.

**Total: ~280 new lines. Simpler than MCP. No new dependencies (just `yaml` which is already used).**
