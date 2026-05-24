# Game Master

An AI-driven text adventure engine that replicates the Adventure mode from [KoboldCPP](https://github.com/lostruins/koboldcpp). You declare actions, the GM narrates the world's response in real-time streaming prose.

Runs entirely locally against [LM Studio](https://lmstudio.ai/) or [llama.cpp](https://github.com/ggerganov/llama.cpp), or against any OpenAI-compatible endpoint (e.g. OpenRouter). Vision-capable models (Gemma 4, LLaVA, Llama 3.2 Vision) unlock image support during play.

---

## Contents

- [How it works](#how-it-works)
- [Setup](#setup)
- [Usage](#usage)
  - [Starting a game](#starting-a-game)
  - [Web UI](#web-ui)
  - [Playing](#playing)
  - [In-game commands](#in-game-commands)
  - [Saving and loading](#saving-and-loading)
  - [Exporting the story](#exporting-the-story)
- [Using images](#using-images)
  - [Step 1 — load a vision model](#step-1--load-a-vision-model)
  - [Step 2 — add images to a scenario](#step-2--add-images-to-a-scenario)
  - [Step 3 — introduce images during play](#step-3--introduce-images-during-play)
  - [How it works under the hood](#how-it-works-under-the-hood)
- [Scenarios](#scenarios)
  - [File structure](#file-structure)
  - [Writing your own](#writing-your-own-scenario)
- [GM tools](#gm-tools)
- [Providers](#providers)
- [Environment variables](#environment-variables)
- [Architecture](#architecture)

---

## How it works

You play as the protagonist. Type what your character does and the GM narrates the world's response in literary prose. Risky actions trigger dice rolls. Key facts are tracked in a persistent memory block. The story is entirely open-ended — no pre-scripted beats.

```
[ACTION] > look around carefully
[ACTION] > approach the monk
[ACTION] > draw your knife and demand answers
```

Two input modes mirror KoboldCPP:

| Mode | What you type | Effect |
|---|---|---|
| **Action** (default) | `draw my knife` | Auto-prefixed as `"You draw my knife"` — protagonist action |
| **Story** | `The fog thickens suddenly.` | Raw text added to the narrative — narrator voice |

Toggle with `/mode`.

---

## Setup

**Prerequisites:** Python 3.11+, conda (recommended), LM Studio or llama.cpp running locally.

```bash
conda create -n game-master python=3.11 -y
conda activate game-master
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` — at minimum set your server URL and model name:

```env
STORY_ENGINE_PROVIDER=local
STORY_ENGINE_LOCAL_BASE_URL=http://localhost:1234/v1   # LM Studio default
STORY_ENGINE_GAME_MASTER_MODEL=gemma-3-27b-it          # or your model name
```

For llama.cpp, change the port to `8080` (or whichever port you started it on). For OpenRouter see [Providers](#providers) below.

---

## Usage

### Starting a game

```bash
# Default scenario — The Ruins of Ashenveil (dark fantasy)
python -m my_code

# Explicit scenario file
python -m my_code scenarios/ashenveil.md

# Web UI (browser, served on port 7860)
python -m my_code --ui web
python -m my_code --ui web --port 8080   # custom port
```

On startup, the engine checks if your model supports vision (see [Using images](#using-images)), then streams the opening narration. If the scenario has no `[opening]` section the GM generates one.

---

### Web UI

The web UI runs as a FastAPI server you connect to from any browser on the same network — useful when your LLM server is on a Mac Mini or desktop and you want to play from a laptop or tablet.

```bash
# On the machine running the LLM server
python -m my_code --ui web

# Connect from any browser on the LAN
http://<host-ip>:7860
```

**Setup screen** — enter your LLM server URL, optional model override, and tick "Enable vision probe" if using a vision-capable model. The URL can point to a remote machine (`http://192.168.1.x:1234/v1`).

**Themes** — the `◑` button in the header cycles through system (follows OS) → dark → light. Preference is saved in `localStorage`.

**Inline edit** — double-click any GM response to edit it in place. A faint border appears, type your changes, then `Ctrl+Enter` to save or `Esc` to cancel. This updates the conversation history so subsequent GM turns read the edited version.

**Undo** — `↩ Undo` in the header removes the last player action and GM response from the conversation history, returning you to the previous state so you can try something different.

**Regen** — `↺ Regen` replays the same player action and generates a new GM response.

**Image attach** — visible when a vision-capable model is detected. Pick an image file, add a label describing what it represents in the scene, then send your action. A `🖼` note appears in the story showing what the vision model made of the image before the GM responds.

**Author's note** — editable in the sidebar, updates live. The text box is vertically resizable.

---

### Playing

Type what your character does and press Enter. You do not need to write "You" in action mode — it is added automatically.

```
[ACTION] > draw your sword and step through the archway

  The blade sang as it cleared the scabbard, the sound swallowed almost
  immediately by the fog. Beyond the archway the dark was absolute for
  three heartbeats — then Lyra's eyes adjusted and she saw the courtyard:
  cracked flagstones, a collapsed well, something that had once been a
  bonfire reduced to a black stain. And in the centre of it, turning
  slowly toward her, Brother Aldric.

  "I wondered when you would stop watching," he said.

[ACTION] > ask him what he is looking for

  Aldric turned fully now. In the failing light his expression was
  difficult to read — careful, she decided. Careful in the way a man
  is careful when he is choosing between two different lies.

  "The same thing you are, I expect," he said. "Answers."
```

Switch to story mode with `/mode` to write in the narrator's voice instead:

```
[STORY] > Three hours passed. Neither of them spoke much.
```

### In-game commands

All commands begin with `/` and are not sent to the GM.

| Command | Description |
|---|---|
| `/save [name]` | Save full game state to `saves/<name>.json`. Auto-names if omitted. |
| `/load [name]` | Restore a save. Omit name to list available saves. |
| `/regen` | Regenerate the last GM response — full rollback and re-run with the same player action. |
| `/edit` | Edit the last GM response inline. Enter replacement text, blank line to confirm, `/cancel` to abort. |
| `/memory` | Display the current memory block — key facts the GM tracks across turns. |
| `/note [text]` | Show or update the author's note. This is a tone/style directive injected near the end of the GM's context every N turns. |
| `/mode` | Toggle between **ACTION** (auto-prefixes "You") and **STORY** (free text) input modes. |
| `/img <path>` | Attach an image to your next action. Vision models only — see below. |
| `/export [name]` | Export the story narration as plain text to `exports/<name>.txt`. |
| `/help` | List all commands. |
| `/quit` | Exit. Prompts to save. |

A silent checkpoint is written to `saves/_checkpoint.json` after every turn automatically.

### Saving and loading

```
[ACTION] > /save before-the-confrontation
  Saved to before-the-confrontation.json.

[ACTION] > /load before-the-confrontation
  Loaded before-the-confrontation (turn 14, 28 messages).
```

Saves capture the full conversation history, memory block, author's note, world info entries, and story log. The session resumes exactly where it left off, with full context.

### Exporting the story

```
[ACTION] > /export ashenveil-session-1
  Exported to ashenveil-session-1.txt (22 turns).
```

Exports contain only the GM's narration turns — no system blocks, no player input — formatted as a readable prose document.

---

## Using images

Vision support lets you ground the GM's narration in real images — a painted scene, a character portrait, a hand-drawn map, a photo of an object. The engine uses the vision model to convert images to prose **once**, then discards the bytes. The GM only ever receives text.

Supported formats: PNG, JPG, WEBP, GIF. Paths can be absolute or relative to your working directory.

### Step 1 — load a vision model

In LM Studio, load a vision-capable model **with its mmproj file selected**. The mmproj is a separate file — without it the model cannot process images even if it is architecturally capable.

Models known to work well: Gemma 4 (any size), LLaVA 1.6, Llama 3.2 Vision, Qwen2-VL.

The engine probes vision capability automatically at startup:

```
Vision: enabled
```

If the mmproj was not loaded, you will see:

```
Vision: not available — model loaded without mmproj or text-only mode.
```

No configuration needed. To skip the probe, set `STORY_ENGINE_VISION_CAPABLE=true` or `false` in `.env`.

---

### Step 2 — add images to a scenario

Add `scene_image` to `[meta]` and/or `portrait` to any character section. Both are optional — the scenario loads normally without them.

```markdown
[meta]
title: The Ruins of Ashenveil
mode: interactive
pov: second-person
scene_image: images/ashenveil_ruins.jpg    ← path to your scene image

[character-1]
name: Lyra Voss
role: player-character
portrait: images/lyra.jpg                  ← path to character portrait
triggers: Lyra, she, Voss
description: ...
```

At startup, the engine calls the vision model once per image and bakes the resulting prose into the system prompt under `## Visual Reference`. From that point on the GM draws on these descriptions throughout the session without the images ever entering the turn-by-turn context.

```
Loading scenario: scenarios/ashenveil.md
Vision: enabled
Describing scene image: images/ashenveil_ruins.jpg
Describing portrait: Lyra Voss
```

---

### Step 3 — introduce images during play

Use `/img <path>` at any point during a game to attach an image to your next action. This is a two-step command — the engine asks you what the image represents in the scene before processing it.

```
[ACTION] > /img maps/old_map.jpg
  What does this represent in the scene?
> A tattered map you found in the ruins three days ago

  Processing image…
  Image understood — it will shape the next narration.

[ACTION] > pull out the map and show it to Aldric

  Lyra unfolded the parchment on the broken wall between them.
  The ink was faded but the markings were clear enough — a valley
  flanked by three peaks, a dotted path leading straight to where
  they now stood. Someone had written in the margins, in a script
  she did not recognise, and circled one of the peaks twice in red.

  Aldric went very still.
```

The label you provide ("a tattered map you found...") tells the vision model what role the image plays in the story, so the description it generates is grounded in your narrative context rather than a generic caption.

Ideas for mid-game images:
- A map or diagram your character discovers
- A portrait of an NPC you encounter
- An item, weapon, or artefact
- A location you want the GM to visualise

---

### How it works under the hood

```
/img maps/old_map.jpg
    │
    ├─ you label it: "a tattered map found in the ruins"
    │
    ├─ vision model: image + label → 2–3 sentence prose description
    │                (one API call, image bytes discarded after)
    │
    └─ next turn message:
           [MEMORY] ...
           [IMAGE CONTEXT]
           A weathered parchment map, three jagged peaks sketched in
           faded ink, a dotted trail winding toward ruins annotated
           in an unknown script. The corners are singed.
           ---
           pull out the map and show it to Aldric
```

The `[IMAGE CONTEXT]` block appears **only in that one turn**. After the GM responds it is cleared and never re-injected. If you want the image's details to persist beyond one turn, tell the GM to remember them (the GM may call `update_memory` automatically if the image reveals something significant).

---

## Scenarios

Scenarios are `.md` files with `[section]` markers. The included `scenarios/ashenveil.md` drops you into a dark fantasy confrontation at the entrance to forbidden ruins.

### File structure

| Section | Required | Description |
|---|---|---|
| `[meta]` | yes | `title`, `mode`, `pov`, `language`, `nsfw`, optional `scene_image` path |
| `[narrator-prompt]` | yes | GM identity, POV rules, NPC control rules |
| `[writing-style]` | yes | Prose style directives (tense, style, sensory focus) |
| `[world-info]` | yes | Global lore injected into every session |
| `[character-N]` | yes (≥1) | `name`, `role`, `triggers`, `description`, `personality`, `backstory`, `speech_style`, optional `portrait` path |
| `[scene-setup]` | no | Location, time, atmosphere |
| `[scenario]` | yes | Background baked into the system prompt |
| `[memory]` | no | Initial memory block — mutable key facts injected every turn |
| `[opening]` | no | GM's first narration; auto-generated if absent |
| `[author-note]` | no | `depth: N` (inject every N turns, 0 = every turn) and `content` |

Character `role` values: `player-character` | `npc` | `antagonist` | `neutral`

### Writing your own scenario

Minimum required sections — everything else is optional:

```markdown
[meta]
title: The Dockside Job

[narrator-prompt]
You are a Game Master running a gritty noir mystery in second person, present tense.
You control all characters except Detective Mara Cole. Never break character.
When the player attempts something risky, use roll_dice first, then narrate the result.

[writing-style]
Hardboiled. Short sentences. Dialogue-heavy. Sensory details — rain, cigarettes,
cheap coffee. Show don't tell.

[world-info]
Port Carrow is a rain-soaked city. Corrupt police, smuggling rings, a mayor who
asks no questions. No magic — just people doing terrible things for money.

[character-1]
name: Mara Cole
role: player-character
triggers: Mara, she, Cole, the detective
description: Forty-two, ex-cop turned private investigator. Tired eyes, good instincts.
personality: Cynical but fair. Gets attached to cases she shouldn't.
backstory: Left the force after her partner was killed and the department buried it.
speech_style: Dry one-liners. Doesn't ask twice.

[scenario]
A shipping magnate's daughter has gone missing. The police aren't looking.
Mara has been hired by the mother. Last known sighting: the Red Anchor tavern,
two nights ago.

[memory]
Player: Mara Cole, private investigator, armed with a .38 revolver.
Case: Elena Voss, 24, missing two days. Mother hired Mara.
Last seen: Red Anchor tavern on the docks.
```

**Triggers and World Info:** the `triggers` field controls when a character's full card is re-injected into the turn context. List every keyword that might naturally appear when that character is present — names, pronouns, nicknames, titles. The engine scans both player input and the GM's last response.

**Author's note:** use `depth: 0` to inject every turn, or a higher number for periodic injection. Useful for genre reminders, pacing control, or keeping the GM on track mid-session.

---

## GM tools

The GM has access to these tools and calls them autonomously mid-narration:

| Tool | When the GM uses it |
|---|---|
| `roll_dice("2d6+3")` | Skill checks, combat, chance events — standard NdS+M notation |
| `update_memory(content)` | Key facts change: character state, items gained, secrets revealed |
| `update_authors_note(content)` | Scene tone needs to shift: ramp tension, signal genre change |
| `add_world_info_entry(keyword, content)` | New lore established during play that should persist |

The GM decides when to use these — you do not need to prompt it. You can see the current memory state at any time with `/memory`.

---

## Providers

| Provider | `STORY_ENGINE_PROVIDER` | Notes |
|---|---|---|
| LM Studio / llama.cpp | `local` | Default. OpenAI-compatible endpoint. |
| OpenRouter | `openrouter` | Requires `OPENROUTER_API_KEY`. |

Both providers use the OpenAI-compatible chat completions API with streaming and function calling. The vision probe and `/img` command work with both.

**Model recommendations for local play:**

- Any instruction-tuned GGUF model works. Narrative or roleplay fine-tunes give better prose.
- For vision: load a model with its mmproj in LM Studio (Gemma 4, LLaVA 1.6, Llama 3.2 Vision).
- Larger context windows (32k+) allow longer sessions without losing early context.

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `STORY_ENGINE_PROVIDER` | `local` | `local` \| `openrouter` |
| `STORY_ENGINE_LOCAL_BASE_URL` | `http://localhost:1234/v1` | LM Studio or llama.cpp server URL |
| `STORY_ENGINE_GAME_MASTER_BASE_URL` | (falls back to LOCAL) | Override base URL for the GM role only |
| `STORY_ENGINE_GAME_MASTER_MODEL` | `default` | Model name. `default` lets the server choose. |
| `STORY_ENGINE_SYSTEM_SUFFIX` | (empty) | Text appended to every system prompt |
| `STORY_ENGINE_VISION_CAPABLE` | (auto-probe) | `true` or `false` to skip the startup vision probe |
| `OPENROUTER_API_KEY` | — | Required for OpenRouter provider |

---

## Architecture

```
my_code/
├── main.py              # Arg parsing → parse_scene_file → run_adventure (--ui terminal/web)
├── parser.py            # .md scenario file → AdventureScene dataclass
├── game_loop.py         # Owns messages list, tool dispatch, turn loop, /regen, /edit
├── agents/
│   └── game_master.py   # TOOL_SCHEMAS, system prompt builder, lore injection, turn message
├── tools/
│   ├── dice_tools.py    # roll_dice — standard NdS+M notation
│   └── lore_tools.py    # Pure Python keyword scanning helpers
├── models/
│   ├── provider.py      # get_client() → (AsyncOpenAI, model_id)
│   └── data_models.py   # AdventureScene, GameState (snapshot/restore), CharacterCard, WorldInfoEntry
├── vision/
│   ├── probe.py         # Startup vision capability check
│   └── describer.py     # Image → prose description (one call, bytes discarded after)
└── ui/
    ├── terminal.py      # Rich streaming display, prompts, panels
    ├── web.py           # FastAPI app — SSE streaming, session state, REST API
    └── static/
        └── index.html   # Single-file browser client (themes, inline edit, undo, image attach)
```

**Turn data flow:**

```
player input
    │
    ├─ /img <path> ──→ describe_image() ──→ state.pending_image_context
    │
    └─ build_turn_message()
           [MEMORY]
           [WORLD CONTEXT]   ← keyword-triggered character cards + world info entries
           [IMAGE CONTEXT]   ← from /img, this turn only, then discarded
           [AUTHOR'S NOTE]   ← every N turns
           --- player action
               │
               └─ _stream_gm() → streamed prose to terminal
                       │
                       ├─ tool calls (roll_dice / update_memory / ...)
                       │   dispatched inline → GameState updated directly
                       └─ final text response appended to messages list
```

**Conversation history** is a plain `list[dict]` (OpenAI message format) owned entirely by `game_loop.py`. The system prompt is passed separately each call, not stored in the list. This means saves are `json.dumps(messages)` and editing/regen is a list slice — no framework unwrapping required.

**Regen** works by taking a shallow copy of `messages` and `state.snapshot()` before each GM call. `/regen` restores both and re-runs the same turn message, giving a fresh response with full rollback of any tool mutations.

**Lore injection** runs entirely in Python — `_build_world_context()` scans the player's input and the GM's last response for character trigger keywords and custom world info entry keywords, injecting matching cards with no LLM call.

**Vision pipeline** — images enter the engine in two ways. Startup images (`scene_image`, `portrait`) are described once and injected as `## Visual Reference` in the system prompt. Mid-game images (`/img`) are described during the command, injected as `[IMAGE CONTEXT]` in the next turn message, and cleared immediately after. In both cases the GM model receives only prose — never raw image bytes.
