# video-subtitle-cruncher

Turn a video — or a live region of your screen — into a rich, queryable context by
combining **what was said** (captions/ASR) with **what was shown** (deduplicated
keyframes described by a vision model). Then generate summaries, detailed
write-ups, chapter lists, or ask questions — now or weeks later, without ever
reprocessing the source.

**Fully local.** Vision and text generation run against your own OpenAI-compatible
endpoint (llama-server, LM Studio, omlx — e.g. Qwen 3.6 / Gemma 4 vision models).
ASR is local faster-whisper. Nothing leaves your machine.

```
source (video file | screen region)
   │  sample ~1 fps
   ▼
perceptual dedup (phash + colorhash, caption band masked)
   │                                    ┌─ burned-in CC read off frames (preferred)
   ▼                                    │  or local ASR (video files with audio)
keyframes {t, image}  +  transcript ────┘
   │
   ▼  vision model describes each keyframe (± transcript window)
timeline.json  ── durable, re-queryable ──▶  summarize | chapters | detailed | ask
```

## Install

Requires: Python ≥ 3.11, `ffmpeg`/`ffprobe` on PATH, and a local vision model
served over an OpenAI-compatible endpoint.

```bash
conda create -n cruncher python=3.12
conda activate cruncher
pip install -e '.[asr]'        # [asr] pulls in faster-whisper; omit if CC-only
```

Point the tool at your model server once via environment variables (or pass
`--base-url` / `--model` per command):

```bash
export CRUNCH_BASE_URL=http://192.168.1.2:7890/v1
export CRUNCH_MODEL=google/gemma-4-26b-a4b-qat
```

macOS screen recording: grant your terminal **Screen Recording** permission
(System Settings → Privacy & Security) or captures come out black.

## Quickstart

### From a video file

```bash
crunch snapshot lecture.mp4                 # phase 1: keyframes + transcript
crunch describe lecture                     # phase 2: vision timeline
crunch summarize lecture --style short      # phase 3: outputs
crunch summarize lecture --style chapters
crunch ask lecture "what did they conclude about X?"
```

### From the screen (e.g. a video you can watch but not download)

