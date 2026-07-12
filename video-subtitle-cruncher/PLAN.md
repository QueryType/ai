# Video Subtitle Cruncher — Plan

Turn a video (and later, a live screen) into a rich, queryable context by combining
**what was said** (transcript/subtitles) with **what was shown** (deduplicated frames +
vision descriptions), then generate summaries, detailed write-ups, or answers on demand.

## Core idea

```
                ┌──────────────── SNAPSHOT PHASE ────────────────┐
Video file ──▶  frame sampler ──▶ perceptual dedup ──▶ keyframes │
  (later:       (1 fps / scene    (pHash + hamming    {t, image} │
   screen)       change)           threshold)                    │
                └────────────────────────────────────────────────┘
Transcript ▶  transcript segments {t_start, t_end, text}
(burned-in CC
 read from frames,
 else local ASR)
                ┌──────────────── CONTEXT PHASE ─────────────────┐
                │ align frames ↔ transcript by timestamp         │
                │ vision model describes each keyframe           │
                │ → timeline.json: [{t, frame, vision_desc,      │
                │                    transcript_window}]         │
                └────────────────────────────────────────────────┘
                ┌──────────────── OUTPUT PHASE ──────────────────┐
                │ user request → short summary | detailed        │
                │ write-up | chapter list | Q&A over timeline    │
                └────────────────────────────────────────────────┘
```

Design constraint from day one: **the pipeline must not care where frames come from.**
A `FrameSource` abstraction lets Phase 4 (screen tracking) reuse everything except capture.

## Data model

One working directory per job:

```
jobs/<video-name>/
  frames/           # kept keyframes: 000123.45.jpg (timestamp in name)
  manifest.json     # source info, settings, phase status (resumable)
  transcript.json   # [{start, end, text}]
  timeline.json     # [{t, frame, phash, vision_desc, transcript_window}]
  outputs/          # generated summaries / write-ups
```

Everything is plain JSON + JPEGs — inspectable, resumable, no DB needed initially.
(SQLite becomes worth it in Phase 4 when screen tracking runs continuously.)

## Phase 1 — Snapshotting (frames + transcript)

**Frame extraction** (`ffmpeg` via subprocess):
- Default: sample at ~1 fps (configurable). Alternative mode: ffmpeg scene-change
  filter (`select='gt(scene,0.3)'`) for talking-head videos where 1 fps is wasteful.
- Downscale on extraction (e.g. long edge 1024–1568 px) — enough for vision models,
  keeps disk and token cost sane.

**Dedup** (the "if similar, discard" step):
- Perceptual hash each sampled frame (`imagehash.phash` or `dhash`).
- Keep a frame only if hamming distance to the *last kept* frame > threshold
  (start at 6–8, make it a CLI flag; tune per content type — slides vs camera footage).
- Comparing against last-kept (not all kept) is O(n) and matches the temporal nature
  of video; optionally also compare against last N kept to catch A→B→A flicker.

**Transcript acquisition — two local sources, burned-in CC preferred:**

1. **Burned-in captions (CC overlaid on the video)** — many videos render the
   transcript directly onto the frames. When present, that's the highest-fidelity
   source and it's already in the pixels we're sampling:
   - *Detect*: probe a handful of frames spread across the video; ask the vision
     model "is there a caption/subtitle band? where?" If yes, note the region.
   - *Extract*: crop the caption band from each sampled frame (pre-dedup, so ~1 fps —
     captions change faster than scenes) and have the vision model read it.
     Collapse consecutive identical/overlapping caption texts into segments with
     start/end timestamps → `transcript.json`.
   - *Interplay with frame dedup*: when CC mode is on, **mask the caption band
     before computing the phash**, otherwise caption changes make visually-identical
     scenes look "different" and defeat the dedup.
2. **Local ASR fallback** — no caption band detected: extract audio with `ffmpeg`,
   transcribe with `faster-whisper` (or whisper.cpp), keep segment timestamps.

