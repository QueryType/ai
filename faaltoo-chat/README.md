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

**Content level** — Strict / Medium / No Control (appends instructions to the system prompt).

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
| `OPENROUTER_API_KEY` | — | Required only for `openrouter` provider |

---

## Web UI features

| Feature | How |
|---|---|
| Pick persona | Chip grid on setup screen |
| Built-in presets | Preset strip — click to load |
| Save your own preset | Pick chips → **＋ Save as Preset** button appears |
| Edit / delete user presets | ✎ / ✕ buttons on user preset chips |
| Regen last response | **↺ Regen** button |
| Undo last turn | **↩ Undo** button |
| Edit bot response | Double-click any bot message |
| Attach image (vision) | 📎 clip button (appears if vision probe passes) |
| Export chat | **Export** button → downloads `chat.txt` |
| New chat | **New Chat** button → back to setup screen |
| Theme | ◑ cycles system / dark / light |
| Font size | A- / A / A+ buttons |

---

## Terminal features

```
/regen         — regenerate last response
/undo          — undo last turn
/export [name] — save chat to exports/name.txt
/img <path>    — attach image (vision models only)
/help          — show commands
/quit          — exit
```

---

## Project structure

```
faaltoo-chat/
├── my_code/
│   ├── __main__.py        — entry point (--ui, --host, --port, --preset)
│   ├── dimensions.py      — all dimension data + built-in presets
│   ├── prompt_builder.py  — compiles selections + NSFW level → system prompt
│   ├── chat_loop.py       — streaming bot call + terminal run loop
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
├── user_presets.json      — your saved presets (auto-created)
├── .env.example
└── requirements.txt
```

---

## Sibling apps

This app lives alongside **chat-engine**, **story-engine**, and **game-master** in the same repo. It shares the same provider/model pattern (`models/provider.py`) and is intentionally the lightest of the four — no scenario files, no agent tools, no multi-character orchestration. Just fast chat.
