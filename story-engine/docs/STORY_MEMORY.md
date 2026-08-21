# Story Memory — Cross-File Continuity

Persistent memory of small concrete details across a chunked, multi-file story
(`story_00.md`, `story_01.md`, `story_02.md`, ...) — the kind of thing that
otherwise falls out of scope once you're a file or two past where it was
established. No setup required: it runs automatically as part of every scene
run.

Design rationale: `docs/STORY_MEMORY_SPEC.md`.

---

## Quick Start

Nothing to configure — it's on by default for every `run_scene()` call, whether
via `main.py`, `batch.py`, or `extend.py`.

```bash
conda activate strandsagents
cd /Volumes/d/code/aiml/story-engine

python my_code/main.py scenes/story_00.md
python my_code/main.py scenes/story_01.md
# story_01's beats can now recall facts established in story_00
```

To opt out for a run — no fact extraction, no retrieval, no db even created:

```bash
python my_code/main.py scenes/story_00.md --skip-memory
python -m my_code.batch scenes/ --skip-memory
```

Or set `STORY_ENGINE_SKIP_MEMORY=true` in `.env` to make that the default (the CLI
flag can still force it on/off per run — same pattern as `--skip-eval`). Useful for
quick test runs, or A/B comparing narrator output with/without continuity memory.
Doesn't touch or delete an existing facts db — just doesn't read or write to it for
that run.

You'll see it in the log:

```
Fact store: story_id=story scene_index=1 db=output/.story.facts.db
Beat 2: fact injection matched 2 entities
```

---

## How It Works

### What gets stored

Not the prose — that already lives in the output `.md` files. Just a distilled
index of **facts about entities**: `(entity, relation, value)`, tagged with
where in the story timeline they were established.

```
dagger  found_by     Aldric        (scene 2, beat 4)
dagger  description  rusted hilt   (scene 2, beat 4)
```

One SQLite file per story, colocated with checkpoints:
`output/.<story_id>.facts.db`

### Write side — extraction

After each beat is accepted (same point `BeatSummariser` runs), a fresh
stateless call extracts atomic facts from that beat's prose using the fast
summariser model (port 8081, 9B) — this is structured JSON extraction, not
prose generation, so the narrator's model and KV cache are never touched.
Extraction failure is non-fatal — logged as `FACT EXTRACTOR FALLBACK` /
`FACT STORE FALLBACK`, the beat itself is never lost.

### Read side — retrieval

Extends the existing `LoreInjector` mechanism (`my_code/tools/lore_tools.py`).
Before a beat is narrated, the upcoming beat's text is scanned — plain Python,
whole-word substring matching against known entity aliases, no LLM — for
entities that already have facts on record. Matches get folded into the same
lore block already prepended to the narrator's prompt, right alongside
character cards:

```
## Established So Far

**dagger**
- found_by: Aldric
- description: rusted hilt
```

No LLM decides *whether* or *what* to query — matching is deterministic
keyword lookup, and the query itself is a parameterized, indexed SQL lookup.
This mirrors the existing constraint on character-card lookup.

### Story identity

Files sharing a numeric-suffix prefix belong to one story:
`story_00.md`/`story_01.md`/`story_02.md` → `story_id = "story"`. Same
convention `extend.py` already uses for auto-numbering sequels. A file with no
numeric suffix is treated as a standalone single-scene story.

- **`main.py`**: `story_id`/`scene_index` are derived automatically from the
  scene's `[meta] output_file` field.
