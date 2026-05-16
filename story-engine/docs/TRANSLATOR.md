# Story Translator

Translate a large story or prose file into another language, paragraph by paragraph. Rolling context from the last two translated paragraphs is carried into each call to preserve character names, tone, and verb tense across the entire document.

---

## Quick Start

```bash
conda activate strandsagents
cd /Volumes/d/code/aiml/story-engine

python -m my_code.translate path/to/story.md --target Hindi
# Output: path/to/story.translated.md
```

---

## How It Works

1. The input file is split on blank lines into paragraphs.
2. If `--source` is omitted, the LLM detects the source language from the first paragraph.
3. Each paragraph is translated in order. A fresh `TranslatorAgent` is created per paragraph (no accumulated state).
4. The last N translated paragraphs (default: 2) are prepended to each call as a read-only context block — the model uses them for consistency but does not retranslate them.
5. The translated paragraphs are joined and written to the output file.

```
Input file
    │
    ▼
Split into paragraphs
    │
    ▼
Detect source language (if not given)
    │
    ├── Paragraph 1 ──► TranslatorAgent ──► translated_1
    │                        ↑
    │                  [no prior context]
    │
    ├── Paragraph 2 ──► TranslatorAgent ──► translated_2
    │                        ↑
    │                  [translated_1]
    │
    ├── Paragraph 3 ──► TranslatorAgent ──► translated_3
    │                        ↑
    │                  [translated_1, translated_2]
    │
    └── ... (window slides forward)
    │
    ▼
Output file
```

---

## CLI Reference

```
python -m my_code.translate <input> --target <lang> [options]
```

| Argument | Required | Description |
|----------|----------|-------------|
| `input` | yes | Path to the input `.md` or `.txt` file |
| `--target` | yes | Target language name (e.g. `Hindi`, `French`, `Japanese`, `Hinglish`) |
| `--source` | no | Source language name. Auto-detected from first paragraph if omitted |
| `--output` | no | Output file path. Defaults to `<input>.translated.<ext>` |
| `--hint` | no | Extra instructions appended to the system prompt (see below) |
| `--context-paragraphs` | no | Number of prior translated paragraphs to carry as context (default: `2`) |

---

## Examples

### Basic — auto-detect source

```bash
python -m my_code.translate story.md --target Hindi
```

### Explicit source language

```bash
python -m my_code.translate story.md --target French --source English
```

### Custom output path

```bash
python -m my_code.translate story.md --target Spanish --output /tmp/story_es.md
```

### Hinglish in Roman script

```bash
python -m my_code.translate story.md --target Hinglish \
  --hint "Write in Roman script (Latin alphabet), not Devanagari. Keep English slang and tech words as-is."
```

### Urdu in Arabic script

```bash
python -m my_code.translate story.md --target Urdu \
  --hint "Use Arabic script (Nastaliq style preferred)."
```

### Hindi but keep English dialogue intact

```bash
python -m my_code.translate story.md --target Hindi \
  --hint "Translate narration to Hindi in Devanagari. Keep all dialogue in English exactly as written."
```

### Wider context window for long stories

```bash
python -m my_code.translate story.md --target Japanese --context-paragraphs 4
```

---

## The `--hint` Flag

`--hint` appends free-form instructions to the translator's system prompt under an `## Additional instructions` section. Use it for anything the target language or style requires that isn't covered by the default prompt:

- Script selection (Roman, Devanagari, Arabic, Cyrillic)
- Register (formal/informal `vous` vs `tu` in French)
- Dialect preferences
- Handling of invented names, brand names, or technical terms
- Mixed-language output (code-switching)

The hint is applied to every paragraph in the run, including the language detection call.

---

## Model Configuration

The translator reuses the summariser's model configuration from `.env`:

```env
STORY_ENGINE_SUMMARISER_BASE_URL=http://192.168.1.5:8081/v1
STORY_ENGINE_SUMMARISER_MODEL=default
```

No new environment variables are needed. To use a different model for translation, point `STORY_ENGINE_SUMMARISER_BASE_URL` to the desired server, or temporarily change the model ID. For languages that require a stronger model (e.g. classical Japanese, literary Arabic), consider routing to the narrator server instead by updating the env var.

---

## Output

- Output is UTF-8 encoded.
- Paragraph breaks from the source are preserved.
- Markdown headings, fences, and other non-prose blocks are passed through as-is — only the text content of each paragraph is translated.
- If the output directory does not exist, it is created automatically.

---

## Troubleshooting

### Output contains English mixed in unexpectedly

The model may revert to English for proper nouns or technical terms. Use `--hint` to give explicit instructions:

```bash
--hint "Translate everything including character names phonetically. Do not leave any English words."
```

### Language detection returns wrong language

Pass `--source` explicitly to skip detection:

```bash
--source English
```

### Output file is empty or very short

Check the server logs for `max_tokens` errors. The summariser context (`ctx=4096`) is enough for typical story paragraphs (~300–500 words). If your paragraphs are unusually long, consider splitting the input manually or increasing the server context window.

### Script is correct but transliteration is off (e.g. Hinglish)

Use `--hint` to specify the exact convention:

```bash
--hint "Use IAST-style Roman transliteration. Aspirated consonants with h (kh, gh, ch, etc.)."
```
