# Story Engine — Input File Schema
> Version 1.0 — This is the contract. All agents read from this format.

---

## Overview

One `.md` file = one scene.  
For multi-scene stories, use one file per scene in a folder.  
Files are processed top-to-bottom. Section order matters.

All sections use the format:
```
[section-name]
content here
```

Inline directives (e.g. `[pause]`) appear inside section content.

---

## Full Annotated Example

```markdown
# ============================================================
# STORY ENGINE INPUT FILE
# ============================================================

# ── EXECUTION CONTROL ────────────────────────────────────────

[meta]
title: The Ruins of Ashenveil
version: 1.0
mode: semi-interactive
# Options: autonomous | interactive | semi-interactive
# autonomous     = runs to completion, no human input
# interactive    = pauses after EVERY beat for human input
# semi-interactive = pauses only at [pause]-marked beats

pause_at: beat
# Only used when mode = semi-interactive
# beat = pause at any beat tagged with [pause]

output_file: output/ashenveil_scene1.md
output_format: prose
# Options: prose | adventure | script

pov: third-person
# Options: third-person | first-person | second-person

target_length: 2000
# Target word count for the full assembled scene

language: en
nsfw: false
# true | false — passed to Narrator as content guidance


# ── NARRATOR CONFIGURATION ──────────────────────────────────

[narrator-prompt]
You are the narrator of a dark fantasy world called Ashenveil.
Write in third-person past tense. You control all characters
except the player character (marked role: player-character).
Introduce NPCs organically through action and dialogue.
Never break character. Never summarize — show through scene.

[writing-style]
Literary fiction. Show don't tell. Paragraph breaks for pacing.
Dialogue in quotes. Internal thoughts in italics.
Avoid purple prose. Keep sentences varied in length.
Use sensory detail — smell, sound, texture — not just visuals.

[author-note]
depth: 4
# Inject this note every N beats as a persistent reminder
content: Maintain tension. Don't resolve conflicts prematurely.
         Keep character motivations consistent with their cards.


# ── WORLD BUILDING ──────────────────────────────────────────

[world-info]
Ashenveil is a crumbling empire on the edge of collapse.
Magic is rare and feared. The ruling Conclave of Scribes
hoards all written knowledge. Outside the capital, the land
is wild and dangerous — old ruins hold power that predates
the empire itself. The common people are superstitious and
largely illiterate by design.


# ── CHARACTER CARDS ─────────────────────────────────────────

[character-1]
name: Lyra Voss
role: player-character
# Options: player-character | npc | antagonist | neutral
# player-character = narrator describes reactions but does not
#                    make decisions for this character
# npc / antagonist / neutral = narrator has full creative control

triggers: Lyra, she, Voss, the scout, the woman
# Comma-separated keywords that trigger lore injection
# Used by LoreInjectorAgent to know when to add this card's
# context to the Narrator's prompt

description: >
  Lyra Voss is a 28-year-old deserter from the Conclave's
  enforcement arm. Lean, dark-haired, perpetually wary.
  She carries a shortbow and a knife she's never cleaned.

personality: Stubborn, darkly funny, deeply distrustful of
             authority. Loyal to a fault once trust is earned.

backstory: >
  Deserted after being ordered to burn a village. Has been
  running for two years. Knows too much about Conclave
  operations to be left alive if caught.

speech_style: Clipped sentences. Sarcasm as deflection.
              Rarely says what she actually means.
              Swears under her breath, not out loud.


[character-2]
name: Brother Aldric
role: npc
triggers: Aldric, he, the monk, the brother, old man

description: >
  A 60-year-old disgraced monk of the Hollow Order.
  Gaunt, white-bearded, surprisingly strong for his age.
  Wears a patched grey robe with the Order's symbol
  scratched out at the breast.

personality: Gentle but evasive. Knows far more than he admits.
             Genuinely kind, which makes him suspicious.
             Unafraid of things that should frighten him.

backstory: >
  Cast out of the Order for heresy — specifically for
  claiming the old ruins still held living power, and that
  the Conclave was wrong to suppress that knowledge.

speech_style: Formal, old-fashioned diction. Speaks in
              questions more than statements. Long pauses
              before answering. Never lies directly.

# Add more [character-N] blocks as needed.
# N can be any integer. Processed in order.


# ── SCENE CONFIGURATION ─────────────────────────────────────

[scene-setup]
location: The approach to the Ashenveil ruins, late afternoon.
          Dense fog rolling in from the east. Ancient stone
          archways half-swallowed by blackthorn vines.
time: Late afternoon, autumn. Sun low, light failing fast.
atmosphere: Dread and exhaustion. The ruins feel watched.
            The fog carries a smell of old ash.

[scenario]
Lyra has been tracking Brother Aldric for three days after
he was spotted near the ruins — a restricted zone she knows
all too well from her Conclave days. She doesn't know if
he's a threat, a fool, or bait. She catches up to him just
as he's about to step through the entrance archway.


# ── STORY STRUCTURE ─────────────────────────────────────────

[scene-beats]
1. Lyra spots Aldric approaching the ruins entrance. She's
   been following him unseen. Establish atmosphere, her
   wariness, the wrongness of the place.

2. She confronts him. Tense exchange — neither trusts the
   other. He's not afraid of her, which unsettles her.
   [pause]

3. Something moves inside the ruins. Both react — first
   moment they're inadvertently on the same side.

4. They make a decision: enter together or not at all.
   The choice should feel earned, not easy.
   [pause]

5. They step inside. End on an image, not an action.
   Something Lyra notices that she doesn't tell Aldric.

# [pause] inline marker:
# In semi-interactive mode: triggers a Strands interrupt here.
# Human sees the output so far, types ">" to redirect or
# presses Enter to approve and continue.
# In autonomous mode: [pause] markers are ignored.
# In interactive mode: pauses happen after every beat
#                      regardless of [pause] markers.


# ── WRITING DIRECTION ────────────────────────────────────────

[writing-instructions]
Open on Lyra's POV, close third-person. Start mid-motion —
she's already watching him, don't open with her arriving.
The ruins should feel like a character, not a backdrop.
Let Aldric be disarming. Don't make him obviously sinister.
The confrontation in beat 2 should have dark humour —
Lyra's sarcasm as a deflection under stress.
```

