# faaltoo chat

A zero-friction local LLM chat launcher. Pick a few dimension chips — archetype, mood, talk-type — and jump straight into a conversation. No character cards, no world-building, no setup faff.

---

## How it works

Instead of writing persona files, you select from short dimension menus. The selections compile into a minimal system prompt and the LLM self-generates its name, backstory, speech style, and behavior.

**Required dimensions** (must pick all three to start):
- **Archetype** — Best Friend, Mentor, Rival, Sibling, Crush, Wise Elder, Stranger on Train
- **Energy / Mood** — Chill, Hyper, Grumpy, Melancholic, Excited, Sleepy
- **Talk-Type** — Timepass, Deep Talk, Roast, Gossip, Rant Mode, Debate, Teach Me, Advice

**Optional dimensions** (add richness):
- Region / Culture, Domain / Passion, Language Style, Relationship Familiarity, Situational Context, Emotional Need

**Content level** — Strict / Medium / No Control (appended to the system prompt).

**Response length** — five levels (Brief · Short · **Medium** · Long · Extended) mapping to 150 / 350 / 700 / 1400 / 2800 tokens. Change it any time before sending — takes effect on the very next response.

**Automatic conversation memory** — every few turns, a silent background call extracts key facts (names, clothing, preferences, relationships, events) and merges them into the system prompt. Fully automatic, invisible to the user, and O(1) cost per cycle — only the new turns since the last extraction are sent each time.

---

## Quickstart

```bash
# Install dependencies
conda activate strandsagents
pip install -r requirements.txt

# Copy env and set your LLM server
cp .env.example .env
# Edit .env: set FAALTOO_LOCAL_BASE_URL to your LM Studio / llama.cpp server

# Launch web UI (default)
python -m my_code

# Custom host/port
python -m my_code --host 0.0.0.0 --port 8080

# Terminal mode
python -m my_code --ui terminal

# Terminal with a preset
python -m my_code --ui terminal --preset "Chai Break"
```

Open **http://localhost:7860** in your browser.

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `FAALTOO_PROVIDER` | `local` | `local` or `openrouter` |
| `FAALTOO_LOCAL_BASE_URL` | `http://localhost:1234/v1` | LM Studio / llama.cpp / Ollama endpoint |
| `FAALTOO_MODEL` | `default` | Model name (leave as `default` for llama.cpp) |
| `FAALTOO_VISION_MODEL` | *(same as FAALTOO_MODEL)* | Separate vision model if needed |
| `FAALTOO_TEMPERATURE` | `0.85` | Generation temperature (0.0–2.0). Only affects bot responses, not memory extraction. |
| `OPENROUTER_API_KEY` | — | Required only for `openrouter` provider |

---

## Web UI features

| Feature | How |
|---|---|
| Pick persona | Chip grid on setup screen |
| Built-in presets | Preset strip — click to load |
| Save your own preset | Pick chips → **＋ Save as Preset** |
| Edit / delete user presets | ✎ / ✕ buttons on user preset chips |
| Response length | Sidebar: Brief / Short / **Medium** / Long / Extended |
| Regen last response | **↺ Regen** button |
| Undo last turn | **↩ Undo** button |
| Edit bot response | Double-click any bot message |
| Attach image (vision) | 📎 clip button (appears if vision probe passes) |
| Export chat | **Export** button → downloads `chat.txt` |
| New chat | **New Chat** → back to setup screen |
| Theme | ◑ cycles system / dark / light |
| Font size | A- / A / A+ buttons |
| Resizable sidebar | Drag the border between chat and sidebar — width is saved across sessions |
| Auto Chat | Checkbox near Send — LLM drives both sides of the conversation (see below) |

---

## Auto Chat

Auto Chat lets the LLM drive both sides of the conversation — the user side is generated turn by turn, typed into the input bar with a realistic animation, and sent through the normal streaming path.

**Starting:** tick the **Auto** checkbox (web) or type `/auto` (terminal). Works from turn 1 or mid-conversation.

**Stopping:**
- Click the textarea (web) — unticks Auto, restores manual mode instantly
- Press Ctrl+C (terminal)
- Type `/auto` again (terminal)
- Context fills to ~80%
- Both sides have clearly signalled they are done — detected via a lightweight LLM call, works in any language, covers warm farewells and cold/tense endings alike

