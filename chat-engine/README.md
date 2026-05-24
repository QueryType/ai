# Chat Engine

A CLI tool for multi-character autonomous conversation. Multiple AI characters share a world and talk to each other. You can watch, steer, or step in as any character at any time.

---

## Quick start

```bash
conda activate strandsagents
cp .env.example .env        # edit with your model settings
python -m src.chat.main_chat examples/ashenveil_chat1.md
```

---

## Setup

### Environment

Copy `.env.example` to `.env` and configure your model provider.

**Local inference (LM Studio, Ollama, Jan):**
```
CHAT_ENGINE_PROVIDER=local
CHAT_ENGINE_LOCAL_BASE_URL=http://localhost:1234/v1
CHAT_ENGINE_MODEL=your-loaded-model-name
```

**OpenRouter:**
```
CHAT_ENGINE_PROVIDER=openrouter
OPENROUTER_API_KEY=your-key
CHAT_ENGINE_MODEL=deepseek/deepseek-v3.2
```

**Anthropic direct:**
```
CHAT_ENGINE_PROVIDER=anthropic
ANTHROPIC_API_KEY=your-key
CHAT_ENGINE_MODEL=claude-sonnet-4-6
```

### Dependencies

```bash
pip install -r requirements.txt
```

---

## Running a session

```bash
python -m src.chat.main_chat examples/ashenveil_chat1.md
```

Turns print as they generate:

```
[T001] Lyra Voss: "You're going in there alone. That's either brave or stupid."
[T002] Brother Aldric: "I've been called both. Neither has stopped me."
[T003] Lyra Voss: "The Conclave has this place flagged. You know that."
[T004] Brother Aldric: "Do they? And yet here you are as well."
[T005] Mira: "The door already knows you're here."
──────────────────────────────────────────────────────
Turn 5  │  Lyra Voss: 2  Brother Aldric: 2  Mira: 1
──────────────────────────────────────────────────────
  Enter to continue, or type a command:
```

Every 5 turns (configurable) the session pauses and waits for your input.

---

## Steering the conversation

### Let it run

Press **Enter** at any pause. In `rules` mode, the rule engine picks the next speaker. In `llm` mode, the model chooses the next speaker and writes the next line in one call.

### Speak as a character

```
[as Lyra] I've seen that symbol. On the bodies they left behind.
```

Your line is injected as Lyra's turn and appears in the transcript exactly like any other line. The GM picks up from there — other characters will react to what you said.

The name is fuzzy-matched, so short names and trigger words work:

```
[as Aldric] We should not linger here.
[as the monk] We should not linger here.
```

### Give the GM a secret instruction

```
[director] Aldric should hint he has been inside the ruins before
```

This note is passed to the GM on the next turn only, then discarded. It never appears in the transcript — it's invisible steering. Use it to nudge tone, drop a revelation, or set up a beat.

### Force who speaks next

```
/next Mira
```

The GM generates Mira's line regardless of what the orchestrator would have picked. Useful when a character has gone quiet and you want to bring them back in.

### Pause after every turn

```
/pause
```

Toggles pause-every-turn mode. Now the session stops after each line so you can read carefully and decide whether to intervene. Press `/pause` again to return to the normal pause interval.

### Check speaking stats

```
/status
```

Shows turn count, last speaker, and how many times each character has spoken.

### End the session

```
/stop
```

Saves both output files and exits.

---

## Output files

Two files are written on `/stop` or when max turns is reached.

### Transcript — clean story output

```
output/ashenveil_chat1_transcript.md
```

Reads as a natural conversation. Human-injected lines are indistinguishable from GM-generated ones. No system markers.

```markdown
# Ashenveil — The Ruins Encounter
*Session started: 2026-04-21T14:32:00*

---

Lyra Voss: "You're going in there alone. That's either brave or stupid."
Brother Aldric: "I've been called both. Neither has stopped me."
Lyra Voss: "The Conclave has this place flagged. You know that."
...
```

### Run log — application record

```
output/ashenveil_chat1_runlog.md
```

Every turn with metadata: who spoke, how they were selected, token count, any director notes.

```markdown
[T001] SPEAKER: Lyra Voss      | GEN: gm    | RULE: opening_turn        | TOKENS: 142
[T002] SPEAKER: Brother Aldric | GEN: gm    | RULE: direct_address      | TOKENS: 98
[T003] SPEAKER: Lyra Voss      | GEN: human | CMD: human_injection      | INPUT: "[as Lyra] ..."
[T004] SPEAKER: Brother Aldric | GEN: gm    | RULE: direct_address      | TOKENS: 87
       DIRECTOR NOTE: "Aldric should hint he's been inside before"
```

---

## Creating your own scenario

Copy `examples/ashenveil_chat1.md` and edit the sections.

### Builder UI

If you want a form-based editor instead of hand-editing markdown, open:

```bash
open my_code/chat-builder.html
```

The builder is a standalone HTML file with no Node or server requirement. It can:

- import an existing chat markdown file such as `examples/ashenveil_chat1.md`
- edit all parser-backed sections, including ending-window controls and `response_length`
- live-preview the emitted markdown
- download a new `.md` file that matches the parser contract in `src/chat/parser.py`

