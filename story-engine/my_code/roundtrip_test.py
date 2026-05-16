#!/usr/bin/env python3
"""
roundtrip_test.py — Roundtrip quality test for story_importer.

Pipeline:
  1. Generate prose  — run story engine on the input .md → output prose
  2. Import          — run story importer on the prose → reconstructed .md
  3. Diff            — field-by-field quality report (quantity + semantic checks)
  4. Improve (auto)  — LLM analyses diff, rewrites importer system prompt
  5. Loop            — repeat from step 2 until satisfied or max iters reached

Usage:
  # Full roundtrip (generate + import + diff):
  python -m my_code.roundtrip_test examples/ashenveil_scene1.md

  # Skip generation (reuse an existing prose output):
  python -m my_code.roundtrip_test examples/ashenveil_scene1.md \\
      --prose output/ashenveil_scene1.md --skip-generate

  # Fully automatic improvement loop:
  python -m my_code.roundtrip_test examples/ashenveil_scene1.md \\
      --prose output/ashenveil_scene1.md --skip-generate --auto --iters 6

  # Commit the best prompt back to single_pass.py after a run:
  python -m my_code.roundtrip_test examples/ashenveil_scene1.md \\
      --prose output/ashenveil_scene1.md --skip-generate --auto --iters 6 --commit
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from my_code.parser import _split_sections, _parse_kv, _parse_beats
from my_code.importers.base import call_llm, BASE_URL, MODEL, word_count
from my_code.importers.single_pass import _imagination_clause, _USER
import my_code.importers.single_pass as _sp_module
from my_code.scene_builder import assemble, validate_generated, slugify


# ── Thresholds ─────────────────────────────────────────────────────────────────

# Absolute floor — gen must have at least this many words regardless of original length
_MIN_WORDS = {
    "narrator_prompt":      50,
    "writing_style":        30,
    "world_info":           50,
    "scenario":             50,
    "writing_instructions": 30,
    "char_description":     20,
    "char_personality":     10,
    "char_backstory":       10,
    "char_speech_style":    10,
    "beat_instruction":     15,
    "scene_setup_sub":       5,
}

# Ratio floor — gen must also be at least this fraction of the original's word count.
# Catches compression loss on rich scenes where original is far above the absolute floor.
# Applied as: effective_min = max(abs_floor, int(orig_words * ratio))
# Set to 0 for fields where ratio checking doesn't make sense.
_RATIO = {
    "narrator_prompt":      0.45,
    "writing_style":        0.40,
    "world_info":           0.35,
    "scenario":             0.35,
    "writing_instructions": 0.40,
    "char_description":     0.45,
    "char_personality":     0.45,
    "char_backstory":       0.40,
    "char_speech_style":    0.45,
    "beat_instruction":     0.40,
    "scene_setup_sub":      0.0,
}

# Trigger count ratio — when orig has many triggers, gen must cover at least this fraction
_TRIGGER_RATIO     = 0.40
_TRIGGER_MIN_COUNT = 3      # absolute floor regardless of orig count

PASS    = "PASS"
THIN    = "THIN"
MISSING = "MISSING"
WARN    = "WARN"

_QUANTITY_WEIGHT  = 0.6
_SEMANTIC_WEIGHT  = 0.4
_SATISFACTION     = 0.82
_DEFAULT_ITERS    = 5
_WORK_DIR         = Path("output/roundtrip_work")


# ── Semantic check helpers ─────────────────────────────────────────────────────

def _has(text: str, *patterns: str) -> bool:
    tl = text.lower()
    return any(p.lower() in tl for p in patterns)


def _sentences(text: str) -> int:
    return len(re.findall(r"[.!?]+", text))


def _has_proper_nouns(text: str) -> bool:
    # Words that start with capital but are not at sentence start
    words = text.split()
    mid_caps = [w for i, w in enumerate(words) if i > 0 and w[:1].isupper() and w.isalpha()]
    return len(mid_caps) >= 2


def _names_in_text(text: str, characters: list[dict]) -> bool:
    tl = text.lower()
    names = [c.get("name", "").split()[0].lower() for c in characters if c.get("name")]
    return sum(1 for n in names if n and n in tl) >= min(2, len(names))


def _beat_title_is_caps(text: str) -> bool:
    # Beat text from generated file is "TITLE instruction..." — first line is title
    first_line = text.split("\n")[0].strip() if "\n" in text else text[:40]
    # Allow either ALL-CAPS title or short title-case (max 6 words)
    words = first_line.split()[:6]
    return bool(words) and all(w.isupper() or not w.isalpha() for w in words[:4])


def _has_action_verbs(text: str) -> bool:
    return _has(text,
        "confront", "reveal", "discover", "enter", "escape", "fight", "flee",
        "speak", "say", "decide", "move", "arrive", "leave", "reach", "find",
        "steps", "turns", "strikes", "hesitates", "pushes", "pulls", "opens",
        "stand", "approach", "offer", "ask", "face", "rise", "walk", "bow",
        "emerge", "challenge", "accept", "refuse", "hand", "draw", "begin",
        "both ", "they ", "she ", "he ", "it ", "together",
    )


# ── Semantic check definitions ─────────────────────────────────────────────────
# Each check: (id, description, fn(gen_text, context) -> bool)

_NARRATOR_PROMPT_CHECKS = [
    ("has_pov",
     "mentions POV / tense",
     lambda t, _: _has(t, "third-person", "first-person", "second-person",
                        "past tense", "present tense", "tense", "perspective")),
    ("has_player_char_rule",
     "states what to do with the player character",
     lambda t, _: _has(t, "player character", "player-character", "player",
                        "protagonist", "you control", "control all")),
    ("has_prohibition",
     "has at least one prohibition (never/avoid/do not)",
     lambda t, _: _has(t, "never ", "don't ", "do not", "avoid ", "must not")),
    ("is_directive",
     "written as instructions (imperative or 'you are')",
     lambda t, _: _has(t, "you are", "write ", "narrate ", "you control",
                        "maintain ", "keep ", "focus ")),
]

_WRITING_STYLE_CHECKS = [
    ("has_dialogue_format",
     "mentions dialogue formatting (quotes, speech)",
     lambda t, _: _has(t, "dialogue", "quote", "speech", '"', "said")),
    ("has_sensory",
     "mentions sensory detail emphasis",
     lambda t, _: _has(t, "sensory", "smell", "sound", "texture",
                        "touch", "sight", "olfactory", "tactile", "auditory")),
    ("has_pacing",
     "mentions pacing / sentence rhythm",
     lambda t, _: _has(t, "rhythm", "pacing", "sentence", "paragraph",
                        "length", "short", "long", "vary")),
    ("has_show_not_tell",
     "references show/don't-tell or internal thought format",
     lambda t, _: _has(t, "show", "tell", "internal", "italics", "thought")),
]

_WORLD_INFO_CHECKS = [
    ("under_300_words",
     "world_info is ≤ 300 words (injected every beat)",
     lambda t, _: word_count(t) <= 300),
    ("has_proper_nouns",
     "contains world-specific proper nouns",
     lambda t, _: _has_proper_nouns(t)),
    ("has_world_rules",
     "states at least one world rule, danger, or restriction",
     lambda t, _: _has(t, "forbid", "danger", "rare", "fear",
                        "illegal", "restrict", "enforcer", "punish",
                        "magic", "power", "rule", "law", "control",
                        "govern", "prison", "trap", "threat", "hunt",
                        "suppress", "hoard", "execute", "outlaw")),
]

_SCENARIO_CHECKS = [
    ("has_character_names",
     "mentions at least two character names",
     lambda t, ctx: _names_in_text(t, ctx.get("characters", []))),
    ("multi_sentence",
     "is at least 3 sentences",
     lambda t, _: _sentences(t) >= 3),
    ("has_motivation",
     "explains why characters are present / their motivation",
     lambda t, _: _has(t, "because", "after", "track", "follow",
                        "seek", "want", "need", "order", "search",
                        "looking for", "reason", "purpose", "driven",
                        "investigating", "pursuing", "to find", "to learn",
                        "to understand", "motivated", "came", "arrived",
                        "has been", "had been", "sent", "flee", "escape",
                        "hiding", "hunting", "watching")),
]

_WRITING_INSTRUCTIONS_CHECKS = [
    ("has_opening_directive",
     "tells where / how to open the scene",
     lambda t, _: _has(t, "open on", "open with", "start with", "begin",
                        "first beat", "scene open", "open at", "open ")),
    ("has_avoidance",
     "has at least one avoidance directive",
     lambda t, _: _has(t, "avoid", "don't", "never ", "not ", "without")),
    ("references_beats",
     "references beats or scene structure",
     lambda t, _: _has(t, "beat ", "final beat", "last beat", "scene",
                        "opening", "ending", "close")),
]

_CHAR_DESCRIPTION_CHECKS = [
    ("has_physical",
     "describes physical appearance (age, hair, clothing, weapon…)",
     lambda t, _: _has(t, "age", "year", "old", "hair", "eye",
                        "tall", "short", "lean", "gaunt", "wear",
                        "carry", "scar", "robes", "coat", "boots")),
]

_CHAR_SPEECH_STYLE_CHECKS = [
    ("is_specific",
     "gives specific speech manner (tone, habit, cadence)",
     lambda t, _: _has(t, "speaks", "says", "voice", "tone", "often",
                        "rarely", "sentence", "word", "phrase", "uses",
                        "tends", "habit", "clipped", "formal", "curt")),
]

_CHAR_TRIGGERS_CHECKS = [
    ("has_pronoun",
     "includes a pronoun (she/he/they) for lore matching",
     lambda t, _: _has(t, "she", "he", "they", "her", "him", "their")),
    ("has_role_title",
     "includes a role/title descriptor beyond the name",
     lambda t, _: len([x.strip() for x in t.split(",") if x.strip()]) >= 3),
]

_BEAT_CHECKS = [
    ("has_action_verb",
     "instruction contains active verbs / character actions",
     lambda t, _: _has_action_verbs(t)),
    ("is_directional",
     "instruction says WHAT happens, not just HOW to write",
     lambda t, _: _has(t, "both ", "they ", "she ", "he ", "it ",
                        "together", "confront", "step", "decide",
                        "reveal", "move", "enter", "flee", "hear")),
]


def _run_checks(checks: list, gen_text: str, context: dict) -> list[dict]:
    results = []
    for check_id, desc, fn in checks:
        try:
            ok = fn(gen_text, context)
        except Exception:
            ok = False
        results.append({
            "id":     check_id,
            "desc":   desc,
            "result": PASS if ok else WARN,
        })
    return results


def _semantic_score(check_results: list[dict]) -> float:
    if not check_results:
        return 1.0
    return sum(1 for c in check_results if c["result"] == PASS) / len(check_results)


# ── Lenient scene parser ───────────────────────────────────────────────────────

def parse_scene_lenient(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8")
    try:
        sections = _split_sections(raw)
    except Exception:
        return {}

    result: dict = {}
    for key in ("narrator-prompt", "writing-style", "world-info",
                "scenario", "writing-instructions"):
        result[key] = sections.get(key, "").strip()

    result["meta"]        = _parse_kv(sections["meta"]) if "meta" in sections else {}
    result["author_note"] = _parse_kv(sections["author-note"]) if "author-note" in sections else {}
    result["scene_setup"] = _parse_kv(sections["scene-setup"]) if "scene-setup" in sections else {}

    chars: list[dict] = []
    for name, content in sorted(
        [(n, c) for n, c in sections.items() if re.match(r"^character-\d+$", n)],
        key=lambda x: int(x[0].split("-")[1]),
    ):
        chars.append(_parse_kv(content))
    result["characters"] = chars

    if "scene-beats" in sections:
        try:
            beats = _parse_beats(sections["scene-beats"])
            result["beats"] = [
                {"index": b.index, "text": b.text, "has_pause": b.has_pause}
                for b in beats
            ]
        except Exception:
            result["beats"] = []
    else:
        result["beats"] = []

    return result


# ── Quantity diff ──────────────────────────────────────────────────────────────

def _grade(gen_text: str, min_words: int,
           orig_words: int = 0, ratio: float = 0.0) -> tuple[str, int]:
    """Return (grade, effective_min).

    effective_min = max(abs floor, int(orig_words * ratio)) when both are provided.
    This catches compression loss on rich scenes where gen passes the absolute floor
    but is still far below what the original contained.
    """
    wc = word_count(gen_text)
    effective_min = min_words
    if orig_words > 0 and ratio > 0:
        effective_min = max(min_words, int(orig_words * ratio))
    if wc == 0:                return MISSING, effective_min
    if wc < effective_min:     return THIN, effective_min
    return PASS, effective_min


def _quantity_diff(orig: dict, gen: dict) -> tuple[dict, dict, dict, int, int]:
    """Returns (fields, chars, beats, total, passed) for quantity checks."""
    fields: dict = {}
    chars:  list = []
    beats:  dict = {}
    total, passed = 0, 0

    def _chk(key: str, o: str, g: str, min_w: int, ratio: float = 0.0):
        nonlocal total, passed
        total += 1
        grade, eff_min = _grade(g, min_w, word_count(o), ratio)
        if grade == PASS: passed += 1
        fields[key] = {
            "orig_words":    word_count(o),
            "gen_words":     word_count(g),
            "effective_min": eff_min,
            "grade":         grade,
            "orig_snippet":  o[:100].replace("\n", " "),
            "gen_snippet":   g[:100].replace("\n", " "),
        }

    _chk("narrator_prompt",      orig.get("narrator-prompt", ""),      gen.get("narrator-prompt", ""),      _MIN_WORDS["narrator_prompt"],      _RATIO["narrator_prompt"])
    _chk("writing_style",        orig.get("writing-style", ""),        gen.get("writing-style", ""),        _MIN_WORDS["writing_style"],        _RATIO["writing_style"])
    _chk("world_info",           orig.get("world-info", ""),           gen.get("world-info", ""),           _MIN_WORDS["world_info"],           _RATIO["world_info"])
    _chk("scenario",             orig.get("scenario", ""),             gen.get("scenario", ""),             _MIN_WORDS["scenario"],             _RATIO["scenario"])
    _chk("writing_instructions", orig.get("writing-instructions", ""), gen.get("writing-instructions", ""), _MIN_WORDS["writing_instructions"], _RATIO["writing_instructions"])

    for sub in ("location", "time", "atmosphere"):
        _chk(f"scene_setup.{sub}",
             orig.get("scene_setup", {}).get(sub, ""),
             gen.get("scene_setup", {}).get(sub, ""),
             _MIN_WORDS["scene_setup_sub"])   # no ratio for short setup fields

    gen_chars = gen.get("characters", [])
    for i, oc in enumerate(orig.get("characters", [])):
        gc = gen_chars[i] if i < len(gen_chars) else {}
        cr: dict = {"name": oc.get("name", f"char-{i+1}"), "fields": {}}
        for field, mk in [("description", "char_description"),
                          ("personality",  "char_personality"),
                          ("backstory",    "char_backstory"),
                          ("speech_style", "char_speech_style")]:
            total += 1
            ow = word_count(oc.get(field, ""))
            # Only apply ratio when original field was actually populated
            ratio = _RATIO[mk] if ow > 0 else 0.0
            grade, eff_min = _grade(gc.get(field, ""), _MIN_WORDS[mk], ow, ratio)
            if grade == PASS: passed += 1
            cr["fields"][field] = {
                "orig_words":    ow,
                "gen_words":     word_count(gc.get(field, "")),
                "effective_min": eff_min,
                "grade":         grade,
            }
        total += 1
        ot = [t.strip() for t in oc.get("triggers", "").split(",") if t.strip()]
        gt = [t.strip() for t in gc.get("triggers", "").split(",") if t.strip()]
        # Ratio-based trigger floor: when original has many, require proportional coverage
        trig_min = max(_TRIGGER_MIN_COUNT, int(len(ot) * _TRIGGER_RATIO)) if len(ot) >= 4 else 2
        tg = PASS if len(gt) >= trig_min else (THIN if gt else MISSING)
        if tg == PASS: passed += 1
        cr["triggers"] = {
            "orig_count":  len(ot),
            "gen_count":   len(gt),
            "needed":      trig_min,
            "grade":       tg,
        }
        chars.append(cr)

    orig_beats = orig.get("beats", [])
    gen_beats  = gen.get("beats", [])
    total += 1
    bc_grade = PASS if len(gen_beats) == len(orig_beats) else (THIN if gen_beats else MISSING)
    if bc_grade == PASS: passed += 1
    beats["count"] = {"orig": len(orig_beats), "gen": len(gen_beats), "grade": bc_grade}

    for i, ob in enumerate(orig_beats):
        gb = gen_beats[i] if i < len(gen_beats) else {}
        total += 1
        ow = word_count(ob.get("text", ""))
        grade, eff_min = _grade(gb.get("text", ""), _MIN_WORDS["beat_instruction"],
                                ow, _RATIO["beat_instruction"])
        if grade == PASS: passed += 1

        pause_orig = ob.get("has_pause", False)
        pause_gen  = gb.get("has_pause", False)
        # Pause preservation counts toward score only when original beat had a pause
        pause_grade = None
        if pause_orig:
            total += 1
            pause_grade = PASS if pause_gen else MISSING
            if pause_grade == PASS: passed += 1

        beats[f"beat_{i+1}"] = {
            "orig_words":    ow,
            "gen_words":     word_count(gb.get("text", "")),
            "effective_min": eff_min,
            "grade":         grade,
            "pause_orig":    pause_orig,
            "pause_gen":     pause_gen,
            "pause_grade":   pause_grade,   # None = not checked (orig had no pause)
        }

    return fields, chars, beats, total, passed


# ── Semantic diff ──────────────────────────────────────────────────────────────

def _semantic_diff(gen: dict) -> tuple[dict, float]:
    """Returns (semantic_report, semantic_score_0_to_1)."""
    ctx = {"characters": gen.get("characters", [])}
    sem: dict = {}
    all_checks: list[dict] = []

    def _do(key: str, text: str, checks_def: list) -> None:
        results = _run_checks(checks_def, text, ctx)
        sem[key] = results
        all_checks.extend(results)

    _do("narrator_prompt",      gen.get("narrator-prompt", ""),      _NARRATOR_PROMPT_CHECKS)
    _do("writing_style",        gen.get("writing-style", ""),        _WRITING_STYLE_CHECKS)
    _do("world_info",           gen.get("world-info", ""),           _WORLD_INFO_CHECKS)
    _do("scenario",             gen.get("scenario", ""),             _SCENARIO_CHECKS)
    _do("writing_instructions", gen.get("writing-instructions", ""), _WRITING_INSTRUCTIONS_CHECKS)

    gen_chars = gen.get("characters", [])
    sem["characters"] = []
    for gc in gen_chars:
        name = gc.get("name", "?")
        char_sem: dict = {"name": name}
        desc_checks  = _run_checks(_CHAR_DESCRIPTION_CHECKS,  gc.get("description", ""),  ctx)
        speech_checks= _run_checks(_CHAR_SPEECH_STYLE_CHECKS, gc.get("speech_style", ""), ctx)
        trig_checks  = _run_checks(_CHAR_TRIGGERS_CHECKS,     gc.get("triggers", ""),     ctx)
        char_sem["description"]  = desc_checks
        char_sem["speech_style"] = speech_checks
        char_sem["triggers"]     = trig_checks
        sem["characters"].append(char_sem)
        all_checks.extend(desc_checks + speech_checks + trig_checks)

    gen_beats = gen.get("beats", [])
    sem["beats"] = []
    for gb in gen_beats:
        beat_checks = _run_checks(_BEAT_CHECKS, gb.get("text", ""), ctx)
        sem["beats"].append({"index": gb.get("index", "?"), "checks": beat_checks})
        all_checks.extend(beat_checks)

    score = _semantic_score(all_checks) if all_checks else 1.0
    return sem, score


# ── Combined diff ──────────────────────────────────────────────────────────────

def diff_scenes(orig: dict, gen: dict) -> dict:
    fields, chars, beats, q_total, q_passed = _quantity_diff(orig, gen)
    sem, sem_score = _semantic_diff(gen)

    q_score = q_passed / q_total if q_total else 1.0
    combined = round(_QUANTITY_WEIGHT * q_score + _SEMANTIC_WEIGHT * sem_score, 3)

    return {
        "fields":         fields,
        "characters":     chars,
        "beats":          beats,
        "semantic":       sem,
        "q_score":        round(q_score, 3),
        "sem_score":      round(sem_score, 3),
        "score":          combined,
        "q_passed":       q_passed,
        "q_total":        q_total,
    }


# ── Report printer ─────────────────────────────────────────────────────────────

_GRADE_SYM = {PASS: "✓", THIN: "~", MISSING: "✗", WARN: "!"}


def print_diff_report(report: dict, iteration: int) -> None:
    q  = report["q_score"]
    s  = report["sem_score"]
    c  = report["score"]
    print(f"\n{'═'*66}")
    print(f"  DIFF REPORT — iter {iteration}  "
          f"combined={c:.0%}  qty={q:.0%} ({report['q_passed']}/{report['q_total']})  sem={s:.0%}")
    print(f"{'═'*66}")

    sem = report["semantic"]

    print("\n  Top-level fields:")
    for key, info in report["fields"].items():
        sym   = _GRADE_SYM[info["grade"]]
        grade = info["grade"]
        eff   = info.get("effective_min", 0)
        suffix = f"  [need≥{eff}w]" if grade == THIN and eff > _MIN_WORDS.get(key.replace(".", "_"), 0) else ""
        print(f"    {sym} {key:<28}  orig={info['orig_words']:>4}w  gen={info['gen_words']:>4}w  [{grade}]{suffix}")
        if grade != PASS and info["gen_snippet"]:
            print(f"       ↳ gen: {info['gen_snippet'][:76]}")
        for chk in sem.get(key, []):
            if chk["result"] != PASS:
                print(f"       ! {chk['desc']}")

    print()
    for cr in report["characters"]:
        char_name = cr["name"]
        char_sem  = next((cs for cs in sem.get("characters", []) if cs["name"] == char_name), {})
        print(f"  Character: {char_name}")
        for field, fi in cr["fields"].items():
            sym    = _GRADE_SYM[fi["grade"]]
            grade  = fi["grade"]
            eff    = fi.get("effective_min", 0)
            suffix = f"  [need≥{eff}w]" if grade == THIN and eff > _MIN_WORDS.get(f"char_{field}", 0) else ""
            print(f"    {sym} {field:<20} orig={fi['orig_words']:>4}w  gen={fi['gen_words']:>4}w  [{grade}]{suffix}")
            for chk in char_sem.get(field, []):
                if chk["result"] != PASS:
                    print(f"       ! {chk['desc']}")
        ti = cr["triggers"]
        sym    = _GRADE_SYM[ti["grade"]]
        needed = ti.get("needed", 2)
        suffix = f"  [need≥{needed}]" if ti["grade"] != PASS else ""
        print(f"    {sym} triggers              orig={ti['orig_count']:>4}  gen={ti['gen_count']:>4}  [{ti['grade']}]{suffix}")
        for chk in char_sem.get("triggers", []):
            if chk["result"] != PASS:
                print(f"       ! {chk['desc']}")

    print("\n  Beats:")
    bc = report["beats"]["count"]
    print(f"    {_GRADE_SYM[bc['grade']]} count  orig={bc['orig']}  gen={bc['gen']}")
    sem_beats = sem.get("beats", [])
    for i, (k, v) in enumerate([(k2, v2) for k2, v2 in report["beats"].items() if k2 != "count"]):
        sym   = _GRADE_SYM[v["grade"]]
        eff   = v.get("effective_min", 0)
        suffix = f"  [need≥{eff}w]" if v["grade"] == THIN and eff > _MIN_WORDS["beat_instruction"] else ""
        # Pause indicator: [✓pause] or [✗pause] only when original had a pause
        if v.get("pause_orig"):
            pause_sym = _GRADE_SYM.get(v.get("pause_grade", MISSING), "?")
            suffix += f"  [{pause_sym}pause]"
        print(f"    {sym} {k:<12} orig={v['orig_words']:>4}w  gen={v['gen_words']:>4}w  [{v['grade']}]{suffix}")
        if i < len(sem_beats):
            for chk in sem_beats[i].get("checks", []):
                if chk["result"] != PASS:
                    print(f"       ! {chk['desc']}")
    print()


# ── Prose extraction ───────────────────────────────────────────────────────────

def extract_prose(md_path: Path) -> str:
    raw = md_path.read_text(encoding="utf-8")
    lines = []
    for line in raw.splitlines():
        stripped = line.strip()
        if re.match(r"^#{1,3}\s", stripped):
            continue
        if re.match(r"^---+$", stripped):
            continue
        # Drop stale tool-call JSON from bad prior runs
        if stripped.startswith('{"function"') or stripped.startswith('{"role"'):
            continue
        lines.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


# ── JSON repair ───────────────────────────────────────────────────────────────

def _repair_json(raw: str) -> str:
    """Try to close a truncated JSON object by balancing brackets/quotes.

    Only handles simple truncation (model ran out of tokens mid-output).
    Returns the repaired string, or the original if repair is not attempted.
    """
    raw = raw.strip()
    if not raw.startswith("{"):
        return raw

    # Count unclosed string — if an odd number of unescaped quotes trail, close it
    in_string = False
    escape_next = False
    opens: list[str] = []

    for ch in raw:
        if escape_next:
            escape_next = False
            continue
        if ch == "\\" and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if not in_string:
            if ch in ("{", "["):
                opens.append(ch)
            elif ch == "}" and opens and opens[-1] == "{":
                opens.pop()
            elif ch == "]" and opens and opens[-1] == "[":
                opens.pop()

    close = ""
    if in_string:
        close += '"'
    for ch in reversed(opens):
        close += "}" if ch == "{" else "]"

    return raw + close if close else raw


# ── Importer runner ────────────────────────────────────────────────────────────

# Compact system prompt used as fallback when prose is too large for the fast model.
# Drops the detailed field rules — just the essentials — to reduce prompt token overhead.
_SYSTEM_COMPACT = """\
You are a story structure analyst. Extract a Story Engine scene JSON from the prose.

