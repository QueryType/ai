"""Fact store — persistent, cross-file entity memory for a story sequence.

Design: docs/STORY_MEMORY_SPEC.md (Phase 0).

One SQLite file per story (files sharing a numeric-suffix prefix, e.g.
story_00.md/story_01.md -> story id "story"), colocated with checkpoints:
output/.<story_id>.facts.db

Retrieval is deterministic entity/alias substring matching plus a plain
indexed SQL query — no LLM involved on the read path, matching the existing
constraint on LoreInjector (see lore_tools.py).
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS facts (
    id INTEGER PRIMARY KEY,
    story_id TEXT NOT NULL,
    scene_index INTEGER NOT NULL,
    beat_index INTEGER NOT NULL,
    entity TEXT NOT NULL,
    relation TEXT NOT NULL,
    value TEXT NOT NULL,
    source_text TEXT
);
CREATE INDEX IF NOT EXISTS idx_facts_entity ON facts(story_id, entity);
CREATE INDEX IF NOT EXISTS idx_facts_timeline ON facts(story_id, scene_index, beat_index);

CREATE TABLE IF NOT EXISTS entity_aliases (
    id INTEGER PRIMARY KEY,
    story_id TEXT NOT NULL,
    canonical_name TEXT NOT NULL,
    alias TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_alias ON entity_aliases(story_id, alias);
"""


def db_path_for_output(output_file: str, story_id: str) -> Path:
    """Facts db path colocated with checkpoints, keyed by story id."""
    p = Path(output_file)
    return p.parent / f".{story_id}.facts.db"


def init_db(db_path: Path) -> Path:
    """Create the db file and schema if not already present."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(_SCHEMA)
        conn.commit()
    finally:
        conn.close()
    return db_path


def _norm(name: str) -> str:
    return name.strip().lower()


def _resolve_or_create_alias_on(conn: sqlite3.Connection, story_id: str, name: str) -> str:
    """Same as resolve_or_create_alias but operates on an existing connection
    and does not commit — for use inside a larger unit of work (see
    insert_facts) so we never open a second writer connection mid-transaction.
    """
    key = _norm(name)
    row = conn.execute(
        "SELECT canonical_name FROM entity_aliases WHERE story_id = ? AND alias = ?",
        (story_id, key),
    ).fetchone()
    if row:
        return row[0]

    canonical = name.strip()
    conn.execute(
        "INSERT INTO entity_aliases (story_id, canonical_name, alias) VALUES (?, ?, ?)",
        (story_id, canonical, key),
    )
    return canonical


def _add_alias_on(conn: sqlite3.Connection, story_id: str, canonical_name: str, alias: str) -> None:
    """Same as add_alias but operates on an existing connection, no commit."""
    key = _norm(alias)
    existing = conn.execute(
        "SELECT 1 FROM entity_aliases WHERE story_id = ? AND alias = ?",
        (story_id, key),
    ).fetchone()
    if existing:
        return
    conn.execute(
        "INSERT INTO entity_aliases (story_id, canonical_name, alias) VALUES (?, ?, ?)",
        (story_id, canonical_name.strip(), key),
    )


def resolve_or_create_alias(db_path: Path, story_id: str, name: str) -> str:
    """Return the canonical entity name for `name`, registering it as a new
    canonical entity (aliased to itself) if it has never been seen before.

    Opens and commits its own connection — for standalone callers. Code that
    already holds a connection (e.g. insert_facts) should use
    _resolve_or_create_alias_on instead, to avoid a second writer connection
    against the same locked db file.
    """
    conn = sqlite3.connect(db_path)
    try:
        canonical = _resolve_or_create_alias_on(conn, story_id, name)
        conn.commit()
        return canonical
    finally:
        conn.close()


def add_alias(db_path: Path, story_id: str, canonical_name: str, alias: str) -> None:
    """Register an additional alias for an already-canonical entity.

    No-op if the alias is already registered (for this story) to any entity —
    existing mapping wins, first writer takes precedence. Opens and commits
    its own connection; see resolve_or_create_alias docstring for why
    insert_facts uses the _on variant instead.
    """
    conn = sqlite3.connect(db_path)
    try:
        _add_alias_on(conn, story_id, canonical_name, alias)
        conn.commit()
    finally:
        conn.close()


def insert_facts(
    db_path: Path,
    story_id: str,
    scene_index: int,
    beat_index: int,
    facts: list[dict],
) -> None:
    """Insert extracted facts. Each dict: {entity, relation, value, source_text?}.

    `entity` is resolved/registered as a canonical name (and any `aliases`
    list on the dict is registered against it) before the fact row is
    written, so later lookups by any alias find this fact.
    """
    conn = sqlite3.connect(db_path)
    try:
        for fact in facts:
            raw_entity = fact["entity"]
            canonical = _resolve_or_create_alias_on(conn, story_id, raw_entity)
            for alias in fact.get("aliases", []):
                _add_alias_on(conn, story_id, canonical, alias)

            conn.execute(
                """INSERT INTO facts
                   (story_id, scene_index, beat_index, entity, relation, value, source_text)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    story_id,
                    scene_index,
                    beat_index,
                    canonical,
                    fact["relation"],
                    fact["value"],
                    fact.get("source_text"),
                ),
            )
        conn.commit()
    finally:
        conn.close()


