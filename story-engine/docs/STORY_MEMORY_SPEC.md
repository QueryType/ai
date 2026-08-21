# Story Memory — Design Spec

## Problem

Today, continuity across a long story that's chunked into a sequence of scene
files (`story_00.md`, `story_01.md`, `story_02.md`, ... run via `batch.py` or
`extend.py`) relies on:

- `SummarizingConversationManager` — only within a single narrator run/process
- `prior_summary` / checkpoint — only within a single scene file's beats
- `extend.py`'s `prior_context` — bullets summarised from the *immediately
  previous* file only

None of this persists small concrete details ("the dagger was rusted",
"Aldric already met the innkeeper in scene 2") once you're more than one file
away from where they were established. There is no cross-file store of story
state.

## Goal

A persistent, queryable store of **facts about entities**, indexed by where
in the story timeline they were established, so that any later beat — in any
file, in the same story sequence — can retrieve exactly what's already true
about an entity it mentions.

Explicitly NOT storing the prose itself (that already lives in the output
`.md` files) — only a distilled index over it.

## Non-goals

- Not a vector/embedding RAG system. Retrieval is exact entity-name matching,
  not semantic similarity. (See design discussion: the access pattern is
  "everything known about entity X so far," not "text similar to this beat.")
- Not a graph database (Neo4j etc.). The query shape is single-entity lookups
  with a timeline filter, not multi-hop graph traversal. A relational table
  with two indexes covers it; SQLite even supports recursive CTEs later if
  multi-hop questions ever materialize.
- Not a new server/service. File-based, like checkpoints — `sqlite3` is
  stdlib.
- No changes to the narrator's model, prompts, or KV-cache-sensitive call
  path. Retrieval stays deterministic Python, same constraint that already
  shaped `LoreInjector`.

## Architecture

### Story identity

A "story" is a sequence of files sharing a numeric-suffix prefix:
`story_00.md`, `story_01.md`, `story_02.md`, ... → story id `story`.
Same prefix convention `extend.py` already uses (`_auto_output_path`).

One shared SQLite file per story, colocated with checkpoints:
`output/.<prefix>.facts.db`

### Schema

```sql
CREATE TABLE facts (
    id INTEGER PRIMARY KEY,
    story_id TEXT NOT NULL,
    scene_index INTEGER NOT NULL,   -- 0, 1, 2 from filename suffix
    beat_index INTEGER NOT NULL,    -- beat number within that scene file
    entity TEXT NOT NULL,           -- canonical entity name
    relation TEXT NOT NULL,         -- e.g. "found_by", "description", "location"
    value TEXT NOT NULL,
    source_text TEXT                -- short quote/paraphrase, for traceability
);
CREATE INDEX idx_facts_entity ON facts(story_id, entity);
CREATE INDEX idx_facts_timeline ON facts(story_id, scene_index, beat_index);

CREATE TABLE entity_aliases (
    id INTEGER PRIMARY KEY,
    story_id TEXT NOT NULL,
    canonical_name TEXT NOT NULL,
    alias TEXT NOT NULL
);
CREATE UNIQUE INDEX idx_alias ON entity_aliases(story_id, alias);
```

Ordering key for "as of now" queries is the tuple `(scene_index, beat_index)`,
compared lexicographically — this is what makes cross-file timeline queries
possible instead of just within-file ones.

### Write side — extraction