It stores draft state in browser local storage, so imports and in-progress edits stay local to your machine.

### Required sections

**`[meta]`** — title and output file paths.

**`[world-info]`** — shared world lore. Keep under 300 words. This goes into every GM context window.

**`[gm-prompt]`** — the GM's identity and output format rules. The example prompt works well. Change the world name at minimum.

**`[writing-style]`** — tone and style guidance. Adjust for your genre.

**`[scenario]`** — the situation at the start of the conversation. Who is here, where, why, and what tension exists between them.

**`[chat-config]`** — runtime controls such as `history_window`, `history_summary_chars`, `max_turns`, `ending_countdown_turns`, and `ending_grace_turns`.

**`[character-1]`, `[character-2]`, ...** — at least two characters required.

### Character fields

```markdown
[character-1]
name: Elena Voss
role: player-character
triggers: Elena, she, the detective, Voss
speaking_weight: 1.0
can_be_taken_over: true

description: >
  Physical appearance. Who are they at a glance.

personality: Core traits. How they relate to others.

backstory: >
  What shaped them. What they're carrying into this scene.

speech_style: How they talk. Sentence length, vocabulary, habits.
              This is the most important field for voice consistency.
```

**`triggers`** — comma-separated words the orchestrator watches for in dialogue. When another character says one of these words, Rule 1 (Direct Address) fires and this character speaks next. Include the character's name, pronouns, and any nicknames or epithets other characters might use.

**`speaking_weight`** — relative speaking frequency in round-robin. `1.0` is normal. `0.6` means roughly 60% as often. Use lower values for background characters who should appear occasionally but not dominate.

**`can_be_taken_over`** — set to `false` to prevent `[as Name]` injection for that character.

### Chat config knobs

```markdown
[chat-config]
max_turns: 40         # 0 = unlimited
pause_every: 5        # 0 = never auto-pause (use /pause manually)
history_window: 20    # how many turns the GM sees per call
history_summary_chars: 700  # semantic older-turn summary for GM continuity
opening_speaker: Elena  # or "auto" to let the orchestrator decide
turn_selection: rules # rules (default) or llm
max_retries: 2        # GM output retry limit on malformed response
```

**For a short test run:** set `max_turns: 8` and `pause_every: 2`.

**For a long autonomous run:** set `pause_every: 0` and let it run to `max_turns`, then read the transcript at the end.

**For tight control:** set `pause_every: 1` so you review and can steer every single turn.

---

## How turn selection works

Set `turn_selection` in `[chat-config]` to choose the mode.

### `rules` (default)

A deterministic rule engine. Applies these rules in order — first match wins.

| Priority | Rule | When it fires |
|---|---|---|
| 1 | **Direct Address** | Last line names a character or contains a question |
| 2 | **Human Reaction** | You just injected a line — most relevant character responds |
| 3 | **Conflict Escalation** | Tension detected — challenged character fires back |
| 4 | **Round-Robin** | No clear trigger — rotate through cast, skip recent speakers |
| 5 | **Fallback** | Character with lowest weighted speaking count |

### `llm`

The model reads the recent chat history, chooses the next speaker, and writes that speaker's next line in one call. This keeps the flow more natural and avoids an extra selection-only model call.

The run log shows `RULE: llm_combined_turn` for these model-selected turns.

Both modes respect `/next Name` overrides and `opening_speaker` config.

---

## Tips

**Voice consistency** — the `speech_style` field is the most powerful lever. Be specific: sentence length, vocabulary range, rhetorical habits, what the character avoids saying. Vague descriptions produce vague voices.

**Tension** — the conflict escalation rule triggers on common tension words (`wrong`, `no`, `never`, `fool`, `doubt`, etc.). Writing characters who push back on each other produces more dynamic turn selection than polite agreement.

**Director notes** — the most effective steering tool. Use them to plant information, accelerate a reveal, or shift tone without breaking the flow of the conversation. The GM treats them as private stage directions.

**Long sessions** — `history_window` keeps the recent turns verbatim. Older turns are compressed into a bounded semantic summary using `history_summary_chars`, so long sessions stay coherent without replaying the full transcript every turn.

**Injecting as a character** — your injected lines are indistinguishable from GM lines in the transcript. If you want a record of which lines were yours, check the run log.

---

## File naming convention

```
[world]_chat[N].md

Examples:
  ashenveil_chat1.md
  thornwood_chat1.md
  ironport_chat2.md
```

---

## Project structure

```
chat-engine/
├── examples/
│   └── ashenveil_chat1.md      input file — world + characters + config
├── src/chat/
│   ├── parser.py               reads .md input → ParsedChat dataclass
│   ├── chat_logger.py          records turns, saves transcript + run log
│   ├── history_summarizer.py   rolling semantic summary for older history
│   ├── orchestrator.py         rule-based turn selector (turn_selection: rules)
│   ├── gm_agent.py             Strands agent — writes one line, or chooses speaker + line in llm mode
│   ├── main_chat.py            CLI loop + human command handling
│   └── models/
│       └── provider.py         model factory (local / openrouter / anthropic / bedrock)
├── output/                     generated transcripts and run logs
├── .env.example
├── requirements.txt
└── README.md
```