{imagination_clause}

Return this JSON with ALL fields populated:
- title, pov, target_length, scenario, narrator_prompt, writing_style, author_note_content
- world_info (under 300 words), scene_setup (location/time/atmosphere)
- characters (name, role, triggers, description, personality, backstory, speech_style)
- beats (exactly {beat_count}; title ALL-CAPS; instruction 2–4 sentences; pause:true for decision points)
- writing_instructions

Return ONLY valid JSON. No markdown fences."""


def run_import(prose: str, imagination: int, beat_count: int, system_prompt: str) -> dict:
    """Call the importer LLM. Retries with compact prompt on JSON parse failure."""

    def _build_messages(sys: str) -> list[dict]:
        sys_rendered = sys.format(
            imagination_clause=_imagination_clause(imagination),
            beat_count=beat_count,
        )
        prose_safe   = prose.replace("{", "{{").replace("}", "}}")
        user_content = _USER.replace("{story_text}", prose_safe).format()
        return [
            {"role": "system", "content": sys_rendered},
            {"role": "user",   "content": user_content},
        ]

    def _clean(raw: str) -> str:
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        return re.sub(r"\n?```$", "", raw.strip())

    # Attempt 1: full prompt, temperature 0.5
    raw = call_llm(_build_messages(system_prompt), temperature=0.5)
    raw = _clean(raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Attempt 2: try repairing truncated JSON before retrying
    repaired = _repair_json(raw)
    if repaired != raw:
        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            pass

    # Attempt 3: compact prompt at temperature 0 (less creative = more concise)
    print("    ↳ retrying with compact prompt (prose may be near context limit)…")
    raw2 = call_llm(_build_messages(_SYSTEM_COMPACT), temperature=0)
    raw2 = _clean(raw2)
    try:
        return json.loads(raw2)
    except json.JSONDecodeError:
        repaired2 = _repair_json(raw2)
        return json.loads(repaired2)   # raise on final failure — caller handles it


def result_to_scene(result: dict, stem: str, iteration: int) -> tuple[Path, dict]:
    _WORK_DIR.mkdir(parents=True, exist_ok=True)
    out_path = _WORK_DIR / f"{stem}_iter{iteration}.md"

    user_data = {
        "title":         result.get("title", stem),
        "output_file":   str(out_path),
        "pov":           result.get("pov", "third-person"),
        "mode":          "autonomous",
        "target_length": result.get("target_length", 3500),
        "nsfw":          "false",
        "scenario":      result.get("scenario", ""),
        "_loaded":       True,
    }
    generated = {
        "narrator_prompt":      result.get("narrator_prompt", ""),
        "writing_style":        result.get("writing_style", ""),
        "author_note_content":  result.get("author_note_content", ""),
        "world_info":           result.get("world_info", ""),
        "scene_setup":          result.get("scene_setup", {}),
        "characters":           result.get("characters", []),
        "beats":                result.get("beats", []),
        "writing_instructions": result.get("writing_instructions", ""),
    }

    content = assemble(user_data, generated)
    out_path.write_text(content, encoding="utf-8")
    return out_path, parse_scene_lenient(out_path)


# ── Prompt optimizer ───────────────────────────────────────────────────────────

_OPTIMIZER_SYSTEM = """\
You are a prompt engineer improving a story analysis system prompt.

