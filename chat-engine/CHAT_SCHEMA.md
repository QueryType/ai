# Story Engine — Chat App Input Schema
> Version 1.0 — Format spec for multi-character chat input files.
> Read alongside CHAT_APP_BRIEF.md.

---

## Overview

One `.md` file = one chat session setup.
The file defines the shared world, all characters, the opening scenario,
and how the chat session should be managed.

Same section syntax as the story engine:
```
[section-name]
content
```

Characters defined here share the same world and scenario.
Each has their own card. The GM agent switches between their voices.

---

## Full Annotated Example

```markdown
# ============================================================
# CHAT ENGINE — CHAT INPUT FILE
# ============================================================

[meta]
title: Ashenveil — The Ruins Encounter
version: 1.0
mode: chat
output_transcript: output/ashenveil_chat1_transcript.md
output_runlog: output/ashenveil_chat1_runlog.md
language: en
nsfw: false


[chat-config]
max_turns: 40
# Planned chat length target. Set to 0 for unlimited.

pause_every: 5
# Pause and prompt human every N turns.
# Set to 0 to never auto-pause (human can still /pause manually).

history_window: 20
# How many recent turns to include in GM context per turn.
# Older turns are dropped to manage token budget.

history_summary_chars: 700
# If older turns fall outside history_window, maintain a bounded semantic summary.
# Set to 0 to disable summary and send only the recent window.

ending_countdown_turns: 2
# Start prompting the GM to land the current scene this many turns before max_turns.

ending_grace_turns: 2
# Allow this many extra turns after max_turns so the current scene can finish cleanly.

opening_speaker: Lyra
# Which character speaks the first line.
# Use "auto" to let orchestrator decide based on scenario.

turn_selection: rules
# rules — rule-based orchestrator (Phase 1, default)
# llm   — LLM-driven orchestrator (Phase 2)

max_retries: 2
# If GM produces malformed output, retry this many times.


[phase-1]
name: First Contact
turns: 1-8
goal: Establish distrust and the initial conversational dynamic.
pace: measured
focus_characters: Lyra Voss, Brother Aldric
required_characters: Lyra Voss, Brother Aldric
avoid_characters: Mira
guidance: Keep Mira peripheral until later.
max_consecutive_turns: 2


[world-info]
Ashenveil is a crumbling empire on the edge of collapse.
Magic is rare and feared. The ruling Conclave of Scribes hoards
all written knowledge. Outside the capital, the land is wild and
dangerous — old ruins hold power that predates the empire itself.
The common people are superstitious and largely illiterate by
design. Conclave enforcers wear grey coats with a red wax seal
at the collar. Deserters are executed on sight.


[gm-prompt]
You are the Game Master of Ashenveil.
You write dialogue for multiple characters in a shared story.
Each turn you will either be told which character speaks next,
or you will choose the next speaker from the available cast.
Write ONLY that character's single dialogue line — nothing else.
Format your output exactly as:
  [Character Name]: "dialogue here"
One line only. No stage directions. No narration. No asterisks.
Stay true to each character's voice as defined in their card.
Never speak as a narrator. Never add parenthetical actions.
Never write more than one character per turn.


[writing-style]
Chat style. Dialogue only — no prose narration between lines.
Each turn is one line from one character.
Dialogue should feel natural and character-specific.
Lines should be 1-3 sentences maximum.
Characters may speak in incomplete sentences if that fits their voice.
Subtext is welcome. Characters don't always say what they mean.


[scenario]
Lyra Voss has tracked Brother Aldric to the entrance of the
Ashenveil ruins. She doesn't know if he's a threat, a fool,
or bait. She confronts him just as he's about to step inside.
Both are wary of each other and of the ruins. Neither wants
to be here with a stranger — but neither wants to be here alone.
The conversation begins the moment Lyra steps out of the treeline.


[character-1]
name: Lyra Voss
role: player-character
triggers: Lyra, she, Voss, the scout, the woman
speaking_weight: 1.0
can_be_taken_over: true

description: >
  Lyra Voss is a 28-year-old deserter from the Conclave's
  enforcement arm. Lean, dark-haired, perpetually wary.
  Carries a shortbow and a knife she's never cleaned.

personality: Stubborn, darkly funny, deeply distrustful of
             authority. Loyal to a fault once trust is earned.

backstory: >
  Deserted three years ago after being ordered to burn a village.
  She did it. Has been running ever since. Knows enough about
  Conclave operations to be dangerous — and hunted.

speech_style: Clipped sentences. Sarcasm as deflection.
              Rarely says what she means. Asks questions
              she already knows the answer to.


[character-2]
name: Brother Aldric
role: npc
triggers: Aldric, he, the monk, the brother, old man
speaking_weight: 1.0
can_be_taken_over: true

description: >
  A 60-year-old disgraced monk of the Hollow Order.
  Gaunt, white-bearded, surprisingly strong for his age.
  Wears a patched grey robe with the Order's symbol
  scratched out at the breast.

personality: Gentle but evasive. Knows far more than he admits.
             Unafraid of things that should frighten him.
             Genuinely kind — which makes him suspicious.

backstory: >
  Cast out of the Hollow Order for heresy — claiming the old
  ruins still held living power the Conclave was suppressing.
  He was right. He's been back three times since his exile.

speech_style: Formal, old-fashioned diction. Speaks in questions
              more than statements. Long pauses implied.
              Never lies directly — deflects instead.


[character-3]
name: Mira
role: npc
triggers: Mira, girl, the child, she
speaking_weight: 0.6
# Lower weight — she speaks less often than the others
can_be_taken_over: true

description: >
  A 14-year-old girl who lives near the ruins. Wild hair,
  bare feet despite the cold. Appears from nowhere and
  disappears the same way. Locals say she's touched.

personality: Odd, direct, unfiltered. Says disturbing things
             casually. Not malicious — just sees things others
             don't and hasn't learned to hide it.

backstory: >
  Has lived near the ruins her whole life. The Conclave
  has tried to remove her twice. Both times she came back.
  She knows the ruins in a way that shouldn't be possible.

speech_style: Simple words. Short sentences. Literal.
              States things as facts that aren't facts yet.
              Never explains herself.
```

