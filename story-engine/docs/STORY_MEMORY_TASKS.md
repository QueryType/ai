# Story Memory — Implementation Tasks

Full design: `docs/STORY_MEMORY_SPEC.md`. Work through phases in order — each
phase should be independently testable before moving to the next. Check off
items as completed; this file is the resume point if work is interrupted
across sessions.

## Phase 0 — Schema & store (no agent integration yet)

- [x] Create `my_code/tools/fact_store.py`
  - [x] `init_db(story_id) -> Path` — creates `output/.<prefix>.facts.db` with
        `facts` and `entity_aliases` tables if not present
  - [x] `insert_facts(db_path, story_id, scene_index, beat_index, facts: list[dict])`
  - [x] `resolve_or_create_alias(db_path, story_id, name) -> str` — returns
        canonical entity name, inserting a new alias row if `name` doesn't
        match an existing one
  - [x] `query_facts(db_path, story_id, entity, before=(scene_index, beat_index)) -> list[dict]`
  - [x] `match_entities(db_path, story_id, text) -> list[str]` — scan text for
        known aliases, return canonical names matched (mirrors
        `scan_for_triggers` in `lore_tools.py`)
- [x] Unit-test the store standalone with a hand-written fixture (no LLM
      calls) — insert facts across fake scene/beat indices, verify timeline
      ordering and alias resolution work before touching any agent code

## Phase 1 — Extraction agent

- [x] Create `my_code/agents/fact_extractor.py`
  - [x] `create_fact_extractor()` — single-shot, `NullConversationManager`,
        no tools, reuses `get_model("summariser")` per `SceneExtenderAgent`
        pattern
  - [x] System prompt: extract atomic `{entity, relation, value, aliases}`
        facts from one beat's prose; instruct canonical naming and alias
        emission explicitly (this is the highest-risk part per the design
        discussion — plan to iterate on this prompt)
  - [x] Parse/validate JSON response, same defensive pattern as
        `_call_evaluator`'s fallback handling (malformed JSON should not
        crash the beat loop — log and skip extraction for that beat)
- [x] Manual test: run the extractor against 2-3 real beats from
      `output/ashenveil_scene1.md`, eyeball the extracted facts for
      atomicity and correct aliasing before wiring into the pipeline

## Phase 2 — Orchestrator write-side wiring

- [x] `run_scene()` in `orchestrator.py`: accept/derive `story_id` and
      `scene_index`
- [x] After beat acceptance (alongside existing `BeatSummariser` call): call
      fact extractor, insert results via `fact_store.insert_facts`
- [x] Extraction failure must not fail the beat — log and continue (matches
      `EVALUATOR FALLBACK` pattern already in the codebase)
- [x] Run one full scene end-to-end, inspect the resulting `.facts.db`
      directly (`sqlite3` CLI) to confirm rows look right

## Phase 3 — Retrieval wiring (LoreInjector extension)

- [x] Extend `scan_for_triggers`/add new tool in `lore_tools.py` to also
      match against `entity_aliases` for the current story
- [x] Extend `build_lore_block` to fold in `query_facts` results for matched
      entities
- [x] Wire facts db path into `_call_lore_injector` in `orchestrator.py`
- [x] Test: manually seed a fact in scene 0 for an entity, write a scene 1
      beat mentioning it, confirm the lore block passed to the narrator
      includes the fact (log the assembled lore block for inspection)

## Phase 4 — Batch/sequence wiring

- [x] `batch.py`: derive `story_id` and `scene_index` per file from the
      filename prefix/suffix, pass through to `run_scene()`
- [x] Run a real 2-3 file batch sequence, confirm facts from file 0 are
      retrievable while generating file 2

## Phase 5 — extend.py integration

- [x] `scene_extender.py`: query facts db for full-timeline `prior_context`
      instead of (or blended with) summarising only the immediately previous
      file
- [x] Compare output quality against current behavior on a real extend case

## Phase 6 — Backfill tool

- [x] Create `my_code/backfill_facts.py`
  - [x] Given a story file sequence, check each for `<!-- beat:N -->`
        markers; if missing, instruct user to run `rewrite.py --map` first
        and exit (don't auto-invoke `--map`, it's interactive)
  - [x] Walk files in order, parse beats, run the Phase 1 extractor per beat
        in strict order, insert via `fact_store.insert_facts`
- [x] Run against the existing `examples/ashenveil_scene1.md` +
      `output/ashenveil_scene1.md` pair as the first real backfill test —
      NOTE: `output/ashenveil_scene1.md` predates beat markers, so this
      confirmed the missing-markers rejection path works correctly, not a
      populated backfill. Actually populating that file's facts still needs
      the user to run `rewrite.py output/ashenveil_scene1.md --map`
      (interactive, line numbers only they can judge) before backfill can run
      on it for real. Tool logic itself is fully verified against scratchpad
      copies of the same content that do have markers (from real orchestrator
      runs), including correct scene_index sequencing across a 2-file story.

## Phase 7 — Docs

- [x] `docs/STORY_MEMORY.md` — user-facing reference (usage, config, how
      retrieval works), same style as `docs/REWRITE.md`
- [x] Update `CLAUDE.md` — new section under "Scene generation tools" or its
      own top-level section, once the feature is real (not before — avoid
      documenting an unbuilt feature as if it exists, per existing
      convention where `REWRITE_PLAN.md` stayed separate from `CLAUDE.md`
      until `rewrite.py` shipped)

## Open questions to resolve during implementation

- Exact `relation` vocabulary — free text vs. a constrained enum? Free text
  is simpler but risks fragmentation (`"found_by"` vs `"discovered_by"`).
  Decide during Phase 1 prompt iteration.
- Should retrieval cap the number of facts injected per entity (long-running
  stories could accumulate many facts per major character)? Revisit once
  Phase 3 is running against a real multi-file story.
