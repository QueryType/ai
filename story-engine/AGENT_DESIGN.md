# Story Engine — Agent Design Document
> Derived from PROJECT_BRIEF.md and SCHEMA.md. This is the implementation contract.

---

## Table of Contents

1. [Agent Inventory](#1-agent-inventory)
2. [Tool Registry](#2-tool-registry)
3. [Data Structures](#3-data-structures)
4. [Execution Mode Flowcharts](#4-execution-mode-flowcharts)
5. [Strands Interrupt Wiring](#5-strands-interrupt-wiring)
6. [Inter-Agent Data Flow](#6-inter-agent-data-flow)
7. [Model Provider Strategy](#7-model-provider-strategy)

---

## 1. Agent Inventory

### 1.1 OrchestratorAgent

**File:** `my_code/agents/orchestrator.py`
**Role:** Entry point. Owns the execution loop. Delegates all generation and evaluation work to sub-agents via the Agent-as-Tool pattern.

**Responsibilities:**
- Receives the path to the scene `.md` file
- Calls `parse_scene_file` to produce a `ParsedScene` object
- Reads `meta.mode` to select the execution strategy (`autonomous`, `interactive`, `semi-interactive`)
- Iterates through `beats` in order
- Before each beat: calls `call_lore_injector` to build lore context
- Tracks beat index and injects author note every `author_note.depth` beats
- Calls `call_narrator` with the assembled `NarratorContext`
- Calls `call_evaluator` with the beat instruction and prose output
- On evaluator `retry`: re-calls narrator (up to `MAX_RETRIES = 3`), with evaluator feedback appended to context
- On evaluator `pass` in semi-interactive mode: checks `beat.has_pause` — if true, calls `request_human_input`
- In interactive mode: calls `request_human_input` after every beat regardless of `[pause]`
- On human `redirect`: injects redirect text into narrator context, regenerates beat (counts as a retry)
- On human `skip`: discards beat output, advances to next beat
- On human `stop`: calls `save_final_output` with beats written so far and exits
- Accumulates prose per beat into `completed_beats`
- Calls `save_final_output` when all beats are done

**Strands agent config:**
```
Agent(
    system_prompt        = ORCHESTRATOR_SYSTEM_PROMPT,
    tools                = [parse_scene_file, call_lore_injector, call_narrator,
                            call_evaluator, save_beat, save_final_output,
                            request_human_input],
    model                = provider.get_model("orchestrator"),
    conversation_manager = NullConversationManager(),   # stateless router
    hooks                = [PauseHookProvider()],        # interrupt wiring (see §5)
)
```

---

### 1.2 LoreInjectorAgent

**File:** `my_code/agents/lore_injector.py`
**Role:** Context budget manager. Knows all character cards. Returns only what the current beat needs.

**Responsibilities:**
- Receives the current beat text and the full character card list
- Tokenizes the beat text and scans for `triggers` keyword matches (case-insensitive, whole-word)
- For each matched character, retrieves their card fields: `description`, `personality`, `backstory`, `speech_style`
- Formats matched cards into a compact lore block (no full dumps — fields are truncated to token budget)
- Always includes `[world-info]` (it is never keyword-gated)
- Returns a single formatted string ready to be inserted into the Narrator's prompt
- If no triggers fire, returns `world-info` only

**Strands agent config:**
```
Agent(
    system_prompt  = LORE_INJECTOR_SYSTEM_PROMPT,
    tools          = [scan_for_triggers, get_character_card, build_lore_block],
    model          = provider.get_model("lore_injector"),
    conversation_manager = NullConversationManager()   # stateless per beat
)
```

---

### 1.3 NarratorAgent

**File:** `my_code/agents/narrator.py`
**Role:** The writer. Produces prose for one beat at a time. Maintains voice continuity via conversation history.

**Responsibilities:**
- Receives a fully assembled `NarratorContext` struct on every call
- Uses a persistent `SummarizingConversationManager` to maintain prior beat context without unbounded token growth
- First call: initialises conversation with system prompt (narrator identity + writing style + world-info + scenario + writing-instructions)
- Each subsequent call: appends the beat instruction + lore injection + optional author note as a new user turn
- Writes prose for the beat; does NOT make plot decisions beyond what the beat instruction specifies
- Does NOT control the player-character's actions/decisions (per schema)
- Returns raw prose string for the beat

**Strands agent config:**
```
Agent(
    system_prompt  = assembled_narrator_system_prompt,  # built from ParsedScene
    tools          = [],                                 # no tools — pure generation
    model          = provider.get_model("narrator"),
    conversation_manager = SummarizingConversationManager(
        summary_ratio = 0.3,              # summarise 30% of oldest messages on overflow
        preserve_recent_messages = 10,    # always keep last 10 messages
    )
)
```

> **Note:** The NarratorAgent is constructed once per scene run, not per beat, so its conversation history persists across beats. It is the only agent with stateful conversation.

---

### 1.4 EvaluatorAgent

**File:** `my_code/agents/evaluator.py`
**Role:** Quality gate. Reads beat intent vs prose output and returns pass/retry with structured feedback.

**Responsibilities:**
- Receives: `beat_instruction`, `prose_output`, `writing_style`, `prior_beats_summary` (optional)
- Runs three checks via its tools:
  1. **Beat coverage** — did the required narrative event actually occur?
  2. **Style compliance** — does prose match the declared `[writing-style]`?
  3. **Coherence** — is prose consistent with what happened in prior beats?
- Returns an `EvalResult` with `result: "pass" | "retry"`, `reason`, per-check booleans, and a `score`
- Evaluator failures surface to Orchestrator; Orchestrator decides retry vs escalate
- In interactive/semi mode: retry reason is shown to the human before regeneration

**Strands agent config:**
```
Agent(
    system_prompt  = EVALUATOR_SYSTEM_PROMPT,
    tools          = [check_beat_coverage, check_style_compliance,
                      check_coherence, emit_eval_result],
    model          = provider.get_model("evaluator"),  # may be a cheaper model
    conversation_manager = NullConversationManager()   # stateless per invocation
)
```

---

## 2. Tool Registry

All tools use the Strands `@tool` decorator. Listed by owning agent.

---

### 2.1 OrchestratorAgent Tools

#### `parse_scene_file`
```
Owner:   OrchestratorAgent
File:    my_code/tools/io_tools.py

Input:
  file_path: str    — absolute or relative path to the .md scene file

Output:
  ParsedScene       — fully structured scene object (see §3.1)

Behaviour:
  Reads the .md file, splits on [section-name] markers,
  parses each section into its typed substructure.
  Validates required sections are present.
  Raises ParseError with section name on malformed input.
```

#### `call_lore_injector`
```
Owner:   OrchestratorAgent  (wraps LoreInjectorAgent as a tool)
File:    my_code/tools/lore_tools.py

Input:
  beat_text:    str        — full text of the current beat instruction
  beat_index:   int        — 0-based index of current beat
  characters:   list[str]  — serialised character card list (JSON)
  world_info:   str        — global world-info content

Output:
  lore_context: str        — formatted lore block ready for Narrator injection

Behaviour:
  Instantiates (or reuses) the LoreInjectorAgent.
  Passes inputs. Returns the agent's text response.
```

#### `call_narrator`
```
Owner:   OrchestratorAgent  (wraps NarratorAgent as a tool)
File:    my_code/tools/narrative_tools.py

Input:
  narrator_context: str   — serialised NarratorContext (see §3.2)

Output:
  prose: str              — written prose for this beat

Behaviour:
  Calls the persistent NarratorAgent with the assembled context.
  NarratorAgent's conversation history is maintained between calls.
  Returns raw prose string.
```

#### `call_evaluator`
```
Owner:   OrchestratorAgent  (wraps EvaluatorAgent as a tool)
File:    my_code/tools/eval_tools.py

Input:
  beat_instruction:   str   — original beat text from [scene-beats]
  prose_output:       str   — prose written by NarratorAgent
  writing_style:      str   — [writing-style] section content
  prior_summary:      str   — optional summary of prior beats (may be empty)

Output:
  EvalResult: str           — serialised EvalResult JSON (see §3.4)

Behaviour:
  Calls the EvaluatorAgent. Returns its structured verdict.
```

#### `save_beat`
```
Owner:   OrchestratorAgent
File:    my_code/tools/io_tools.py

Input:
  beat_index:  int
  prose:       str

Output:
  None

Behaviour:
  Appends the beat prose to the in-memory completed_beats list.
  Does not write to disk. (Final write happens in save_final_output.)
```

#### `save_final_output`
```
Owner:   OrchestratorAgent
File:    my_code/tools/io_tools.py

Input:
  completed_beats:  list[str]   — prose strings in beat order
  meta:             str         — serialised Meta object (title, format, pov, etc.)
  output_file:      str         — output path from [meta]

Output:
  file_path: str    — path to written output file

Behaviour:
  Assembles beats with scene headers.
  Writes formatted markdown to output_file.
  Applies output_format formatting (prose / adventure / script).
  Returns the path on success.
```

#### `request_human_input`
```
Owner:   OrchestratorAgent
File:    my_code/tools/io_tools.py

Input:
  beat_index:    int
  beat_total:    int
  prose_output:  str

Output:
  HumanInput     — serialised HumanInput object (see §3.5)

Behaviour:
  Displays beat index, separator, and prose to stdout.
  Prompts: "> Type a direction to redirect, or press Enter to continue:"
  Parses input into HumanInput struct:
    - empty / Enter    → action: "continue"
    - "> /skip"        → action: "skip"
    - "> /stop"        → action: "stop"
    - "> /retry"       → action: "retry"
    - any other text   → action: "redirect", text: <input>
  In Strands: this tool fires a BeforeToolCallEvent interrupt
  (see §5 for interrupt wiring).
```

---

### 2.2 LoreInjectorAgent Tools

#### `scan_for_triggers`
```
Owner:   LoreInjectorAgent
File:    my_code/tools/lore_tools.py

Input:
  beat_text:    str
  characters:   list[CharacterCard]

Output:
  matched_names: list[str]   — names of characters whose triggers fired

Behaviour:
  For each character, checks if any trigger keyword appears in
  beat_text (case-insensitive, whole-word boundary match).
  Returns list of matched character names in card order.
```

#### `get_character_card`
```
Owner:   LoreInjectorAgent
File:    my_code/tools/lore_tools.py

Input:
  character_name: str
  characters:     list[CharacterCard]

Output:
  card_content: str   — formatted card fields as a compact string block

Behaviour:
  Looks up character by name.
  Formats: name, role, description, personality, backstory, speech_style.
  Enforces a per-card token budget (target: ~150 words).
  Omits backstory if it would exceed budget.
```

#### `build_lore_block`
```
Owner:   LoreInjectorAgent
File:    my_code/tools/lore_tools.py

Input:
  world_info:      str
  matched_cards:   list[str]   — pre-formatted card strings

Output:
  lore_block: str   — single formatted injection string

Behaviour:
  Combines world-info (always) + matched character cards.
  Adds section headers: "## World" and "## Characters in Scene".
  Returns complete lore context ready for Narrator prompt insertion.
```

---

### 2.3 NarratorAgent Tools

> The NarratorAgent carries **no tools** — it is a pure generation agent.
> It receives context via its conversation history and returns prose directly.
> Tools are not needed because the Narrator's job is to write, not to query.

The `call_narrator` tool on the Orchestrator side handles all context assembly
before invoking the agent.

---

### 2.4 EvaluatorAgent Tools

#### `check_beat_coverage`
```
Owner:   EvaluatorAgent
File:    my_code/tools/eval_tools.py

Input:
  beat_instruction:  str
  prose_output:      str

Output:
  covered:  bool
  reason:   str    — brief explanation if false

Behaviour:
  Prompts the model to determine whether the core narrative event
  described in beat_instruction is present in prose_output.
  Returns true if the event occurred, false with explanation if not.
```

#### `check_style_compliance`
```
Owner:   EvaluatorAgent
File:    my_code/tools/eval_tools.py

Input:
  prose_output:   str
  writing_style:  str

Output:
  compliant:  bool
  issues:     list[str]   — specific violations if non-compliant

Behaviour:
  Checks prose against the [writing-style] directives.
  Common checks: POV consistency, tense, show-don't-tell,
  dialogue formatting, sentence variety.
  Returns list of issues (empty = pass).
```

#### `check_coherence`
```
Owner:   EvaluatorAgent
File:    my_code/tools/eval_tools.py

Input:
  prose_output:      str
  prior_summary:     str   — summary of prior beats (may be empty for beat 0)

Output:
  coherent:   bool
  reason:     str

Behaviour:
  Checks that prose does not contradict established facts from
  prior beats (character positions, established facts, tone).
  Skipped (auto-pass) if prior_summary is empty (first beat).
```

#### `emit_eval_result`
```
Owner:   EvaluatorAgent
File:    my_code/tools/eval_tools.py

Input:
  beat_coverage:   bool
  style_compliant: bool
  coherent:        bool
  issues:          list[str]

Output:
  EvalResult (serialised JSON)   — see §3.4

Behaviour:
  Aggregates the three check results.
  result = "pass" if all three are true, else "retry".
  score = sum of passing checks / 3.
  reason = joined issue strings or "All checks passed."
  Returns the final EvalResult.
```

---

## 3. Data Structures

These are Python dataclasses (or TypedDicts). Defined in `my_code/models/`.

### 3.1 `ParsedScene`
```
@dataclass
class ParsedScene:
    meta:                 Meta
    narrator_prompt:      str
    writing_style:        str
    author_note:          AuthorNote | None
    world_info:           str
    characters:           list[CharacterCard]
    scene_setup:          SceneSetup
    scenario:             str
    beats:                list[Beat]
    writing_instructions: str | None
```

### `Meta`
```
@dataclass
class Meta:
    title:          str
    version:        str             # default "1.0"
    mode:           str             # "autonomous" | "interactive" | "semi-interactive"
    pause_at:       str             # "beat" (default)
    output_file:    str
    output_format:  str             # "prose" | "adventure" | "script"
    pov:            str             # "third-person" | "first-person" | "second-person"
    target_length:  int             # default 1500
    language:       str             # default "en"
    nsfw:           bool            # default False
```

### `AuthorNote`
```
@dataclass
class AuthorNote:
    depth:    int    # inject every N beats
    content:  str
```

### `CharacterCard`
```
@dataclass
class CharacterCard:
    name:         str
    role:         str       # "player-character" | "npc" | "antagonist" | "neutral"
    triggers:     list[str]
    description:  str
    personality:  str
    backstory:    str | None
    speech_style: str | None
```

### `SceneSetup`
```
@dataclass
class SceneSetup:
    location:    str | None
    time:        str | None
    atmosphere:  str | None
```

### `Beat`
```
@dataclass
class Beat:
    index:      int      # 1-based, matches numbering in [scene-beats]
    text:       str      # beat instruction text (without [pause] marker)
    has_pause:  bool     # True if [pause] appeared in this beat's text
```

---

### 3.2 `NarratorContext`
Assembled by Orchestrator before each `call_narrator` invocation.
```
@dataclass
class NarratorContext:
    beat_instruction:     str
    lore_context:         str       # from LoreInjectorAgent
    author_note:          str | None
    beat_index:           int       # 1-based
    beat_total:           int
    redirect_instruction: str | None  # from human input on retry/redirect
```

> The static scene context (narrator_prompt, writing_style, world_info, scenario,
> scene_setup, writing_instructions) is baked into the NarratorAgent's system
> prompt at construction time — it does not travel with every NarratorContext.

---

### 3.3 `LoreContext`
Output of `build_lore_block`.
```
@dataclass
class LoreContext:
    world_info:       str
    character_cards:  list[str]   # pre-formatted strings per matched character
    full_block:       str         # assembled injection string
    triggered_names:  list[str]   # names of characters that matched
```

---

### 3.4 `EvalResult`
```
@dataclass
class EvalResult:
    result:          str        # "pass" | "retry"
    score:           float      # 0.0 – 1.0  (passing checks / 3)
    reason:          str        # human-readable summary
    beat_coverage:   bool
    style_compliant: bool
    coherent:        bool
    issues:          list[str]  # specific failure descriptions
```

---

### 3.5 `HumanInput`
```
@dataclass
class HumanInput:
    action:  str        # "continue" | "redirect" | "skip" | "stop" | "retry"
    text:    str | None # populated only for action="redirect"
```

---

## 4. Execution Mode Flowcharts

### 4.1 Mode 1: Autonomous

```
┌─────────────────────────────────────────────────┐
│  main.py: load .md file, call OrchestratorAgent  │
└───────────────────────┬─────────────────────────┘
                        │
                        ▼
               parse_scene_file()
                        │
                        ▼
            ┌───────────────────────┐
            │   for beat in beats   │◄─────────────────────────┐
            └───────────┬───────────┘                          │
                        │                                      │
                        ▼                                      │
             call_lore_injector()                              │
                        │                                      │
                        ▼                                      │
    inject author_note? (beat_index % depth == 0)             │
                        │                                      │
                        ▼                                      │
               call_narrator()                                 │
                        │                                      │
                        ▼                                      │
               call_evaluator()                                │
                        │                                      │
              ┌─────────┴──────────┐                          │
              │                    │                          │
           "pass"               "retry"                       │
              │                    │                          │
              │          retry_count < MAX_RETRIES?           │
              │                 │         │                   │
              │               yes         no                  │
              │                 │         │                   │
              │       append evaluator    │                   │
              │       reason to context   │                   │
              │       call_narrator()     │                   │
              │       call_evaluator()    │                   │
              │                 └────────►│                   │
              │                      log max retries hit      │
              │                           │                   │
              ▼                           ▼                   │
          save_beat()               save_beat()               │
         (prose output)            (best attempt)             │
              │                           │                   │
              └─────────┬─────────────────┘                   │
                        │                                     │
                   more beats? ───────────────────────────────┘
                        │
                     no more
                        │
                        ▼
               save_final_output()
                        │
                        ▼
                    [DONE]
```

---

### 4.2 Mode 2: Interactive

```
┌─────────────────────────────────────────────────┐
│  main.py: load .md file, call OrchestratorAgent  │
└───────────────────────┬─────────────────────────┘
                        │
                        ▼
               parse_scene_file()
                        │
                        ▼
            ┌───────────────────────┐
            │   for beat in beats   │◄──────────────────────────────────┐
            └───────────┬───────────┘                                   │
                        │                                               │
                        ▼                                               │
             call_lore_injector()                                       │
                        │                                               │
                        ▼                                               │
    inject author_note? (beat_index % depth == 0)                      │
                        │                                               │
                        ▼                                               │
               call_narrator()                                          │
                        │                                               │
                        ▼                                               │
               call_evaluator()                                         │
                        │                                               │
              ┌─────────┴──────────┐                                   │
              │                    │                                   │
           "pass"               "retry" ──── retry < MAX ────┐         │
              │                                              │         │
              │                                   append reason,       │
              │                                   call_narrator()       │
              │                                   call_evaluator()      │
              │                                              │         │
              │                                       max retries?      │
              │                                       (log + continue)  │
              │                                              │         │
              └─────────────────────┬────────────────────────┘         │
                                    │                                   │
                                    ▼                                   │
                       [INTERRUPT] request_human_input()               │
                       show prose to human, prompt for ">"             │
                                    │                                   │
               ┌────────────────────┼───────────────────────────┐      │
               │                    │                           │      │
          "continue"           "redirect"              "skip"  "stop" "retry"
               │                    │                    │       │      │
               │         append redirect text            │   save_final │
               │         as new instruction              │   _output()  │
               │         call_narrator()                 │       │      │
               │         call_evaluator()                │    [DONE]    │
               │         → loop back to interrupt ───────►             │
               │                                         │              │
               ▼                                         ▼              │
           save_beat()                             skip beat           │
               │                                         │              │
               └──────────────────┬──────────────────────┘              │
                                  │                                     │
                             more beats? ────────────────────────────────┘
                                  │
                               no more
                                  │
                                  ▼
                         save_final_output()
                                  │
                                  ▼
                              [DONE]
```

---

### 4.3 Mode 3: Semi-Interactive

```
┌─────────────────────────────────────────────────┐
│  main.py: load .md file, call OrchestratorAgent  │
└───────────────────────┬─────────────────────────┘
                        │
                        ▼
               parse_scene_file()
                        │
                        ▼
            ┌───────────────────────┐
            │   for beat in beats   │◄──────────────────────────────────┐
            └───────────┬───────────┘                                   │
                        │                                               │
                        ▼                                               │
             call_lore_injector()                                       │
                        │                                               │
                        ▼                                               │
    inject author_note? (beat_index % depth == 0)                      │
                        │                                               │
                        ▼                                               │
               call_narrator()                                          │
                        │                                               │
                        ▼                                               │
               call_evaluator()                                         │
                        │                                               │
              ┌─────────┴──────────┐                                   │
              │                    │                                   │
           "pass"               "retry" ──── retry < MAX ────┐         │
              │                                              │         │
              │                                   append reason,       │
              │                                   call_narrator()       │
              │                                   call_evaluator()      │
              │                                              │         │
              │                                       max retries?      │
              │                                       (log + continue)  │
              │                                              │         │
              └─────────────────────┬────────────────────────┘         │
                                    │                                   │
                              beat.has_pause?                           │
                          ┌─────────┴──────────┐                       │
                         yes                   no                      │
                          │                    │                       │
                          ▼                    ▼                       │
         [INTERRUPT] request_human_input()  save_beat()               │
         show prose, prompt for ">"             │                      │
                          │                    │                      │
      ┌───────────────────┼──────────────┐     │                      │
      │                   │              │     │                      │
 "continue"          "redirect"     "skip" "stop" "retry"             │
      │                   │              │     │      │               │
      │         inject redirect          │  save_final│               │
      │         call_narrator()          │  _output() │               │
      │         call_evaluator()         │     │      │               │
      │         re-interrupt ────────────►  [DONE]    │               │
      │                                  │         regenerate         │
      ▼                                  ▼         (no new input)     │
  save_beat()                       skip beat           │             │
      │                                  │              │             │
      └──────────────────┬───────────────┘──────────────┘             │
                         │                                            │
                    more beats? ─────────────────────────────────────┘
                         │
                      no more
                         │
                         ▼
                save_final_output()
                         │
                         ▼
                     [DONE]
```

---

## 5. Strands Interrupt Wiring

### How Interrupts Work in Strands

Strands provides `BeforeToolCallEvent` hooks via its `HookProvider` mechanism.
An interrupt suspends the agent's execution loop before a tool fires, allowing
external code to inspect and optionally block the call.

```python
# Verified against strands-agents 1.33.0
from strands.hooks import HookProvider, HookRegistry, BeforeToolCallEvent

class PauseHookProvider(HookProvider):
    def register_hooks(self, registry: HookRegistry, **kwargs) -> None:
        registry.add_callback(BeforeToolCallEvent, self.maybe_pause)

    def maybe_pause(self, event: BeforeToolCallEvent):
        if event.tool_use.get("name") == "request_human_input":
            # Strands suspends here — we read stdin and resume
            event.interrupt(name="human_pause")

# Wired to agent via: Agent(hooks=[PauseHookProvider()], ...)
```

### Our Wiring

The `request_human_input` tool is the sole interrupt surface in the engine.

```
OrchestratorAgent calls request_human_input()
         │
         ▼
BeforeToolCallEvent fires
         │
         ▼
PauseHookProvider.maybe_pause() intercepts
         │
         ▼
Print prose output to stdout
Prompt human: "> ..."
Read stdin
         │
         ▼
Parse HumanInput struct
         │
         ├── action = "continue" → resume, tool returns HumanInput
         ├── action = "redirect" → resume, tool returns HumanInput with text
         ├── action = "skip"     → resume, tool returns HumanInput
         ├── action = "stop"     → resume, tool returns HumanInput
         └── action = "retry"    → resume, tool returns HumanInput
         │
         ▼
OrchestratorAgent reads HumanInput.action and routes accordingly
```

### Interrupt Scoping by Mode

| Mode | When interrupt fires | Condition |
|---|---|---|
| `autonomous` | Never | `request_human_input` is never called |
| `interactive` | After every beat | Unconditionally after `call_evaluator` resolves |
| `semi-interactive` | After selected beats | Only when `beat.has_pause == True` |

### Resume with Redirect

When `action = "redirect"`, the Orchestrator does **not** use `agent(interrupt_responses=[...])`.
Instead it appends the redirect text to the `NarratorContext.redirect_instruction` field
and calls `call_narrator` again directly. This avoids Strands resume complexity
while keeping the redirect injection clean and auditable.

---

## 6. Inter-Agent Data Flow

### Per-Beat Data Flow

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  ORCHESTRATOR                                                                 │
│                                                                               │
│  ParsedScene ──────────────────────────────────────────────────────────────► │
│  beats[i].text ──────────► call_lore_injector()                              │
│                                    │                                          │
│                                    │ beat_text, characters, world_info        │
│                                    ▼                                          │
│                          ┌──────────────────────┐                            │
│                          │  LORE INJECTOR AGENT  │                            │
│                          │                       │                            │
│                          │  scan_for_triggers()  │                            │
│                          │  get_character_card() │                            │
│                          │  build_lore_block()   │                            │
│                          └──────────┬────────────┘                            │
│                                     │                                         │
│                               lore_context: str                               │
│                                     │                                         │
│  beats[i].text ──────────► call_narrator(NarratorContext)                    │
│  lore_context ──────────────────────┤                                         │
│  author_note (if due) ──────────────┤                                         │
│  redirect_instruction (if any) ─────┤                                         │
│                                     │                                         │
│                                     ▼                                         │
│                          ┌──────────────────────┐                            │
│                          │    NARRATOR AGENT     │                            │
│                          │                       │                            │
│                          │  [conversation hist]  │◄── prior beats (summary)  │
│                          │  write prose          │                            │
│                          └──────────┬────────────┘                            │
│                                     │                                         │
│                               prose_output: str                               │
│                                     │                                         │
│  beats[i].text ──────────► call_evaluator()                                  │
│  prose_output ──────────────────────┤                                         │
│  writing_style ─────────────────────┤                                         │
│  prior_summary ─────────────────────┤                                         │
│                                     │                                         │
│                                     ▼                                         │
│                          ┌──────────────────────┐                            │
│                          │   EVALUATOR AGENT     │                            │
│                          │                       │                            │
│                          │  check_beat_coverage  │                            │
│                          │  check_style_comp.    │                            │
│                          │  check_coherence      │                            │
│                          │  emit_eval_result     │                            │
│                          └──────────┬────────────┘                            │
│                                     │                                         │
│                               EvalResult                                      │
│                                     │                                         │
│              ┌──────────────────────┤                                         │
│              │                      │                                         │
│           "pass"                 "retry"                                      │
│              │                      └──► loop (append reason, re-call)        │
│              ▼                                                                │
│          save_beat()                                                          │
│          [mode check] ──────────────► request_human_input() (if applicable)  │
│                                                                               │
└──────────────────────────────────────────────────────────────────────────────┘
```

### What Each Agent Receives and Returns

| Agent | Receives | Returns |
|---|---|---|
| `LoreInjectorAgent` | beat_text, characters (full list), world_info | `lore_context: str` |
| `NarratorAgent` | NarratorContext (beat + lore + note + redirect) | `prose: str` |
| `EvaluatorAgent` | beat_instruction, prose, writing_style, prior_summary | `EvalResult` |
| `OrchestratorAgent` | scene .md file path | written output file path |

### Session State Owned by Orchestrator

The Orchestrator owns all mutable scene state:

| State variable | Type | Description |
|---|---|---|
| `parsed_scene` | `ParsedScene` | Full parsed input, read-only after parse |
| `completed_beats` | `list[str]` | Prose strings accumulated per beat |
| `beat_index` | `int` | Current beat (1-based) |
| `retry_count` | `int` | Retry counter, reset per beat |
| `narrator_agent` | `NarratorAgent` | Persistent agent instance, lives for full scene |
| `prior_summary` | `str` | Orchestrator-maintained rolling summary — appends 1-line per beat after eval pass. Fed to Evaluator `check_coherence`. |

The `NarratorAgent` is the only sub-agent that carries inter-beat state
(via its `SummarizingConversationManager`). All other sub-agents are stateless
per invocation.

---

## 7. Model Provider Strategy

**File:** `my_code/models/provider.py`

### Design Principle

All model configuration is centralised in **one place** — environment variables read by a single
`get_model(role)` factory. Swapping between local dev (LM Studio / llama.cpp) and cloud
(OpenRouter / Anthropic / Bedrock) is a `.env` change, zero code changes.

### Why This Works

LM Studio, llama.cpp, Ollama, and OpenRouter all expose the same **OpenAI-compatible
`/v1/chat/completions`** endpoint. Strands' `OpenAIModel` speaks this protocol natively.
Changing the backend is just changing `base_url` + `model_id`.

```
Local backend (LM Studio / llama.cpp / Ollama)
        ↕  OpenAI-compatible API (localhost)
    Strands OpenAIModel(base_url, model_id)
        ↕
    provider.get_model("narrator")
        ↕
    Agent(model=...)
```

### Environment Variables

| Variable | Example (local) | Example (cloud) | Description |
|---|---|---|---|
| `STORY_ENGINE_PROVIDER` | `local` | `openrouter` | Selects provider path |
| `STORY_ENGINE_LOCAL_BASE_URL` | `http://localhost:1234/v1` | — | Base URL for local backends |
| `STORY_ENGINE_NARRATOR_MODEL` | `qwen3-30b-a3b` | `deepseek/deepseek-v3.2` | Model for NarratorAgent |
| `STORY_ENGINE_EVALUATOR_MODEL` | `qwen3-8b` | `claude-sonnet-4-20250514` | Model for EvaluatorAgent (can be cheaper) |
| `STORY_ENGINE_ORCHESTRATOR_MODEL` | `qwen3-30b-a3b` | `deepseek/deepseek-v3.2` | Model for OrchestratorAgent |
| `STORY_ENGINE_LORE_MODEL` | `qwen3-8b` | `deepseek/deepseek-v3.2` | Model for LoreInjectorAgent |
| `OPENROUTER_API_KEY` | — | `sk-or-...` | Required for cloud provider |

### Provider Factory

```python
# my_code/models/provider.py
import os
from strands.models.openai import OpenAIModel

_ROLES = ("narrator", "evaluator", "orchestrator", "lore_injector")
_DEFAULT_MODEL = "default"

def get_model(role: str) -> OpenAIModel:
    """Return a Strands model instance for the given agent role.

    All config comes from env vars — swap .env to switch backends.
    """
    provider = os.environ.get("STORY_ENGINE_PROVIDER", "local")

    if provider == "local":
        base_url = os.environ.get(
            "STORY_ENGINE_LOCAL_BASE_URL", "http://localhost:1234/v1"
        )
        model_id = os.environ.get(
            f"STORY_ENGINE_{role.upper()}_MODEL", _DEFAULT_MODEL
        )
        return OpenAIModel(
            client_args={"base_url": base_url, "api_key": "not-needed"},
            model_id=model_id,
        )

    elif provider == "openrouter":
        model_id = os.environ.get(
            f"STORY_ENGINE_{role.upper()}_MODEL", "deepseek/deepseek-v3.2"
        )
        return OpenAIModel(
            client_args={
                "base_url": "https://openrouter.ai/api/v1",
                "api_key": os.environ["OPENROUTER_API_KEY"],
            },
            model_id=model_id,
        )

    elif provider == "anthropic":
        from strands.models import AnthropicModel
        model_id = os.environ.get(
            f"STORY_ENGINE_{role.upper()}_MODEL", "claude-sonnet-4-20250514"
        )
        return AnthropicModel(model=model_id)

    elif provider == "bedrock":
        from strands.models import BedrockModel
        model_id = os.environ.get(
            f"STORY_ENGINE_{role.upper()}_MODEL",
            "us.anthropic.claude-sonnet-4-20250514-v1:0"
        )
        return BedrockModel(model_id=model_id)

    else:
        raise ValueError(f"Unknown provider: {provider}")
```

### Example `.env` Files

**Local dev (LM Studio):**
```env
STORY_ENGINE_PROVIDER=local
STORY_ENGINE_LOCAL_BASE_URL=http://localhost:1234/v1
STORY_ENGINE_NARRATOR_MODEL=qwen3-30b-a3b
STORY_ENGINE_EVALUATOR_MODEL=qwen3-8b
STORY_ENGINE_ORCHESTRATOR_MODEL=qwen3-30b-a3b
STORY_ENGINE_LORE_MODEL=qwen3-8b
```

**Local dev (Ollama):**
```env
STORY_ENGINE_PROVIDER=local
STORY_ENGINE_LOCAL_BASE_URL=http://localhost:11434/v1
STORY_ENGINE_NARRATOR_MODEL=llama3.1:70b
STORY_ENGINE_EVALUATOR_MODEL=llama3.1:8b
STORY_ENGINE_ORCHESTRATOR_MODEL=llama3.1:70b
STORY_ENGINE_LORE_MODEL=llama3.1:8b
```

**Cloud (OpenRouter):**
```env
STORY_ENGINE_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-...
STORY_ENGINE_NARRATOR_MODEL=deepseek/deepseek-v3.2
STORY_ENGINE_EVALUATOR_MODEL=anthropic/claude-sonnet-4-20250514
STORY_ENGINE_ORCHESTRATOR_MODEL=deepseek/deepseek-v3.2
STORY_ENGINE_LORE_MODEL=deepseek/deepseek-v3.2
```

### Local Backend Notes

| Concern | Guidance |
|---------|---------|
| **Tool calling** | Verify the loaded model supports function/tool calling (GGUF with chat template). Orchestrator, LoreInjector, and Evaluator require it. Narrator does not. |
| **Context window** | Local models have smaller context. `SummarizingConversationManager` triggers on context overflow automatically — but lower `preserve_recent_messages` (e.g., 6) for local dev to leave more room. |
| **Single model loaded** | LM Studio loads one model at a time. Use the same model for all roles, or run multiple llama.cpp instances on different ports. |
| **Speed** | Local inference is slower. For dev iteration, use `autonomous` mode with 1–2 beats. |

---

## Open Design Questions

### Resolved

| Question | Decision | Rationale |
|---|---|---|
| Evaluator model | **Per-role model via env var** | `provider.get_model("evaluator")` reads `STORY_ENGINE_EVALUATOR_MODEL`. Can be a cheaper/smaller model. See §7. |
| Retry backoff strategy | **Count-only (max 3)** | Simple retry counter, reset per beat. No exponential backoff — LLM regeneration doesn't benefit from delays. Add backoff later if needed. |
| Output headers | **Config in `[meta].output_format`** | `prose` = seamless, `adventure` = beat headers, `script` = screenplay formatting. Already reflected in `Meta.output_format`. |
| Session persistence | **Out of scope for v1** | Each scene run is independent. Strands SessionManager can be added later for resume-from-checkpoint. |
| `prior_summary` source | **Orchestrator-owned rolling summary** | The Narrator's `SummarizingConversationManager` stores summaries in a private `_summary_message` — coupling to that is fragile. Instead, the Orchestrator maintains its own `prior_summary: str` by appending a 1-line summary of each beat's prose after it passes evaluation. Simple, no private-API coupling, and gives the Evaluator exactly what it needs for coherence checks. |