---

## Section Reference

### `[meta]` — Required

| Field | Type | Required | Options / Notes |
|---|---|---|---|
| `title` | string | yes | Scene title, used in output header |
| `version` | string | no | Schema version, default `1.0` |
| `mode` | enum | yes | `autonomous` \| `interactive` \| `semi-interactive` |
| `pause_at` | enum | no | `beat` (default) — where semi-interactive pauses |
| `output_file` | path | yes | Relative path for output `.md` file |
| `output_format` | enum | yes | `prose` \| `adventure` \| `script` |
| `pov` | enum | yes | `third-person` \| `first-person` \| `second-person` |
| `target_length` | int | no | Target word count, default `1500` |
| `language` | string | no | ISO code, default `en` |
| `nsfw` | bool | no | `true` \| `false`, default `false` |

---

### `[narrator-prompt]` — Required

Free text. This is the system prompt for the NarratorAgent.  
Define the narrator's identity, world context, and core rules.  
Keep it focused — world details belong in `[world-info]`.

---

### `[writing-style]` — Required

Free text. Separate from narrator identity.  
Defines *how* the narrator writes — POV, tense, prose style, formatting.  
Can be swapped across scenes without touching the narrator prompt.

---

### `[author-note]` — Optional

```
[author-note]
depth: 4          # integer — inject every N beats
content: ...      # free text — persistent reminder to narrator
```

Injected by the OrchestratorAgent every `depth` beats.  
Equivalent to SillyTavern's Author's Note feature.

---

### `[world-info]` — Required

Free text. Global world lore — always included in Narrator context.  
Keep concise. Not keyword-triggered — always present.  
Character-specific lore belongs in character cards.

---

### `[character-N]` — At least one required

Multiple blocks allowed. N is any integer (1, 2, 3...).  
Processed in order. Each block supports:

| Field | Required | Notes |
|---|---|---|
| `name` | yes | Character's full name |
| `role` | yes | `player-character` \| `npc` \| `antagonist` \| `neutral` |
| `triggers` | yes | Comma-separated keywords for LoreInjector |
| `description` | yes | Physical appearance, age, occupation |
| `personality` | yes | Core traits, how they behave |
| `backstory` | no | Relevant history the narrator should know |
| `speech_style` | no | How they talk — strongly recommended |

**`role: player-character`** — Narrator describes this character's  
perceptions and reactions but does NOT make decisions for them.  
In interactive/semi mode, the human steers this character via `>` input.

---

### `[scene-setup]` — Required

```
[scene-setup]
location: ...
time: ...
atmosphere: ...
```

Physical and sensory context for the scene.  
All three sub-fields are optional individually but at least one is expected.

---

### `[scenario]` — Required

Free text. The backstory/situation that leads into this scene.  
Equivalent to ST's Scenario field + Memory combined.  
Not repeated in output — used only to brief the Narrator.

---

### `[scene-beats]` — Required

Numbered list. Each beat is one prose generation unit.

```
[scene-beats]
1. Description of what should happen in beat 1.
2. Description of beat 2.
   [pause]       ← optional inline pause marker
3. Description of beat 3.
```

**`[pause]` inline marker:**
- `semi-interactive` mode: triggers Strands interrupt after this beat
- `interactive` mode: ignored (pauses after every beat anyway)
- `autonomous` mode: ignored (never pauses)

Beat descriptions should be directional, not prescriptive.  
Tell the Narrator *what* should happen, not *how* to write it.

---

### `[writing-instructions]` — Optional but Recommended

Free text. Scene-specific directions for the Narrator.  
Equivalent to the `>` action input in SillyTavern/KoboldCPP.  
Injected once at the start of the first beat, then available  
for reference throughout the scene.

---

## Inline Directives (Inside Beat Descriptions)

| Directive | Where | Behaviour |
|---|---|---|
| `[pause]` | inside `[scene-beats]` | Interrupt after this beat (semi-interactive only) |

More directives may be added in future versions.

---

## Human Input During Pauses

When execution pauses in `interactive` or `semi-interactive` mode,  
the human sees the prose output so far and is prompted:

```
[Beat 2 complete]
──────────────────────────────────────────
[prose output shown here]
──────────────────────────────────────────
> Type a direction to redirect, or press Enter to continue:
```

Input options:
- **Press Enter / empty input** → approve and continue to next beat
- **`> free text`** → redirect instruction fed back to Narrator, beat regenerated
- **`> /skip`** → skip this beat entirely, move to next
- **`> /stop`** → stop execution, save what's written so far
- **`> /retry`** → discard output, regenerate this beat with no new input

---

## Naming Convention

```
[world-name]_scene[N]_[short-descriptor].md

Examples:
  ashenveil_scene1_ruins_approach.md
  thornwood_scene3_the_ambush.md
  ironport_scene1_arrival.md
```

---

## Notes on Token Efficiency

- `[world-info]` is always included — keep it under ~300 words
- Character cards are injected only when their `triggers` fire
- `[scenario]` is included once at scene start, not every beat
- `[writing-instructions]` is included once at scene start
- `[author-note]` is re-injected every `depth` beats

For long scenes with many characters, keep individual  
character cards under ~200 words each to manage context budget.