---

## Section Reference

### `[meta]` — Required

| Field | Type | Required | Notes |
|---|---|---|---|
| `title` | string | yes | Used in transcript header |
| `version` | string | no | Default `1.0` |
| `mode` | enum | yes | Must be `chat` for this schema |
| `output_transcript` | path | yes | Clean chat output file |
| `output_runlog` | path | yes | Application run log file |
| `language` | string | no | Default `en` |
| `nsfw` | bool | no | Default `false` |

---

### `[chat-config]` — Required

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `max_turns` | int | no | `50` | `0` = unlimited |
| `pause_every` | int | no | `5` | `0` = never auto-pause |
| `history_window` | int | no | `20` | Recent turns in GM context |
| `history_summary_chars` | int | no | `700` | Max characters for rolling semantic summary of older turns; `0` disables summary |
| `ending_countdown_turns` | int | no | `2` | Start landing guidance this many turns before `max_turns` |
| `ending_grace_turns` | int | no | `2` | Extra turns allowed past `max_turns` to finish the scene |
| `opening_speaker` | string | no | `auto` | Character name or `auto` |
| `turn_selection` | enum | no | `rules` | `rules` = rule-based; `llm` = LLM-driven |
| `max_retries` | int | no | `2` | GM output retry limit |

---

### `[world-info]` — Required

Free text. Always included in GM context.
Keep under 300 words for token efficiency.
Global lore only — character-specific backstory goes in character cards.

---

### `[gm-prompt]` — Required

The system prompt for the GM agent.
Defines the GM's role, output format constraints, and core rules.
This is the most important section for output quality.

**Critical rules to always include:**
- Write ONE character per turn only
- Exact output format: `[Name]: "dialogue"`
- No narration, no stage directions, no asterisks
- Stay true to character cards
- If the engine does not provide `NEXT SPEAKER`, choose one speaker and still write only that speaker's line

---

### `[writing-style]` — Required

Defines the style of dialogue output.
For chat mode this should emphasise brevity — 1-3 sentences per turn.
Passed to GM agent as part of system prompt.

---

### `[scenario]` — Required

Free text. The situation at the start of the chat.
Included once in GM context at session start.
Equivalent to story engine's `[scenario]` — sets the stage.

---

### `[phase-N]` — Optional

Use numbered phase sections such as `[phase-1]`, `[phase-2]`, `[phase-3]` to shape the full-chat arc.
These sections let you define the intended flow, pacing, and character distribution across the total run.

| Field | Type | Required | Notes |
|---|---|---|---|
| `name` | string | yes | Human-readable phase name |
| `turns` | range | yes | Inclusive turn range, e.g. `1-8` |
| `goal` | string | no | High-level purpose of the phase |
| `pace` | string | no | Short pacing hint such as `measured`, `brisk`, `tightening` |
| `focus_characters` | csv | no | Characters who should dominate this phase |
| `required_characters` | csv | no | Characters who must appear at least once in this phase |
| `avoid_characters` | csv | no | Characters to de-emphasise in this phase |
| `guidance` | string | no | Extra phase-specific GM guidance |
| `max_consecutive_turns` | int | no | Soft cap used by planner to reduce repetition; default `2` |

Phase sections are optional. If omitted, the engine behaves as before and uses only local speaker selection.

---

### `[character-N]` — At least 2 required

