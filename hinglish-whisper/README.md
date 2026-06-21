# hinglish-whisper

Local inference for [Trelis/whisper-hinglish-preview](https://huggingface.co/Trelis/whisper-hinglish-preview) — a whisper-large-v3 model fine-tuned for Hinglish (Hindi-English code-switched) speech recognition.

## Performance

| Task | This Model | whisper-large-v3 |
|---|---|---|
| Hinglish — CoSHE-500 | **13.67% WER** | 29.74% |
| Pure Hindi — Common Voice | **12.86% WER** | — |
| English — FLEURS-en | **6.93% WER** | — |

## Setup

```bash
conda create -n hinglish-whisper python=3.12 -y
conda activate hinglish-whisper
pip install -r requirements.txt
```

Copy `.env` and edit paths for your machine:

```bash
cp .env .env.local  # or edit .env directly
```

Key variables:

| Variable | Default | Description |
|---|---|---|
| `HF_HOME` | `/Volumes/d/cache/hf_cache` | Hugging Face model cache |
| `MODEL_ID` | `Trelis/whisper-hinglish-preview` | Whisper model to load |
| `PORT` | `5050` | Web server port |
| `LLM_BASE_URL` | `http://192.168.1.2:7890` | LM Studio / llama.cpp base URL |
| `LLM_MODEL` | `google/gemma-4-26b-a4b-qat` | Model name sent in translation requests |

## Usage

### Web GUI

```bash
conda activate hinglish-whisper
python app.py
# open http://localhost:5050
```

Features:
- Drag-and-drop or click to upload audio (WAV · MP3 · FLAC · M4A · OGG)
- **Sync to audio mode** — transcript highlights in sync with playback; click any segment to seek
- **Plain text mode** — streaming plain transcription, no player
- Language toggle: Hindi/Hinglish or English
- Hinglish mode toggle: enables the `<|mixedcode|>` token for code-switched audio
- **Translation** — translate the transcript to any of 22 languages via a local LLM; toggle between original and translated view; audio sync works on both
- Light / dark / auto theme

### CLI

```bash
conda activate hinglish-whisper

# Hinglish audio (default)
python transcribe.py audio.wav

# Pure Hindi
python transcribe.py audio.wav --no-mixed

# English
python transcribe.py audio.wav --lang en --no-mixed
```

The CLI prints each chunk as it is transcribed so you see output progressively rather than waiting for the full file.

## How it works

### Chunked streaming

Long audio is processed in **20-second chunks** (configurable via `CHUNK_SAMPLES` in `app.py`). Each chunk is transcribed independently and results stream back immediately — the web UI appends text and the audio player appears after the first chunk lands.

No overlap between chunks (`STRIDE_SAMPLES = 0`) avoids duplicate words at boundaries. If you hear clipped words at boundaries, set `STRIDE_SAMPLES = 8000` (0.5 s).

### Sync to audio (web UI)

When **Sync to audio** is on, each chunk's transcript is stored as a single segment spanning that chunk's time window (e.g. 0–20 s, 20–40 s, …). As the audio plays, `audio.currentTime` is compared against each segment's `start`/`end` to drive highlighting. Clicking a segment seeks the audio to that position.

> **Note:** This model (whisper-hinglish-preview) does not generate Whisper timestamp tokens — it always produces `<|notimestamps|>` output. Sync accuracy is therefore at the chunk granularity (20 s by default). Reduce `CHUNK_SAMPLES` for finer sync at the cost of more inference calls.

### Translation

After transcription completes, the **Translate to** panel appears. Select a target language and click Translate — all segments are sent in a single request to a local LLM (LM Studio or llama.cpp) via the OpenAI-compatible `/v1/chat/completions` endpoint.

- The LLM translates only the `text` field of each segment; `start`/`end` timestamps are enforced from the original and never altered by the LLM
- Audio sync and click-to-seek work identically on the translated view
- The **Original / \<Language\>** toggle in the transcript header switches between views without re-translating
- Copy always copies whichever view is currently active
- Supported languages: English, Bengali, Telugu, Marathi, Tamil, Urdu, Gujarati, Kannada, Malayalam, Punjabi, Odia, Assamese, Sanskrit, Nepali, Sindhi, Konkani, Maithili, Dogri, Manipuri, Bodo, Kashmiri, Santali

### Memory management

Each chunk's intermediate tensors (`features`, `out`) are deleted immediately after decoding. When transcription finishes, `torch.mps.empty_cache()` flushes the MPS allocator pool, bringing GPU memory back to model-only usage (~4 GB) between runs.

### Prompt tokens

The model requires explicit control tokens at the start of decoding:

| Token | Meaning |
|---|---|
| `<\|startoftranscript\|>` | Always first |
| `<\|hi\|>` / `<\|en\|>` | Language |
| `<\|mixedcode\|>` | Hinglish code-switching (optional) |
| `<\|transcribe\|>` | Task |
| `<\|notimestamps\|>` | Suppress timestamp generation |

Audio is resampled to 16 kHz mono before feature extraction. `max_new_tokens` is set to `448 − prompt_length` to stay within Whisper's 448-token decoder limit.

## Hardware

Optimized for Apple Silicon via MPS (`float16`). On M4 Pro the ~4 GB model fits in unified memory; peak usage during inference reaches ~25 GB due to MPS activation buffers, dropping back to ~4 GB after each run once the cache is flushed.

| Setting | Value |
|---|---|
| Device | MPS (Apple Silicon) |
| Dtype | `float16` |
| Model size | ~4 GB |
| Peak inference memory | ~25 GB (flushed after each run) |
| HF cache | configurable via `HF_HOME` in `.env` |
| Chunk size | 20 s |
| Chunk overlap | 0 s |

## Model lineage

`whisper-large-v3` → `whisper-large-v3-vaani` (ARTPARK/IISc Hindi fine-tune) → `whisper-hinglish-preview` (Hinglish fine-tune by Trelis Research)