- **`batch.py`**: all files in one batch run share a single `story_id` (from
  the first file's name) and get `scene_index` set by their position in the
  sequence you gave — so batch order is authoritative even if a file's own
  `output_file` doesn't happen to follow the `story_NN` convention.
- **`extend.py`**: pulls facts from the *entire* story timeline so far (not
  just the immediately-previous file) into the sequel-generation prompt, so
  `prior_context` can be grounded in details from several files back.

---

## The Browser Scene Builder (`scene-builder.html`)

`my_code/scene-builder.html` is a standalone, static HTML tool (opens directly in a
browser, `fetch`s an LLM endpoint, no backend of its own) with its own "Create Sequel"
panel — a client-side equivalent of `extend.py`. Left on its own, it can only see
whichever single previous `.md` file you pick via its file input, the same limitation
`extend.py` had before Story Memory existed.

To give it access to the fact store, run the small read-only HTTP server:

```bash
conda activate strandsagents
python -m my_code.facts_server                          # binds 0.0.0.0:8082, reads ./output
python -m my_code.facts_server --port 8082 --output-dir output
```

Then, in `scene-builder.html`'s config bar, set **Facts Server URL** to wherever it's
running (e.g. `http://192.168.1.5:8082`). When you load a previous scene file into the
"Create Sequel" panel and click **Generate Sequel**, it fetches
`GET /facts?story_id=...&through_scene=...` (story id and scene index parsed
client-side from the loaded filename, same convention as `derive_story_coords()`) and
folds the result into the generation prompt — the same "Established Story Facts" block
`extend.py` already builds server-side. A status line next to the Generate button shows
what happened (`Loaded facts: N entities`, or a reason it didn't).

This is entirely optional: leave the field blank and the panel behaves exactly as
before. If the server is unreachable or has no db for that story, it fails silently —
generation proceeds without facts rather than blocking.

No auth on the endpoint (read-only, local/LAN use only, same trust model as the
narrator/evaluator servers already documented in CLAUDE.md).

---

## Backfilling an Existing Story

If you already have a multi-file story that predates this feature, populate
its facts db without regenerating anything:

```bash
python -m my_code.backfill_facts output/story_00.md output/story_01.md
python -m my_code.backfill_facts output/          # all .md in dir, alphabetical
```

Requires `<!-- beat:N -->` markers in each file — add them once with
`python -m my_code.rewrite <file> --map` (interactive, no LLM) if the files
predate marker embedding. `backfill_facts.py` will tell you exactly which
files need this and exit without changing anything if any are missing markers.

Beats are walked in file order, then beat order within each file — this
matters because alias resolution ("is 'the blade' the same as 'dagger'?")
depends on seeing entities appear chronologically. It uses the same extractor
as live runs, so a backfilled db is indistinguishable from one built by
actually running the scenes.

---

## Inspecting the Store

It's a plain SQLite file — no special tooling needed:

```bash
sqlite3 -header -column output/.story.facts.db \
  "SELECT scene_index, beat_index, entity, relation, value FROM facts ORDER BY scene_index, beat_index;"

sqlite3 -header -column output/.story.facts.db \
  "SELECT canonical_name, alias FROM entity_aliases;"
```

---

## Known Limitations

- **Extraction quality is the load-bearing part.** If a beat's important
  detail never gets extracted, it's gone — nothing re-scans old prose later.
  Extraction runs on the summariser model (9B), which occasionally emits
  literal placeholder text instead of a real relation, or over-extracts
  atmosphere/mood despite being told not to. This is a prompt-tuning target,
  not a structural limitation — the store and retrieval mechanism are solid;
  what goes into them depends on the extractor.
- **No fact-count cap per entity.** A very long-running story could
  accumulate many facts for a major character, all injected on every match.
  Not yet an issue at typical story lengths; revisit if lore blocks start
  bloating the narrator prompt.
- **Retrieval is exact-match, not semantic.** If a beat refers to an entity by
  a phrasing that was never registered as an alias, it won't be found. This is
  a deliberate tradeoff (see `docs/STORY_MEMORY_SPEC.md`'s non-goals) —
  precise recall over fuzzy similarity — but it means alias coverage matters.

---

## Troubleshooting

### `FACT EXTRACTOR FALLBACK` in the log

The extractor's JSON response couldn't be parsed, or the call itself raised.
The beat's prose is unaffected — it's saved normally — but no facts were
recorded for that beat. Non-fatal by design; check the raw output snippet
logged alongside the warning if it happens often.

### `FACT STORE FALLBACK: insert failed`

A SQLite error on write — facts extracted for that beat weren't persisted.
The beat itself still saved normally. Shouldn't happen under normal use; if
it does, check that `output/` is writable and not on a read-only mount.

### Facts aren't showing up in a later scene

1. Confirm the files actually share a `story_id` — check the `Fact store:
   story_id=... scene_index=...` log line for each run. If run standalone
   (not via `batch.py`) with mismatched filenames, they may have landed as
   separate stories.
2. Check the entity was actually extracted: `sqlite3 output/.story.facts.db
   "SELECT * FROM entity_aliases WHERE alias LIKE '%yourword%'"`.
3. If the entity exists but under a different alias than the later beat used,
   that's the exact-match limitation above — the extraction prompt may need
   to register more aliases for that entity.

### `backfill_facts.py` says no beat markers found

Run `python -m my_code.rewrite <file> --map` on each listed file first
(interactive, no LLM), then re-run the backfill.