1. Turn **CC on** in the player — burned-in captions are the transcript source
   for screen recordings (there's no audio channel to fall back on).
2. Find the player region: hover the video's top-left corner with `Cmd-Shift-4`
   and note X,Y; hover the bottom-right for X2,Y2; then W=X2−X1, H=Y2−Y1.
   (Press Esc — don't take the shot.)
3. Start playback, then:

```bash
crunch record --region 15,190,1020,575 --interval 1 --name mytalk
# ... watch the video; Ctrl-C when it ends (or pass --duration 1800)
crunch describe mytalk
crunch summarize mytalk
```

### Web UI (for the inference phases)

Everything that talks to the model — describe, summarize, ask — is also
available in a local browser UI:

```bash
crunch web                    # http://127.0.0.1:8765
```

Set the endpoint and model at the top (**load models** pulls the id list from
the server; settings persist in the browser), pick a job in the sidebar, then
run **describe → summarize / ask**. Past outputs show as tabs per job, with
keyframe images rendered inline in detailed write-ups. Capture (`snapshot`,
`record`) stays on the CLI.

The UI sits on a small JSON API (usable directly, e.g. from scripts):

| Endpoint | Does |
|---|---|
| `GET /api/jobs` | Job library + configured defaults |
| `GET /api/models?base_url=` | Proxy the runtime's `/models` list |
| `POST /api/describe` | `{job, base_url, model, window?}` → build timeline |
| `POST /api/summarize` | `{job, style, base_url, model}` → saved markdown |
| `POST /api/ask` | `{job, question, base_url, model}` → answer |
| `GET /api/output?job=&file=` | Read a saved output |
| `GET /frames/<job>/<file>` | Keyframe JPEGs |

The server binds to `127.0.0.1` by default; it has no auth, so only use
`--host 0.0.0.0` on a network you trust.

### Coming back later

Jobs are a durable library — the expensive work (sampling, dedup, vision
descriptions) runs once; every later request just re-reads `timeline.json`:

```bash
crunch list
crunch summarize mytalk --style detailed    # weeks later, no reprocessing
crunch ask mytalk "which stocks were mentioned?"
```

Outputs are timestamped in `jobs/<name>/outputs/` and accumulate — earlier
answers are never overwritten.

## Commands

| Command | What it does |
|---|---|
| `crunch snapshot <video>` | Sample at `--fps` (default 1), dedup, acquire transcript (CC → ASR) |
| `crunch record` | Same, but sampling a live screen region at `--interval` seconds |
| `crunch pick` | Drag-select a region, print its `X,Y,W,H` *(known issue on some macOS setups — see below)* |
| `crunch describe <job>` | Vision-describe each keyframe with its ±`--window`s transcript context |
| `crunch summarize <job>` | `--style short` (default) \| `detailed` \| `chapters` |
| `crunch ask <job> "<question>"` | Q&A over the stored timeline, cites timestamps |
| `crunch list` | Show the job library |
| `crunch web` | Browser UI for describe/summarize/ask (`--host`, `--port`, default 8765) |

Common flags: `--base-url`, `--model` (or the `CRUNCH_*` env vars),
`--jobs-dir` (default `./jobs`), `--force` (redo an existing job),
`--keep-samples` (retain raw samples for debugging).

Tuning flags for phase 1: `--threshold` (phash hamming distance for "new
frame", default 8 — raise for talking-head video, lower for slide decks),
`--long-edge` (downscale size, default 1024), `--no-cc`, `--no-asr`,
`--asr-model` (faster-whisper size, default `small`).

## How it works

**Dedup** — every sample gets a structural hash (phash) *and* a color hash; a
frame is a duplicate only if it's close to a recently-kept frame on **both**
(phash alone misses color-only scene changes). Comparison runs against the last
3 kept frames so a brief cut back to a previous shot doesn't re-admit it.

**Burned-in captions (CC)** — a few probe frames are shown to the vision model
to detect a caption band (bottom/top). If found:
- the band is **masked before hashing**, so caption changes don't defeat dedup;
- the band crop of each sample is read by the vision model, gated by a crop
  hash — the model is only called when the caption actually changed (a
  60s recording typically costs a handful of vision calls);
- **rolling captions** (YouTube-style scrolling) are stitched by suffix/prefix
  overlap so the transcript reads as continuous speech;
- **static on-screen text** that leaks into the band (slide lines, watermarks)
  is detected — a stable beginning across readings whose tails differ — and
  stripped.

**ASR fallback** — video files with audio and no detected captions are
transcribed with faster-whisper.

**Descriptions** — cached by phash in `descriptions.json`; re-running
`describe` is free for frames the model has already seen, across `--force`
re-runs of the same content.

**Outputs** — the timeline + transcript become one context document; long
videos are condensed in time-ordered chunks first (map-reduce) before the
final generation pass.

## Job directory layout

```
jobs/<name>/
  manifest.json       # source, settings, phase status, kept-frame index
  frames/             # keyframes named by timestamp: 000123.45.jpg
  transcript.json     # {"source": "cc"|"asr"|"none", "segments": [...]}
  descriptions.json   # phash -> vision description cache
  timeline.json       # the artifact everything downstream reads
  outputs/            # short-*.md, detailed-*.md, chapters-*.md, qa-*.md
```

Everything is plain JSON + JPEG — inspectable, resumable, no database.

## Tips & known issues

- **Screen recordings: CC on, region tight.** Aim the region at the video
  player rectangle only — page headers/controls waste pixels and add noise.
  The player's top edge is usually *below* the site's own header.
- **Start playback before `crunch record`** — the first captures happen
  immediately, so whatever is frontmost at t=0 lands in the job.
- **`crunch pick` overlay** renders opaque black instead of a transparent dim
  on some macOS setups (Tk alpha quirk) — use the two-corner `Cmd-Shift-4`
  method above until this is reworked.
- **Sidecar `.srt`/`.vtt` files are deliberately not parsed** (yet) — CC and
  ASR cover the target use cases with one output shape.

## Roadmap

- **M4 — continuous screen tracking:** rolling capture with retention policy,
  active-app context, daily "what did I do?" digests, privacy exclusion list.
- Cross-job semantic search over descriptions ("which video showed that
  architecture diagram?").
- Native region picker to replace the Tk overlay.

See `PLAN.md` for the full design.