Deliberately **not** handling sidecar `.srt`/`.vtt` or embedded subtitle streams —
one output shape (`transcript.json`) keeps downstream simple, and subtitle-file
parsers can be added later as alternate producers if ever needed.

Deliverable: `frames/` + `transcript.json` + resumable `manifest.json`.
CLI: `crunch snapshot <video> [--fps 1] [--threshold 8]`.

## Phase 2 — Context building (vision + alignment)

**Alignment:** for each kept frame at time *t*, attach the transcript window
[t − 15s, t + 15s] (configurable). This pairs "what the screen showed" with
"what was being said about it".

**Vision descriptions:** send each keyframe (+ its transcript window as grounding)
to a vision model, ask for a dense factual description: visible text (OCR-ish),
diagrams, UI elements, code on screen, charts. Cache results keyed by phash so
re-runs are free.

**Provider layer — fully local.** Current-generation local vision models
(Qwen 3.6, Gemma 4) have very capable image recognition and on-screen-text reading —
good enough for both frame description and reading burned-in captions. All runtimes
speak (or can be wrapped in) an OpenAI-compatible chat endpoint, so one HTTP client
covers them:

| Runtime | Notes |
|---|---|
| `llama-server` | GGUF vision models (Qwen 3.6 / Gemma 4 — mmproj required alongside the GGUF); OpenAI-compat `/v1/chat/completions` with image content parts |
| LM Studio | Same OpenAI-compat endpoint on `localhost:1234`; easy model switching |
| omlx / MLX | Apple-silicon native; vision support has improved and is a first-class option on this machine |

One `VisionProvider` implementation targeting the OpenAI-compat API, configured by
`base_url` + `model` (config file / CLI flags). No cloud APIs — everything stays on
the machine, which also makes the Phase 4 screen-tracking privacy story trivial.
The same endpoint config is reused for the text-generation step in Phase 3.

Deliverable: `timeline.json` — the single artifact all outputs are built from.
CLI: `crunch describe <job> [--base-url ...] [--model ...]`.

## Phase 3 — Output generation & re-querying

**Jobs are a durable library, not a one-shot run.** Snapshotting and vision
description are the expensive steps; they run once and their results live in the
job directory indefinitely. The user can come back days later and ask for something
different — a summary today, a detailed write-up tomorrow, a specific question next
week — and only the cheap generation step re-runs against the stored `timeline.json`.

- `crunch list` — show processed jobs (name, duration, date, which outputs exist).
- Every output command takes a job name and works purely off stored artifacts;
  nothing re-decodes the video.
- Each generated output is saved to `outputs/` with a timestamped name, so earlier
  answers are kept, not overwritten.
- Later (exploratory, likely with Phase 4): embed the vision descriptions +
  transcript windows for semantic search across *all* jobs ("which video showed
  that architecture diagram?"). Not needed for M3 — plain full-context or
  map-reduce prompting over one job comes first.

Inputs: `timeline.json` + user request. Outputs written to `outputs/`.

- **Short summary** — one-pass if the timeline fits in context.
- **Detailed write-up** — section per detected "scene cluster" (runs of frames with
  similar phash / topic), preserving figures: embed or reference the actual frames
  in a Markdown output so the write-up shows the key visuals, not just text.
- **Chapters** — timestamped chapter list (useful for lectures/tutorials).
- **Q&A** — `crunch ask <job> "question"` over the timeline.

For long videos: map-reduce — summarize per 10-minute chunk, then combine.
The synthesis prompt should explicitly instruct the model to weave *both* channels:
"the speaker said X while the screen showed Y".

CLI: `crunch summarize <job> [--style short|detailed|chapters]`, `crunch ask <job> <q>`.

**Web UI (built):** `crunch web` serves a local browser UI over exactly these
inference phases — endpoint/model settings (model list proxied from the runtime),
job sidebar, describe / summarize / ask, and a tabbed viewer for accumulated
outputs with keyframes rendered inline. Stdlib `http.server` + one self-contained
HTML file, no new dependencies, no CDN assets. Capture stays on the CLI.

## Phase 4 — Screen tracking extension

**Partially pulled forward:** `crunch record` (region screen capture → same
dedup/CC pipeline) already exists — built for the "video I can't download, only
watch" case (e.g. YouTube with CC on: play it, record the player region, captions
are read off the screen). What remains for Phase 4 proper is the *continuous*
tracking mode below.