After a beat is accepted (same point `BeatSummariser` already runs, in
`orchestrator.py`'s beat loop), a new stateless call extracts facts from that
beat's prose:

- New agent, same pattern as `Evaluator`/`BeatSummariser`/`TranslatorAgent`:
  single-shot, `NullConversationManager`, fresh instance per beat, no tools.
- Model: reuse `get_model("summariser")` (port 8081, 9B) — same reasoning as
  `SceneExtenderAgent` and `story_importer`'s extraction call. This is
  structured JSON extraction, not prose generation; the 31B narrator is
  neither needed nor touched.
- Output: JSON list of `{entity, relation, value, aliases: [...]}`.
- Entities are checked against `entity_aliases` for the story; new aliases
  get inserted, canonical name reused if a match is found (so "the blade"
  and "dagger" collapse to one entity over time).
- Rows inserted with the current `scene_index`/`beat_index`.

This runs in beat order, file order — extraction quality depends on seeing
entities appear chronologically, per the earlier design discussion, so this
must not be parallelized across beats.

### Read side — retrieval

Extends `LoreInjector`'s existing trigger-scan mechanism
(`my_code/tools/lore_tools.py`, called from `_call_lore_injector` in
`orchestrator.py`) rather than replacing it:

1. Same deterministic keyword scan already used for character triggers, now
   also matching against `entity_aliases` for the story.
2. On a match, a plain parameterized SQL query:
   ```sql
   SELECT relation, value FROM facts
   WHERE story_id = ? AND entity = ?
     AND (scene_index, beat_index) < (?, ?)
   ORDER BY scene_index, beat_index
   ```
3. Results folded into the same lore block already prepended to the
   narrator's prompt — no new prompt-injection mechanism, no new model call
   on the narrator's path.

No LLM decides whether or what to query. Matching is substring/alias lookup;
retrieval is a parameterized query. This mirrors the existing constraint that
`LoreInjector` has no LLM call at all.

### Batch/sequence wiring

`batch.py` iterates scene files and calls `run_scene()` per file today, each
run isolated. It needs to:
- Derive `story_id` from the filename prefix once per batch.
- Derive `scene_index` per file (position in the sorted/given sequence, or
  parsed from the numeric suffix).
- Pass both into `run_scene()` so the facts db path and current
  scene/beat coordinates are available to the extraction and retrieval
  calls.

`extend.py`/`scene_extender.py`: `prior_context` generation should query the
facts db for the full timeline up to the end of the previous scene, not just
summarise the immediately-previous file's text as it does today.

### Backfill

For an existing sequence of files with no facts db yet:
1. Any file missing `<!-- beat:N -->` markers needs `rewrite.py --map` run
   first (existing tool, no LLM).
2. Walk files in story order, parse beats via the existing
   `_parse_output_beats`-equivalent logic already used by `rewrite.py`.
3. Run the same extraction call used for live beats, in strict
   scene/beat order, populating the same schema.

This is the same extraction code path as live runs, invoked by a script over
history instead of by the orchestrator after each beat — no separate
extraction logic to maintain.

## Files to create/modify

| File | Change |
|---|---|
| `my_code/tools/fact_store.py` | New — SQLite schema init, insert/query helpers, alias resolution |
| `my_code/agents/fact_extractor.py` | New — `create_fact_extractor()`, single-shot JSON extraction agent |
| `my_code/tools/lore_tools.py` | Extend trigger scan to also match `entity_aliases`; extend `build_lore_block` to fold in fact rows |
| `my_code/agents/orchestrator.py` | Call fact extraction after beat acceptance (alongside `BeatSummariser`); pass `story_id`/`scene_index` through `run_scene()`; wire facts db into `_call_lore_injector` |
| `my_code/batch.py` | Derive `story_id`/`scene_index` per file, pass through to `run_scene()` |
| `my_code/agents/scene_extender.py` | Query facts db for `prior_context` instead of/in addition to previous-file summary |
| `my_code/backfill_facts.py` | New — CLI to populate the db from an existing file sequence |

## Constraints / decisions made

- SQLite, not a new server or graph DB — matches project's file-based,
  dependency-light conventions.
- Extraction and retrieval both use the 9B (port 8081) or no model at all
  (retrieval) — 31B narrator's KV cache is never touched by this feature.
- Extraction runs synchronously, in order, per beat — not batched or
  parallelized, because alias resolution depends on chronological order.
- Retrieval is deterministic keyword/alias matching, same constraint already
  imposed on `LoreInjector` — no LLM-driven query generation.
- Facts db is additive to existing lore-card mechanism, not a replacement.