**Image in auto mode:** attach an image and label before ticking Auto — the user-side generator is told about the pending image and writes a message that naturally references it. The image is included in the first auto turn, then cleared.

**How the user side is generated:** a small non-streaming call (max 120 tokens) asks the model to write the next natural user message. It is instructed not to repeat topics already covered, not to rush toward a conclusion, and to vary style turn by turn.

---

## Terminal features

```
/regen          — regenerate last response
/undo           — undo last turn
/auto           — toggle auto chat (LLM drives both sides; Ctrl+C to stop)
/tokens <level> — set response length: brief|short|medium|long|extended (or 150–2800)
/export [name]  — save chat to exports/name.txt
/img <path>     — attach image (vision models only)
/help           — show commands
/quit           — exit
```

---

## API endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/dimensions` | Dimension data, built-in presets, user presets, user-added options |
| `POST` | `/api/dimensions/{dim_key}` | Add a custom option to a dimension |
| `DELETE` | `/api/dimensions/{dim_key}/{value}` | Remove a user-added dimension option |
| `DELETE` | `/api/dimensions` | Clear all user-added dimension options |
| `POST` | `/api/presets` | Save a new user preset |
| `PUT` | `/api/presets/{name}` | Rename or update a user preset |
| `DELETE` | `/api/presets/{name}` | Delete a user preset |
| `POST` | `/api/start` | Start a session (selections, nsfw_level, server_url, model, vision) |
| `POST` | `/api/chat` | Send a message — SSE stream |
| `POST` | `/api/regen` | Regenerate last response — SSE stream |
| `POST` | `/api/undo` | Undo the last turn |
| `POST` | `/api/edit` | Edit the last bot message in place |
| `GET` | `/api/export` | Download full chat as plain text |
| `POST` | `/api/reset` | Clear session and return to setup |
| `POST` | `/api/auto/user-turn` | Generate next user-side message for auto chat |

### `/api/chat` form fields

| Field | Type | Default | Description |
|---|---|---|---|
| `text` | string | — | User message (required) |
| `image` | file | — | Optional image attachment |
| `image_label` | string | `""` | Label / description hint for the image |
| `max_tokens` | int | `700` | Max tokens for this response (clamped 150–2800) |

### `/api/auto/user-turn` JSON body

| Field | Type | Default | Description |
|---|---|---|---|
| `has_image` | bool | `false` | Whether a pending image is attached |
| `image_label` | string | `""` | Label of the pending image |

Returns `{"text": "..."}` with the generated message, or `{"goodbye": true}` if both sides have clearly signalled they are done.

### SSE event types

| Event | Payload | Description |
|---|---|---|
| `user` | `{text}` | Echo of the user message |
| `image_desc` | `{text}` | Image description (vision turns only) |
| `chunk` | `{text}` | Streamed bot token |
| `regen` | — | Regen starting |
| `state` | `{turn_count, vision_capable, ctx_pct}` | Updated session state |
| `done` | — | Stream complete |
| `error` | `{message}` | Error occurred |

---

## Project structure

```
faaltoo-chat/
├── my_code/
│   ├── __main__.py        — entry point (--ui, --host, --port, --preset)
│   ├── dimensions.py      — dimension data + built-in presets
│   ├── prompt_builder.py  — selections + NSFW level → system prompt
│   ├── chat_loop.py       — streaming bot call, auto chat logic, terminal run loop
│   ├── vision.py          — vision probe + image description
│   ├── models/
│   │   ├── data_models.py — ChatSession dataclass
│   │   └── provider.py    — LLM client factory (local / openrouter)
│   └── ui/
│       ├── terminal.py    — Rich terminal UI + dimension picker
│       ├── web.py         — FastAPI app (all endpoints)
│       └── static/
│           └── index.html — single-page web UI
├── exports/               — exported chat transcripts
├── user_presets.json      — saved presets (auto-created)
├── user_dimensions.json   — custom dimension options (auto-created)
├── dev_commands.txt       — dev notes: debug endpoints, temperature, token tuning
├── .env.example
└── requirements.txt
```

---

## Sibling apps

This app lives alongside **chat-engine**, **story-engine**, and **game-master** in the same repo. It shares the same provider/model pattern (`models/provider.py`) and is intentionally the lightest of the four — no scenario files, no agent tools, no multi-character orchestration. Just fast chat.