Same pipeline, new source:

- `ScreenSource` implements `FrameSource`: capture via `mss` every N seconds
  (macOS: needs Screen Recording permission). Screens are mostly static, so the
  phash dedup from Phase 1 discards ~95%+ of captures unchanged.
- No transcript channel by default; optional: active app/window title
  (via `NSWorkspace` / `osascript`) as the "transcript" analog — cheap and very
  useful for grounding ("what app was this?").
- Continuous operation changes storage: rolling SQLite index of kept frames,
  retention policy (e.g. keep frames 7 days, keep vision descriptions forever).
- Outputs: "what did I do today?" digest, "when did I last see X?" search over
  vision descriptions.
- **Privacy is a feature**: everything is local already (capture, vision, storage),
  so the remaining controls are an exclusion list of apps/window titles never
  captured (password managers, banking) and a pause hotkey.

## Project structure

As built:

```
video-subtitle-cruncher/
  pyproject.toml
  cruncher/
    snapshot.py     # ffprobe/ffmpeg sampling + phash+colorhash dedup (band-masked)
    screen.py       # mss region capture → same sample shape as snapshot
    pick.py         # tk drag-select region picker (known broken on some macOS)
    transcript.py   # burned-in CC: band detect, crop-hash gating, rolling-caption
                    #   merge, static-prefix strip; faster-whisper ASR fallback
    timeline.py     # phase 2: descriptions (phash-cached) + transcript windows
    generate.py     # phase 3: summaries / write-ups / chapters / Q&A (map-reduce)
    provider.py     # OpenAI-compat client (llama-server / LM Studio / omlx)
    manifest.py     # Job dirs + manifest handling
    web.py          # `crunch web`: stdlib HTTP server + JSON API over phases 2–3
    webui.html      # single-file browser UI (no external assets)
    cli.py          # crunch <command>
  jobs/             # gitignored, durable job library
```

Dependencies: `ffmpeg` (system), `imagehash`, `Pillow`, `httpx`, `mss`;
optional extra `[asr]` → `faster-whisper`.

## Milestones

1. ✅ **M1 — Snapshot:** video in → deduped keyframes + transcript out; plus
   `crunch record` (screen region capture) pulled forward from M4.
2. ✅ **M2 — Timeline:** vision descriptions + alignment → `timeline.json`
   (verified on real YouTube screen recordings, Gemma 4 over LM Studio).
3. ✅ **M3 — Outputs & re-query:** summary / detailed / chapters / ask + `crunch list`;
   `crunch web` adds a local browser UI over the same inference phases.
4. **M4 — Screen tracking:** continuous capture, rolling store, daily digest,
   privacy controls. *(Remaining.)*

## Open questions — resolved during M1–M3

- **Dedup:** phash alone missed color-only scene changes → duplicate requires
  closeness on *both* phash (threshold 8, `--threshold`) and colorhash; compare
  against the last 3 kept frames.
- **Detailed write-ups embed frames inline** (`![frame](frames/...)`) — confirmed;
  the web UI renders them.
- **CC extraction cost:** solved with crop-hash gating — dhash the caption crop and
  call the vision model only when it changes (~3 calls per 24–73 samples in practice).
- **Model/runtime default:** Gemma 4 (`google/gemma-4-26b-a4b-qat`) over an
  OpenAI-compat endpoint; others remain one `--base-url`/`--model` away. A formal
  Qwen 3.6 bake-off is still pending.

## Still open (for M4)

- Phase 4 capture cadence vs battery/CPU on laptops (probably 5–10 s, event-driven later).
- Replacement for the Tk region picker (renders opaque black on some macOS setups).