The system prompt instructs an LLM to extract a Story Engine scene JSON from raw prose.
You will receive the CURRENT system prompt and a FAILURE REPORT listing which checks failed.

Rules for your rewrite:
  - Keep {imagination_clause} and {beat_count} placeholders exactly as-is.
  - Do NOT remove any existing field rules — only strengthen or add to them.
  - For every failing check, add a clear, specific instruction that addresses it.
  - If a field rule is vague, make it concrete with an example of what good output looks like.
  - Keep the final line "Return ONLY valid JSON. No markdown fences. No explanation." intact.
  - Return ONLY the new system prompt text. No explanations, no markdown code fences."""


def _failure_report(report: dict, orig: dict) -> str:
    lines = []

    for key, info in report["fields"].items():
        if info["grade"] != PASS:
            lines.append(f"QUANTITY FAIL — {key}: grade={info['grade']} "
                         f"orig={info['orig_words']}w gen={info['gen_words']}w")
            if info["orig_snippet"]:
                lines.append(f"  ORIGINAL: {info['orig_snippet']}")
            if info["gen_snippet"]:
                lines.append(f"  GENERATED: {info['gen_snippet']}")

    sem = report["semantic"]
    for key, checks in sem.items():
        if key in ("characters", "beats"):
            continue
        for chk in (checks or []):
            if chk["result"] != PASS:
                lines.append(f"SEMANTIC FAIL — {key}: {chk['desc']}")

    for cs in sem.get("characters", []):
        name = cs.get("name", "?")
        for field, checks in cs.items():
            if field == "name" or not isinstance(checks, list):
                continue
            for chk in checks:
                if chk["result"] != PASS:
                    lines.append(f"SEMANTIC FAIL — character({name}).{field}: {chk['desc']}")
                    orig_chars = orig.get("characters", [])
                    oc = next((c for c in orig_chars if c.get("name") == name), {})
                    if oc.get(field):
                        lines.append(f"  ORIGINAL {field}: {oc[field][:120]}")

    for i, beat_sem in enumerate(sem.get("beats", [])):
        for chk in beat_sem.get("checks", []):
            if chk["result"] != PASS:
                lines.append(f"SEMANTIC FAIL — beat {i+1}: {chk['desc']}")

    if not lines:
        lines.append("(all checks passed — prompt looks good)")

    return "\n".join(lines)


def optimize_prompt(current_system: str, report: dict, orig: dict) -> str:
    failures = _failure_report(report, orig)
    user_content = (
        f"CURRENT SYSTEM PROMPT:\n{current_system}\n\n"
        f"FAILURE REPORT:\n{failures}\n\n"
        "Rewrite the system prompt to fix the above failures. "
        "Return ONLY the new system prompt."
    )
    improved = call_llm([
        {"role": "system", "content": _OPTIMIZER_SYSTEM},
        {"role": "user",   "content": user_content},
    ], temperature=0.3)
    return improved.strip()


# ── Story engine runner ────────────────────────────────────────────────────────

def generate_prose(scene_path: Path) -> Path:
    print(f"\n  Running story engine on {scene_path.name} …")
    print("  (this may take several minutes)\n")
    r = subprocess.run(
        [sys.executable, "-m", "my_code.main", str(scene_path)],
        cwd=str(Path(__file__).parent.parent),
    )
    if r.returncode != 0:
        print(f"\n  ERROR: story engine exited with code {r.returncode}")
        sys.exit(1)
    from my_code.parser import parse_scene_file
    scene = parse_scene_file(str(scene_path))
    return Path(scene.meta.output_file)


# ── CLI ────────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Story Importer — roundtrip quality test harness",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("scene", metavar="SCENE.MD")
    p.add_argument("--prose", metavar="PATH",
                   help="Existing prose file (skips story engine run)")
    p.add_argument("--skip-generate", action="store_true",
                   help="Do not run the story engine (requires --prose or prior output)")
    p.add_argument("--imagination", type=int, default=50, metavar="0-100")
    p.add_argument("--iters", type=int, default=_DEFAULT_ITERS,
                   help=f"Max improvement iterations (default {_DEFAULT_ITERS})")
    p.add_argument("--auto", action="store_true",
                   help="Automatically apply LLM prompt improvements each iteration")
    p.add_argument("--commit", action="store_true",
                   help="Write the best improved prompt back to single_pass.py")
    return p.parse_args()


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    args = _parse_args()

    scene_path = Path(args.scene)
    if not scene_path.exists():
        print(f"ERROR: {args.scene} not found")
        sys.exit(1)

    stem = slugify(scene_path.stem)
    _WORK_DIR.mkdir(parents=True, exist_ok=True)

    print(f"\n{'═'*66}")
    print(f"  STORY IMPORTER — ROUNDTRIP TEST")
    print(f"  scene    : {scene_path}")
    print(f"  importer : {BASE_URL}  [{MODEL}]")
    print(f"  auto     : {args.auto}   iters: {args.iters}")
    print(f"{'═'*66}")

    # ── Phase 1: prose ────────────────────────────────────────────────────────
    if args.prose:
        prose_path = Path(args.prose)
    elif args.skip_generate:
        from my_code.parser import parse_scene_file
        prose_path = Path(parse_scene_file(str(scene_path)).meta.output_file)
    else:
        prose_path = generate_prose(scene_path)

    if not prose_path.exists():
        print(f"\n  ERROR: Prose file not found: {prose_path}")
        print("  Run without --skip-generate, or pass --prose PATH")
        sys.exit(1)

    prose_text = extract_prose(prose_path)
    wc = word_count(prose_text)
    print(f"\n  Prose  : {prose_path}  ({wc:,} words)")

    clean_prose_path = _WORK_DIR / f"{stem}_prose.txt"
    clean_prose_path.write_text(prose_text, encoding="utf-8")

    orig = parse_scene_lenient(scene_path)
    orig_beat_count = len(orig.get("beats", []))
    print(f"  Original: {len(orig.get('characters', []))} chars, {orig_beat_count} beats")

    # ── Phase 2: loop ────────────────────────────────────────────────────────
    current_system = _sp_module._SYSTEM
    best_score, best_system = 0.0, current_system
    history: list[dict] = []

    for iteration in range(1, args.iters + 1):
        print(f"\n{'─'*66}")
        print(f"  Iteration {iteration}/{args.iters}  —  importing …")

        try:
            result = run_import(prose_text, args.imagination,
                                orig_beat_count or 5, current_system)
        except json.JSONDecodeError as exc:
            print(f"  ERROR: invalid JSON from importer — {exc}")
            continue
        except Exception as exc:
            print(f"  ERROR: {exc}")
            continue

        gen_path, gen = result_to_scene(result, stem, iteration)
        print(f"  Generated: {gen_path}")

        generated_block = {
            "narrator_prompt":      result.get("narrator_prompt", ""),
            "writing_style":        result.get("writing_style", ""),
            "author_note_content":  result.get("author_note_content", ""),
            "world_info":           result.get("world_info", ""),
            "scene_setup":          result.get("scene_setup", {}),
            "characters":           result.get("characters", []),
            "beats":                result.get("beats", []),
            "writing_instructions": result.get("writing_instructions", ""),
        }
        val_errors = validate_generated(generated_block)
        if val_errors:
            print(f"  Validation errors: {len(val_errors)}")
            for e in val_errors[:6]:
                print(f"    ✗ {e}")

        report = diff_scenes(orig, gen)
        print_diff_report(report, iteration)

        history.append({
            "iteration":  iteration,
            "score":      report["score"],
            "q_score":    report["q_score"],
            "sem_score":  report["sem_score"],
            "val_errors": len(val_errors),
            "gen_path":   str(gen_path),
        })

        if report["score"] > best_score:
            best_score  = report["score"]
            best_system = current_system

        # Save prompt used this iteration for inspection
        (_WORK_DIR / f"{stem}_system_iter{iteration}.txt").write_text(
            current_system, encoding="utf-8"
        )

        if report["score"] >= _SATISFACTION:
            print(f"\n  Score {report['score']:.0%} ≥ {_SATISFACTION:.0%} — satisfied!")
            break

        if iteration == args.iters:
            print("\n  Max iterations reached.")
            break

        # ── Improve ────────────────────────────────────────────────────────
        if args.auto:
            print("\n  Auto-improving prompt …")
            try:
                improved = optimize_prompt(current_system, report, orig)
                if "{imagination_clause}" in improved and "{beat_count}" in improved:
                    current_system = improved
                    print(f"  Prompt updated ({word_count(improved)} words).")
                else:
                    print("  WARNING: optimizer dropped required placeholders — keeping current.")
            except Exception as exc:
                print(f"  WARNING: optimizer failed ({exc}) — keeping current.")
        else:
            try:
                raw = input(
                    "\n  Enter=next iteration  |  'improve'=LLM-optimize prompt  |  'stop'=exit: "
                ).strip().lower()
            except (EOFError, KeyboardInterrupt):
                raw = "stop"
            if raw == "stop":
                break
            if raw == "improve":
                print("  Optimizing …")
                try:
                    improved = optimize_prompt(current_system, report, orig)
                    if "{imagination_clause}" in improved and "{beat_count}" in improved:
                        current_system = improved
                        print(f"  Prompt updated ({word_count(improved)} words).")
                    else:
                        print("  WARNING: required placeholders missing — keeping current.")
                except Exception as exc:
                    print(f"  WARNING: optimizer failed ({exc})")

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{'═'*66}")
    print("  SUMMARY")
    print(f"{'═'*66}")
    for h in history:
        print(f"  iter {h['iteration']}  "
              f"combined={h['score']:.0%}  qty={h['q_score']:.0%}  sem={h['sem_score']:.0%}  "
              f"val_errors={h['val_errors']}  → {Path(h['gen_path']).name}")
    print(f"\n  Best combined score: {best_score:.0%}")

    best_path = _WORK_DIR / f"{stem}_system_best.txt"
    best_path.write_text(best_system, encoding="utf-8")
    print(f"  Best prompt saved : {best_path}")

    # ── Commit ────────────────────────────────────────────────────────────────
    if args.commit and best_system != _sp_module._SYSTEM:
        sp_path = Path(__file__).parent / "importers" / "single_pass.py"
        src = sp_path.read_text(encoding="utf-8")
        pattern = re.compile(r'(_SYSTEM\s*=\s*""")[^"]*(?:""")', re.DOTALL)
        new_src = pattern.sub(
            lambda m: m.group(1) + best_system + '"""',
            src, count=1,
        )
        if new_src == src:
            print("\n  WARNING: could not locate _SYSTEM in single_pass.py — not written.")
        else:
            backup = sp_path.with_suffix(".py.bak")
            shutil.copy(sp_path, backup)
            sp_path.write_text(new_src, encoding="utf-8")
            print(f"\n  Backed up: {backup}")
            print(f"  Wrote improved _SYSTEM to: {sp_path}")
    elif args.commit:
        print("\n  Prompt unchanged — nothing to commit.")
    else:
        print(f"\n  To commit best prompt to single_pass.py, re-run with --commit")
    print()


if __name__ == "__main__":
    main()