Multiple blocks. N is any integer.
Each block supports:

| Field | Required | Notes |
|---|---|---|
| `name` | yes | Character's full name — used in output formatting |
| `role` | yes | `player-character` \| `npc` \| `antagonist` \| `neutral` |
| `triggers` | yes | Keywords for turn selection logic |
| `speaking_weight` | no | Float, default `1.0` — relative speaking frequency |
| `can_be_taken_over` | no | Bool, default `true` — human can speak as this character |
| `description` | yes | Physical appearance |
| `personality` | yes | Core traits |
| `backstory` | no | Relevant history |
| `speech_style` | yes | How they speak — critical for voice consistency |

**`role: player-character`** — In Phase 1 this is informational only.
In Phase 3 this will affect how the per-character agent is prompted.
For now the GM agent treats all characters equally.

**`speaking_weight`** — Used by the round-robin fallback rule.
Lower weight = speaks less often when no other rule applies.
Example: a background character set to `0.4` speaks roughly half
as often as a main character at `1.0`.

---

## Human Commands Reference

When the chat pauses (auto or manual), these commands are available:

| Input | Effect | Logged |
|---|---|---|
| `Enter` (empty) | Continue, GM selects next speaker | No |
| `[as Name] text` | Inject as that character's turn | Yes — run log |
| `[director] text` | Hidden OOC note to GM, next turn only | Yes — run log |
| `/next Name` | Force Name to speak next (GM generates) | Yes — run log |
| `/pause` | Keep pausing after every turn until Enter | No |
| `/stop` | End session, save all outputs | Yes — run log |
| `/status` | Show stats — turn count, speaking breakdown | No |

**Human-injected lines in transcript:**
Appear identical to GM-generated lines. No marker. No label.
The transcript is the story — human turns blend in seamlessly.

---

## Output Files

### Transcript (clean story output)

```markdown
# Ashenveil — The Ruins Encounter
*Session started: 2026-04-21*

---

Lyra: "You're going in there alone. That's either brave or stupid."
Aldric: "I've been called both. Neither has stopped me."
Lyra: "The Conclave has this place flagged. You know that."
Aldric: "Do they? And yet here you are as well."
Mira: "The door already knows you're here."
Lyra: "Where did she come from?"
Aldric: "She lives here. More or less."

---
*Session ended — Turn 24 | Reason: user /stop*
```

### Run Log (application record)

```markdown
# Run Log — Ashenveil Chat 1
*Session: 2026-04-21T14:32:00*
*Input: examples/ashenveil_chat1.md*
*Model: deepseek/deepseek-v3.2 via openrouter*

---

[T001] SPEAKER: Lyra    | GEN: gm    | RULE: opening_turn        | TOKENS: 142
[T002] SPEAKER: Aldric  | GEN: gm    | RULE: direct_address      | TOKENS: 98
[T003] SPEAKER: Lyra    | GEN: gm    | RULE: conflict_escalation | TOKENS: 115
[T004] SPEAKER: Lyra    | GEN: human | CMD: [as Lyra]            | INPUT: "The Conclave has this place flagged. You know that."
[T005] SPEAKER: Aldric  | GEN: gm    | RULE: direct_address      | TOKENS: 87
[T006] SPEAKER: Mira    | GEN: gm    | RULE: round_robin         | TOKENS: 54
[T007] SPEAKER: Lyra    | GEN: gm    | RULE: direct_address      | TOKENS: 91
[T008] SPEAKER: Aldric  | GEN: gm    | RULE: direct_address      | TOKENS: 102
       DIRECTOR NOTE: "[director] Aldric should hint he's been inside before"

---
*SESSION END*
*Total turns: 24 | Human interventions: 3 | Director notes: 1*
*Total tokens generated: 2847*
*Transcript saved: output/ashenveil_chat1_transcript.md*
*Run log saved: output/ashenveil_chat1_runlog.md*
```

---

## Naming Convention

```
[world]_chat[N]_[descriptor].md

Examples:
  ashenveil_chat1_ruins_encounter.md
  thornwood_chat2_the_market.md
  ironport_chat1_dockside.md
```

---

## Key Differences from Story Engine Schema

| Story Engine | Chat App |
|---|---|
| `[scene-beats]` — linear structure | No beats — open-ended conversation |
| `[writing-instructions]` — prose direction | `[gm-prompt]` — dialogue format rules |
| `[narrator-prompt]` — narrator identity | `[gm-prompt]` — GM identity |
| `[author-note]` with depth | Not used in Phase 1 |
| `[output]` single block | `output_transcript` + `output_runlog` |
| Evaluator checks beat completion | Orchestrator manages turn flow |
| `[pause]` inline markers | `pause_every` config + manual `/pause` |
| One narrator voice | Multiple character voices via GM |