def query_facts(
    db_path: Path,
    story_id: str,
    entity: str,
    before: tuple[int, int],
) -> list[dict]:
    """All facts about `entity` established strictly before (scene_index, beat_index)."""
    scene_index, beat_index = before
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            """SELECT relation, value, scene_index, beat_index FROM facts
               WHERE story_id = ? AND entity = ?
                 AND (scene_index, beat_index) < (?, ?)
               ORDER BY scene_index, beat_index""",
            (story_id, entity, scene_index, beat_index),
        ).fetchall()
        return [
            {"relation": r[0], "value": r[1], "scene_index": r[2], "beat_index": r[3]}
            for r in rows
        ]
    finally:
        conn.close()


def query_all_facts(
    db_path: Path,
    story_id: str,
    before: tuple[int, int],
) -> dict[str, list[dict]]:
    """All facts for every entity established strictly before (scene_index, beat_index),
    grouped by entity, timeline-ordered within each entity.

    Unlike query_facts (single entity, driven by a beat-text keyword match — the
    reactive LoreInjector path), this dumps the full known timeline regardless of
    entity. Used by extend.py's proactive planning, which has no beat text to scan
    for triggers yet — it's generating the next scene's setup, not reacting to one.
    """
    scene_index, beat_index = before
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            """SELECT entity, relation, value, scene_index, beat_index FROM facts
               WHERE story_id = ?
                 AND (scene_index, beat_index) < (?, ?)
               ORDER BY entity, scene_index, beat_index""",
            (story_id, scene_index, beat_index),
        ).fetchall()
    finally:
        conn.close()

    facts_by_entity: dict[str, list[dict]] = {}
    for entity, relation, value, s_idx, b_idx in rows:
        facts_by_entity.setdefault(entity, []).append(
            {"relation": relation, "value": value, "scene_index": s_idx, "beat_index": b_idx}
        )
    return facts_by_entity


def match_entities(db_path: Path, story_id: str, text: str) -> list[str]:
    """Scan `text` for known aliases, return matched canonical entity names.

    Mirrors scan_for_triggers() in lore_tools.py: whole-word, case-insensitive
    substring matching, no LLM involved.
    """
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT DISTINCT canonical_name, alias FROM entity_aliases WHERE story_id = ?",
            (story_id,),
        ).fetchall()
    finally:
        conn.close()

    matched: list[str] = []
    seen: set[str] = set()
    for canonical, alias in rows:
        if canonical in seen:
            continue
        pattern = r"\b" + re.escape(alias) + r"\b"
        if re.search(pattern, text, re.IGNORECASE):
            matched.append(canonical)
            seen.add(canonical)
    return matched
