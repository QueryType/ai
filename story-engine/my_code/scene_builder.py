#!/usr/bin/env python3
"""
scene_builder.py — Interactive CLI to build Story Engine scene input files.

Uses any OpenAI-compatible chat completion endpoint.

Config (via .env or environment variables):
  SCENE_BUILDER_BASE_URL   — defaults to STORY_ENGINE_LOCAL_BASE_URL
  SCENE_BUILDER_MODEL      — defaults to STORY_ENGINE_EVALUATOR_MODEL, then NARRATOR_MODEL
  SCENE_BUILDER_API_KEY    — defaults to "none" (fine for local servers)

Usage:
  python my_code/scene_builder.py                    # fresh build via interview
  python my_code/scene_builder.py --out PATH         # pre-set output path
  python my_code/scene_builder.py --load PATH        # edit an existing scene file
"""

import argparse
import json
import os
import re
import sys
import textwrap
from pathlib import Path

try:
    from openai import OpenAI
except ImportError:
    print("ERROR: openai package not installed.  Run: pip install openai")
    sys.exit(1)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# ── Config ────────────────────────────────────────────────────────────────────

BASE_URL = (
    os.getenv("SCENE_BUILDER_BASE_URL")
    or os.getenv("STORY_ENGINE_LOCAL_BASE_URL", "http://localhost:8080/v1")
)
MODEL = (
    os.getenv("SCENE_BUILDER_MODEL")
    or os.getenv("STORY_ENGINE_EVALUATOR_MODEL")
    or os.getenv("STORY_ENGINE_NARRATOR_MODEL", "default")
)
API_KEY = os.getenv("SCENE_BUILDER_API_KEY", "none")

# Theme: dark | light | system  (system = no ANSI colors)
# Set via SCENE_BUILDER_THEME env var; --theme CLI arg overrides at runtime.
_THEME: str = os.getenv("SCENE_BUILDER_THEME", "dark").lower()

# ANSI escape sequences
_R = "\033[0m"   # reset

_PALETTES: dict[str, dict[str, str]] = {
    "dark": {
        "header":    "\033[1;96m",   # bold bright-cyan
        "label":     "\033[1;97m",   # bold bright-white
        "beat_num":  "\033[1;93m",   # bold bright-yellow
        "beat_title":"\033[1;93m",   # bold bright-yellow
        "success":   "\033[1;92m",   # bold bright-green
        "error":     "\033[1;91m",   # bold bright-red
        "muted":     "\033[2;37m",   # dim white
        "waiting":   "\033[0;36m",   # cyan
        "divider":   "\033[0;34m",   # blue
        "prompt":    "\033[1;96m",   # bold bright-cyan
    },
    "light": {
        "header":    "\033[1;34m",   # bold blue
        "label":     "\033[1;30m",   # bold dark-gray
        "beat_num":  "\033[1;35m",   # bold magenta
        "beat_title":"\033[1;35m",   # bold magenta
        "success":   "\033[1;32m",   # bold green
        "error":     "\033[1;31m",   # bold red
        "muted":     "\033[0;90m",   # dark gray
        "waiting":   "\033[0;34m",   # blue
        "divider":   "\033[0;90m",   # dark gray
        "prompt":    "\033[1;34m",   # bold blue
    },
    "system": {k: "" for k in (
        "header", "label", "beat_num", "beat_title",
        "success", "error", "muted", "waiting", "divider", "prompt",
    )},
}


def _c(text: str, role: str) -> str:
    """Wrap text in the current theme's ANSI codes for the given role."""
    palette = _PALETTES.get(_THEME, _PALETTES["system"])
    code = palette.get(role, "")
    if not code:
        return text
    return f"{code}{text}{_R}"


def set_theme(name: str):
    """Set the active theme globally. Falls back to 'system' for unknown names."""
    global _THEME
    _THEME = name if name in _PALETTES else "system"


# ── Terminal helpers ──────────────────────────────────────────────────────────

def ask(prompt: str, default: str = "") -> str:
    print()
    print(prompt)
    try:
        val = input(_c("> ", "prompt")).strip()
    except (EOFError, KeyboardInterrupt):
        print("\nAborted.")
        sys.exit(0)
    return val if val else default


def hr(char: str = "─", width: int = 64):
    print(_c(char * width, "divider"))


def wrap(text: str, indent: str = "  ") -> str:
    return textwrap.fill(text, width=72, initial_indent=indent, subsequent_indent=indent)


def slugify(title: str) -> str:
    s = title.lower()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_-]+", "_", s)
    return s.strip("_")


TARGET_LENGTHS = {
    "short": 1500, "s": 1500,
    "medium": 3500, "m": 3500,
    "long": 6000,  "l": 6000,
    "epic": 9000,  "e": 9000,
}


# ── Validation constants ──────────────────────────────────────────────────────

_VALID_ROLES  = {"player-character", "npc", "antagonist", "neutral"}
_VALID_POVS   = {"third-person", "third-person-limited", "first-person", "second-person"}
_VALID_MODES  = {"autonomous", "semi-interactive", "interactive"}

_REQUIRED_TOP   = [
    "narrator_prompt", "writing_style", "author_note_content",
    "world_info", "scene_setup", "characters", "beats", "writing_instructions",
]
_REQUIRED_SETUP = ["location", "time", "atmosphere"]
_REQUIRED_CHAR  = ["name", "role", "triggers", "description", "personality"]
_REQUIRED_BEAT  = ["title", "instruction"]


# ── Phase 1 — Interview ───────────────────────────────────────────────────────

def interview(default_output: str = "") -> dict:
    data: dict = {}

    hr("═")
    print(_c("  STORY ENGINE — SCENE BUILDER", "header"))
    print(_c(f"  endpoint : {BASE_URL}", "muted"))
    print(_c(f"  model    : {MODEL}", "muted"))
    hr("═")
    print("Answer the questions below. Press Enter to accept any default shown in [ ].")
    print()

    data["title"] = ask("Q1  Title of your scene?") or "Untitled Scene"
    slug = slugify(data["title"])
    default_out = default_output or f"output/{slug}.md"
    data["output_file"] = ask(f"    Output file path?  [{default_out}]", default_out)

    hr()
    data["genre_tone"] = ask(
        "Q2  What kind of story is this?\n"
        "    Describe the genre, emotional tone, and key themes.\n"
        "    Stylistic references welcome. ('like Cormac McCarthy', 'Bollywood epic', etc.)"
    )

    hr()
    data["world"] = ask(
        "Q3  Describe your world.\n"
        "    Where and when is this set? Key rules or constraints that create pressure?\n"
        "    Cultural details, time of year, any lore the narrator needs?"
    )

    hr()
    print("Q4  Tell me about your characters.")
    print("    For each one: name, age, role in this scene,")
    print("    physical appearance, personality under pressure, relevant backstory.")
    print("    Type 'done' when all characters are entered.\n")

    characters = []
    n = 1
    while True:
        entry = ask(f"    Character {n}  (or 'done'):")
        if entry.lower() == "done":
            if not characters:
                print("    At least one character is required.")
                continue
            break
        if entry:
            characters.append(entry)
            n += 1
    data["characters"] = characters

    hr()
    data["scenario"] = ask(
        "Q5  What's happening at the very start of this scene?\n"
        "    What tension is already active? Emotional state of the characters?\n"
        "    Any unresolved pressure from before?"
    )

    hr()
    raw_size = ask(
        "Q6  Scene length?\n"
        "    short (~1500 words)  /  medium (~3500)  /  long (~6000)  /  epic (~9000)\n"
        "    [medium]",
        "medium",
    ).lower()
    data["target_length"] = TARGET_LENGTHS.get(raw_size, 3500)

    hr()
    raw_pov = ask(
        "Q7  Point of view?\n"
        "    third-person  /  third-person-limited  /  first-person  /  second-person\n"
        "    [third-person]",
        "third-person",
    ).lower()
    data["pov"] = raw_pov if raw_pov in _VALID_POVS else "third-person"

    hr()
    raw_mode = ask(
        "Q8  Execution mode?\n"
        "    autonomous         — runs all beats unattended\n"
        "    semi-interactive   — pauses at [pause] markers only\n"
        "    interactive        — pauses after every beat\n"
        "    [autonomous]",
        "autonomous",
    ).lower()
    data["mode"] = raw_mode if raw_mode in _VALID_MODES else "autonomous"

    data["nsfw"] = "false"
    return data


# ── Phase 2 — LLM generation (full scene) ────────────────────────────────────

_SYSTEM_FULL = """\
You are a story structure assistant. Given a scene brief, produce a complete JSON object
with all fields needed for a Story Engine scene file.

Rules:
- narrator_prompt: who the narrator is, tense, POV control rules, what it must/must not do
- writing_style: sentence rhythm, dialogue format, sensory emphasis — the HOW of the prose
- author_note_content: one persistent thematic reminder, 1-2 sentences max
- world_info: concise lore injected every beat, STRICTLY under 300 words
- beats: min 3, max 10; each title SHORT and evocative (e.g. "THE DESCENT");
  each instruction is directional (WHAT happens) not prescriptive (HOW to write it)
- character triggers: rich keyword set — name, name variants, pronouns, role titles,
  any descriptive handles that would naturally appear in beat text
- Everything must feel specific to THIS story, never generic template filler

Return ONLY valid JSON. No markdown fences. No explanation outside the JSON."""


def _build_full_prompt(data: dict) -> str:
    beat_count = max(3, min(10, round(data["target_length"] / 700)))
    wpb = data["target_length"] // beat_count
    chars_block = "\n\n".join(f"Character {i+1}:\n{c}" for i, c in enumerate(data["characters"]))

    return f"""\
Build a Story Engine scene structure from this brief.

TITLE: {data["title"]}
GENRE / TONE / THEMES: {data["genre_tone"]}
WORLD / SETTING: {data["world"]}
SCENARIO: {data["scenario"]}
TARGET: {data["target_length"]} words total · {beat_count} beats · ~{wpb} words each
POV: {data["pov"]}

CHARACTERS:
{chars_block}

Return this JSON (all fields required):
{{
  "narrator_prompt": "...",
  "writing_style": "...",
  "author_note_content": "...",
  "world_info": "...",
  "scene_setup": {{
    "location": "...",
    "time": "...",
    "atmosphere": "..."
  }},
  "characters": [
    {{
      "name": "...",
      "role": "player-character|npc|antagonist|neutral",
      "triggers": "comma, separated, keywords",
      "description": "...",
      "personality": "...",
      "backstory": "...",
      "speech_style": "..."
    }}
  ],
  "beats": [
    {{
      "title": "SHORT TITLE",
      "instruction": "2-4 sentences of directional beat guidance",
      "pause": false
    }}
  ],
  "writing_instructions": "scene-specific creative direction"
}}"""


def _call_llm(messages: list, temperature: float = 0.7) -> str:
    """Make a chat completion call and return the content string."""
    client = OpenAI(base_url=BASE_URL, api_key=API_KEY)
    response = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=temperature,
    )
    raw = response.choices[0].message.content.strip()
    # Strip markdown fences if the model added them
    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw.strip())
    return raw


def generate_full(data: dict) -> dict:
    """Generate the complete scene structure from interview answers."""
    print()
    hr()
    print(_c("  Generating scene structure — please wait...", "waiting"))
    hr()
    raw = _call_llm([
        {"role": "system", "content": _SYSTEM_FULL},
        {"role": "user",   "content": _build_full_prompt(data)},
    ])
    return json.loads(raw)


# ── LLM beat helpers (rewrite / extend) ──────────────────────────────────────

_SYSTEM_BEAT = """\
You are a story beat editor. You make targeted edits to individual scene beats.
Return ONLY valid JSON. No markdown fences. No explanation."""


def llm_rewrite_beat(beat: dict, direction: str, context: dict) -> dict:
    """Ask the LLM to rewrite a single beat based on user direction.

    Returns an updated beat dict with title, instruction, and pause preserved.
    """
    prompt = f"""\
Rewrite the following story beat based on the requested changes.

CURRENT BEAT:
Title: {beat["title"]}
Instruction: {beat["instruction"]}

REQUESTED CHANGES:
{direction}

STORY CONTEXT:
Title: {context.get("title", "")}
Scenario: {context.get("scenario", "")}
World: {context.get("world_info", "")}

Return ONLY this JSON:
{{
  "title": "SHORT EVOCATIVE TITLE",
  "instruction": "2-4 sentences of directional beat guidance"
}}"""

    print(_c("  Rewriting beat — please wait...", "waiting"))
    raw = _call_llm([
        {"role": "system", "content": _SYSTEM_BEAT},
        {"role": "user",   "content": prompt},
    ])
    result = json.loads(raw)
    # Preserve the pause flag from the original
    result["pause"] = beat.get("pause", False)
    return result


_SYSTEM_EXTEND = """\
You are a story structure assistant. You extend an existing beat arc with new beats.
Beat titles must be SHORT and evocative. Instructions are directional (WHAT happens),
not prescriptive (HOW to write it). Return ONLY valid JSON. No markdown fences."""


def llm_extend_beats(beats: list, direction: str, count: int, context: dict) -> list:
    """Ask the LLM to generate `count` new beats that continue the arc.

    Returns a list of new beat dicts.
    """
    existing = "\n".join(
        f"{i}. {b['title']}: {b['instruction']}"
        for i, b in enumerate(beats, 1)
    )
    prompt = f"""\
Extend this story beat arc with {count} new beat(s).

EXISTING BEATS:
{existing}

STORY CONTEXT:
Title: {context.get("title", "")}
Scenario: {context.get("scenario", "")}
World: {context.get("world_info", "")}

DIRECTION FOR NEW BEATS:
{direction}

Return ONLY a JSON array of {count} new beat(s):
[
  {{
    "title": "SHORT EVOCATIVE TITLE",
    "instruction": "2-4 sentences of directional beat guidance",
    "pause": false
  }}
]"""

    print(_c(f"  Generating {count} new beat(s) — please wait...", "waiting"))
    raw = _call_llm([
        {"role": "system", "content": _SYSTEM_EXTEND},
        {"role": "user",   "content": prompt},
    ])
    result = json.loads(raw)
    if not isinstance(result, list):
        raise ValueError("LLM did not return a JSON array for beat extension")
    return result


# ── Beat arc review ───────────────────────────────────────────────────────────

def _print_beats(beats: list):
    print()
    for i, b in enumerate(beats, 1):
        pause_tag = _c("  [pause]", "muted") if b.get("pause") else ""
        num   = _c(f"  {i}.", "beat_num")
        title = _c(b["title"], "beat_title")
        print(f"{num} {title}{pause_tag}")
        print(wrap(b["instruction"], indent="     "))
    print()


def review_beats(beats: list, mode: str, context: dict) -> list:
    """Interactive beat arc review. context is used for LLM rewrite/extend calls."""
    hr("═")
    print(_c("  BEAT ARC REVIEW", "header"))
    hr("═")
    _print_beats(beats)

    print("  Commands:")
    print("    ok                        — accept as-is and continue")
    print("    rewrite N <description>   — LLM rewrites beat N based on your direction")
    print("    extend <description>      — LLM adds more beats continuing the story")
    print("    edit N <new text>         — manually replace beat N instruction")
    print("    title N <new title>       — rename beat N")
    print("    pause N                   — toggle [pause] marker on beat N")
    print("    add <instruction>         — append a beat manually")
    print("    remove N                  — delete beat N")
    print("    swap N M                  — swap beats N and M")

    while True:
        cmd = ask("Command [ok]:").strip()
        if not cmd or cmd.lower() == "ok":
            break

        parts = cmd.split(None, 2)
        action = parts[0].lower()

        try:
            # ── LLM rewrite ──────────────────────────────────────────────────
            if action == "rewrite" and len(parts) >= 3:
                n = int(parts[1]) - 1
                if not (0 <= n < len(beats)):
                    print(f"  Beat number out of range (1–{len(beats)}).")
                    continue
                direction = parts[2]
                try:
                    updated = llm_rewrite_beat(beats[n], direction, context)
                    print(f"\n  Rewritten beat {n+1}:")
                    print(f"    Title: {updated['title']}")
                    print(wrap(updated["instruction"], indent="    "))
                    confirm = ask("  Accept? [yes] / 'no' to discard:").strip().lower()
                    if confirm in ("", "yes", "y"):
                        beats[n] = updated
                        print(f"  Beat {n+1} updated.")
                    else:
                        print("  Discarded — original kept.")
                except (json.JSONDecodeError, ValueError) as e:
                    print(f"  LLM returned bad output: {e} — original kept.")

            # ── LLM extend ───────────────────────────────────────────────────
            elif action == "extend" and len(parts) >= 2:
                direction = " ".join(parts[1:])
                remaining = 10 - len(beats)
                if remaining <= 0:
                    print("  Already at maximum 10 beats.")
                    continue
                raw_count = ask(
                    f"  How many beats to add? (max {remaining})  [{min(2, remaining)}]",
                    str(min(2, remaining)),
                ).strip()
                try:
                    count = max(1, min(remaining, int(raw_count)))
                except ValueError:
                    count = min(2, remaining)
                try:
                    new_beats = llm_extend_beats(beats, direction, count, context)
                    print(f"\n  {len(new_beats)} new beat(s) generated:")
                    for i, b in enumerate(new_beats, len(beats) + 1):
                        print(f"    {i}. {b.get('title', '?')}")
                        print(wrap(b.get("instruction", ""), indent="       "))
                    confirm = ask("  Append these? [yes] / 'no' to discard:").strip().lower()
                    if confirm in ("", "yes", "y"):
                        beats.extend(new_beats)
                        print(f"  {len(new_beats)} beat(s) appended. Total: {len(beats)}")
                    else:
                        print("  Discarded.")
                except (json.JSONDecodeError, ValueError) as e:
                    print(f"  LLM returned bad output: {e} — no beats added.")

            # ── Manual edit ──────────────────────────────────────────────────
            elif action == "edit" and len(parts) >= 3:
                n = int(parts[1]) - 1
                beats[n]["instruction"] = parts[2]
                print(f"  Beat {n+1} updated.")

            elif action == "title" and len(parts) >= 3:
                n = int(parts[1]) - 1
                beats[n]["title"] = parts[2].upper()
                print(f"  Beat {n+1} renamed.")

            elif action == "pause" and len(parts) == 2:
                n = int(parts[1]) - 1
                beats[n]["pause"] = not beats[n].get("pause", False)
                state = "ON" if beats[n]["pause"] else "OFF"
                print(f"  Pause {state} for beat {n+1}.")

            elif action == "add" and len(parts) >= 2:
                if len(beats) >= 10:
                    print("  Already at maximum 10 beats.")
                    continue
                instruction = " ".join(parts[1:])
                beats.append({"title": f"BEAT {len(beats)+1}", "instruction": instruction, "pause": False})
                print(f"  Beat {len(beats)} added.")

            elif action == "remove" and len(parts) == 2:
                n = int(parts[1]) - 1
                removed = beats.pop(n)
                print(f"  Removed: {removed['title']}")

            elif action == "swap" and len(parts) == 3:
                n, m = int(parts[1]) - 1, int(parts[2]) - 1
                beats[n], beats[m] = beats[m], beats[n]
                print(f"  Swapped beats {n+1} and {m+1}.")

            else:
                print("  Unrecognised command — try again.")
                continue

        except (ValueError, IndexError) as e:
            print(f"  Error: {e}")
            continue

        _print_beats(beats)

    # Remind about pauses if semi-interactive and none set
    if mode == "semi-interactive" and not any(b.get("pause") for b in beats):
        print("  Note: mode is semi-interactive but no [pause] markers are set.")
        raw = ask("  Enter beat numbers to pause at (space-separated), or Enter to skip:").strip()
        if raw:
            for token in raw.split():
                try:
                    beats[int(token) - 1]["pause"] = True
                except (ValueError, IndexError):
                    pass

    return beats


# ── Section review ────────────────────────────────────────────────────────────

def review_voice(generated: dict):
    hr("═")
    print(_c("  NARRATOR VOICE & STYLE", "header"))
    hr("═")
    print("\nNarrator prompt:")
    print(wrap(generated["narrator_prompt"]))
    print("\nWriting style:")
    print(wrap(generated["writing_style"]))
    print()

    if ask("Any changes to narrator voice or style?  (Enter to skip, or describe what to change):").strip():
        new_np = ask("  New narrator prompt (full replacement, or Enter to keep):").strip()
        if new_np:
            generated["narrator_prompt"] = new_np
        new_ws = ask("  New writing style (full replacement, or Enter to keep):").strip()
        if new_ws:
            generated["writing_style"] = new_ws


def review_triggers(generated: dict):
    hr("═")
    print(_c("  CHARACTER TRIGGERS", "header"))
    hr("═")
    print("  These keywords activate a character's card when they appear in beat text.")
    print("  Make sure they cover every way you'll refer to each character.\n")

    for char in generated["characters"]:
        print(f"  {char['name']}:")
        print(wrap(char["triggers"], indent="    "))
        new = ask(f"  Edit triggers for {char['name']}?  (Enter to keep, or type new list):").strip()
        if new:
            char["triggers"] = new


# ── Load existing scene file ──────────────────────────────────────────────────

class LoadError(Exception):
    pass


def _split_sections(text: str) -> dict:
    """Split raw file text on [section-name] markers."""
    section_re = re.compile(r"^\[([a-z][a-z0-9_-]*)\]\s*$", re.MULTILINE)
    matches = list(section_re.finditer(text))
    if not matches:
        raise LoadError("No [section] markers found — not a valid scene file.")
    sections = {}
    for i, m in enumerate(matches):
        name = m.group(1)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections[name] = text[start:end].strip()
    return sections


def _parse_kv(text: str) -> dict:
    """Parse key: value lines, handling multi-line continuation and YAML > folding."""
    result = {}
    current_key = None
    current_lines = []

    for line in text.splitlines():
        kv = re.match(r"^([a-z_]+)\s*:\s*(.*)", line)
        if kv:
            if current_key is not None:
                result[current_key] = " ".join(l for l in current_lines if l).strip()
            current_key = kv.group(1)
            value = kv.group(2).strip()
            current_lines = [] if value == ">" else [value]
        elif current_key is not None and line.strip():
            current_lines.append(line.strip())

    if current_key is not None:
        result[current_key] = " ".join(l for l in current_lines if l).strip()

    return result


def _parse_beats_from_text(text: str) -> list:
    """Parse numbered beat list from scene-beats section text."""
    beat_re = re.compile(r"^(\d+)\.\s+", re.MULTILINE)
    matches = list(beat_re.finditer(text))
    if not matches:
        raise LoadError("[scene-beats]: No numbered beats found.")

    beats = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        raw = text[start:end].strip()
        has_pause = "[pause]" in raw
        instruction = re.sub(r"\[pause\]", "", raw).strip()
        instruction = re.sub(r"\s+", " ", instruction)
        # First line may be an evocative title (all caps), rest is the instruction
        lines = instruction.splitlines()
        if lines and re.match(r"^[A-Z &\-']+$", lines[0].strip()):
            title = lines[0].strip()
            instruction = " ".join(lines[1:]).strip() or title
        else:
            title = f"BEAT {m.group(1)}"
        beats.append({"title": title, "instruction": instruction, "pause": has_pause})
    return beats


_REQUIRED_SECTIONS = ("meta", "narrator-prompt", "writing-style", "world-info", "scenario", "scene-beats")


def load_scene_file(path_str: str) -> tuple[dict, dict]:
    """Parse an existing scene .md file into (user_data, generated) dicts.

    Raises LoadError with a descriptive message if the file is missing required
    sections or has malformed content.
    """
    path = Path(path_str)
    if not path.exists():
        raise LoadError(f"File not found: {path_str}")
    if path.suffix.lower() != ".md":
        raise LoadError(f"Expected a .md file, got: {path.suffix}")

    text = path.read_text(encoding="utf-8")
    sections = _split_sections(text)

    # Check required sections
    missing = [s for s in _REQUIRED_SECTIONS if s not in sections]
    if missing:
        raise LoadError(f"Missing required section(s): {', '.join(f'[{s}]' for s in missing)}")

    if not any(k.startswith("character-") for k in sections):
        raise LoadError("No [character-N] sections found — at least one is required.")

    # Parse meta
    meta = _parse_kv(sections["meta"])
    required_meta = ("title", "mode", "output_file", "output_format", "pov")
    missing_meta = [k for k in required_meta if k not in meta]
    if missing_meta:
        raise LoadError(f"[meta] missing required field(s): {', '.join(missing_meta)}")

    # Parse characters
    char_sections = sorted(
        [(name, content) for name, content in sections.items() if name.startswith("character-")],
        key=lambda x: int(re.search(r"\d+", x[0]).group()),
    )
    characters = []
    for name, content in char_sections:
        kv = _parse_kv(content)
        missing_char = [f for f in ("name", "role", "triggers", "description", "personality") if f not in kv]
        if missing_char:
            raise LoadError(f"[{name}] missing required field(s): {', '.join(missing_char)}")
        characters.append({
            "name":        kv["name"],
            "role":        kv["role"],
            "triggers":    kv["triggers"],
            "description": kv["description"],
            "personality": kv["personality"],
            "backstory":   kv.get("backstory", ""),
            "speech_style": kv.get("speech_style", ""),
        })

    # Parse scene-setup (optional fields)
    setup_kv = _parse_kv(sections.get("scene-setup", ""))
    scene_setup = {
        "location":   setup_kv.get("location", ""),
        "time":       setup_kv.get("time", ""),
        "atmosphere": setup_kv.get("atmosphere", ""),
    }

    # Parse beats
    beats = _parse_beats_from_text(sections["scene-beats"])
    if not beats:
        raise LoadError("[scene-beats]: No beats parsed.")

    # Parse author-note
    author_note_content = ""
    if "author-note" in sections:
        an_kv = _parse_kv(sections["author-note"])
        author_note_content = an_kv.get("content", "")

    # Build user_data and generated dicts
    user_data = {
        "title":        meta["title"],
        "output_file":  meta["output_file"],
        "pov":          meta["pov"],
        "mode":         meta["mode"],
        "target_length": int(meta.get("target_length", "3500")),
        "nsfw":         meta.get("nsfw", "false"),
        "scenario":     sections["scenario"],
        # Not stored in file — set sentinels so validate_user_data passes
        "genre_tone":   "(loaded from file)",
        "world":        "(loaded from file)",
        "characters":   [],   # raw text not stored; not needed for assembly
        "_loaded":      True,
    }

    generated = {
        "narrator_prompt":    sections["narrator-prompt"],
        "writing_style":      sections["writing-style"],
        "author_note_content": author_note_content,
        "world_info":         sections["world-info"],
        "scene_setup":        scene_setup,
        "characters":         characters,
        "beats":              beats,
        "writing_instructions": sections.get("writing-instructions", ""),
    }

    return user_data, generated


# ── Validation ────────────────────────────────────────────────────────────────

class ValidationError(Exception):
    pass


def validate_user_data(data: dict) -> list:
    errors = []
    if not data.get("title", "").strip():
        errors.append("title is empty")
    if not data.get("output_file", "").strip():
        errors.append("output_file is empty")
    # genre_tone and world are only meaningful for fresh builds
    if not data.get("_loaded"):
        if not data.get("genre_tone", "").strip():
            errors.append("genre/tone description is empty")
        if not data.get("world", "").strip():
            errors.append("world description is empty")
        if not data.get("characters"):
            errors.append("no characters provided")
    if not data.get("scenario", "").strip():
        errors.append("scenario is empty")
    if data.get("pov") not in _VALID_POVS:
        errors.append(f"pov '{data.get('pov')}' must be one of: {', '.join(sorted(_VALID_POVS))}")
    if data.get("mode") not in _VALID_MODES:
        errors.append(f"mode '{data.get('mode')}' must be one of: {', '.join(sorted(_VALID_MODES))}")
    if not isinstance(data.get("target_length"), int) or data["target_length"] < 500:
        errors.append("target_length must be an integer >= 500")
    return errors


def validate_generated(gen: dict) -> list:
    errors = []

    for key in _REQUIRED_TOP:
        if not gen.get(key):
            errors.append(f"missing or empty: '{key}'")

    setup = gen.get("scene_setup", {})
    if not isinstance(setup, dict):
        errors.append("'scene_setup' must be an object")
    else:
        for key in _REQUIRED_SETUP:
            if not setup.get(key, "").strip():
                errors.append(f"scene_setup.{key} is empty")

    characters = gen.get("characters", [])
    if not isinstance(characters, list) or len(characters) == 0:
        errors.append("'characters' must be a non-empty list")
    else:
        for i, char in enumerate(characters, 1):
            if not isinstance(char, dict):
                errors.append(f"character {i} is not an object")
                continue
            for field in _REQUIRED_CHAR:
                if not char.get(field, "").strip():
                    errors.append(f"character {i} ({char.get('name', '?')}): '{field}' is empty")
            if char.get("role", "") not in _VALID_ROLES:
                errors.append(
                    f"character {i} ({char.get('name', '?')}): "
                    f"role '{char.get('role')}' must be one of: {', '.join(sorted(_VALID_ROLES))}"
                )
            triggers = [t.strip() for t in char.get("triggers", "").split(",") if t.strip()]
            if len(triggers) < 2:
                errors.append(
                    f"character {i} ({char.get('name', '?')}): "
                    f"triggers has only {len(triggers)} entry — add pronouns/titles"
                )

    beats = gen.get("beats", [])
    if not isinstance(beats, list):
        errors.append("'beats' must be a list")
    elif len(beats) < 3:
        errors.append(f"beat count is {len(beats)} — minimum is 3")
    elif len(beats) > 10:
        errors.append(f"beat count is {len(beats)} — maximum is 10")
    else:
        for i, beat in enumerate(beats, 1):
            if not isinstance(beat, dict):
                errors.append(f"beat {i} is not an object")
                continue
            for field in _REQUIRED_BEAT:
                if not beat.get(field, "").strip():
                    errors.append(f"beat {i}: '{field}' is empty")
            instr = beat.get("instruction", "")
            if len(instr.split()) < 10:
                errors.append(f"beat {i} instruction is very short ({len(instr.split())} words)")

    world_info = gen.get("world_info", "")
    wc = len(world_info.split())
    if wc > 300:
        errors.append(f"world_info is {wc} words — must be under 300 (injected every beat)")

    return errors


def run_validation(user_data: dict, generated: dict) -> bool:
    all_errors = validate_user_data(user_data) + validate_generated(generated)
    if not all_errors:
        return True
    hr("═")
    print(_c(f"  VALIDATION — {len(all_errors)} problem(s) found", "error"))
    hr("═")
    for err in all_errors:
        print(_c(f"  ✗  {err}", "error"))
    print()
    return False


# ── Blank template (for manual authoring) ────────────────────────────────────

_BLANK_TEMPLATE = """\
# ============================================================
# STORY ENGINE INPUT FILE
# Fill in every <<PLACEHOLDER>> field, then run with:
#   python -m my_code <this_file>
# Reference: docs/USER_GUIDE.md  |  docs/SCENE_BUILDER.md
# ============================================================

[meta]
title: <<Your Scene Title>>
version: 1.0
mode: autonomous
pause_at: beat
output_file: output/<<scene_filename>>.md
output_format: prose
pov: third-person
target_length: 3500
language: en
nsfw: false

# mode options      : autonomous | semi-interactive | interactive
# output_format     : prose | adventure | script
# pov options       : third-person | third-person-limited | first-person | second-person
# target_length     : short=1500  medium=3500  long=6000  epic=9000


[narrator-prompt]
<<Who is the narrator? Set tense, POV control rules, and what it must/must not do.

Example:
You are the narrator of a dark fantasy world. Write in third-person past tense.
You control all characters except those marked role: player-character — never make
decisions for them. Introduce NPCs through action and dialogue, not description dumps.
Never break character. Never summarize — show through scene.>>


[writing-style]
<<How does the narrator write? Rhythm, dialogue format, sensory focus.

Example:
Literary fiction. Show don't tell. Paragraph breaks for pacing.
Dialogue in double quotes. Internal thoughts in italics.
Vary sentence length — short for action, long for landscape and dread.
Lean on smell, sound, and texture, not just visuals.
Avoid purple prose. Keep metaphors earned.>>


[author-note]
depth: 5
content: <<One persistent thematic reminder injected every N beats (depth controls N).
Example: Maintain tension. Don't resolve conflicts prematurely. Keep character
motivations consistent with their cards.>>


[world-info]
<<Global lore injected into every beat. KEEP UNDER 300 WORDS.

Include: location/geography, time period, key rules or constraints that create
pressure, cultural details, factions, anything the narrator needs as constant
background. Be specific — generic lore produces generic prose.

Do NOT put character backstory here — that goes in the character cards.

Example:
Ashenveil is a crumbling empire on the edge of collapse. Magic is rare and feared.
The ruling Conclave of Scribes hoards all written knowledge. Outside the capital,
the land is wild — old ruins hold power that predates the empire. The common people
are largely illiterate by design. Conclave enforcers wear grey coats with a red wax
seal. Deserters are executed on sight.>>


[character-1]
name: <<Full Name>>
role: <<player-character | npc | antagonist | neutral>>
triggers: <<Comma-separated keywords the lore injector scans for in beat text.
Cover: name, name variants, pronouns (he/she/they/him/her), role titles,
descriptive handles that might appear in beats ("the old man", "the scout").
Example: Lyra, she, her, Voss, the scout, the woman, the deserter>>
description: >
  <<Physical appearance, age, key visible details. Be specific and sensory.
  Example: Lyra Voss is a 28-year-old deserter. Lean, dark-haired, perpetually
  wary. She carries a shortbow and a knife she has never cleaned.>>
personality: <<Core traits and how they behave under pressure.
Example: Stubborn, darkly funny, distrustful of authority. Compartmentalises guilt.>>
backstory: >
  <<Relevant history for THIS scene only — not a full biography.
  Example: Deserted three years ago after being ordered to burn a village.
  Has been running ever since. Knows enough to be dangerous — and hunted.>>
speech_style: <<How they talk — rhythm, vocabulary, dialect, deflection patterns.
Example: Clipped sentences. Sarcasm as deflection. Rarely says what she means.
Asks questions she already knows the answer to.>>


[character-2]
name: <<Full Name>>
role: <<player-character | npc | antagonist | neutral>>
triggers: <<name, pronouns, titles, descriptive handles — comma separated>>
description: >
  <<Physical appearance, age, key details.>>
personality: <<Core traits and behaviour under pressure.>>
backstory: >
  <<Relevant history for this scene.>>
speech_style: <<How they talk.>>


[scene-setup]
location: <<Specific, evocative location.
Example: Ancient stone ruins at the forest edge, half-swallowed by blackthorn vines.
Dense fog rolling in from the east.>>
time: <<Time of day, season, light conditions.
Example: Late afternoon, autumn. Sun low, temperature dropping sharply.>>
atmosphere: <<Mood, sensory texture, emotional undertone.
Example: Dread and exhaustion. The fog carries a smell of old ash and something
sweeter underneath — wrong, like flowers at a funeral.>>


[scenario]
<<The backstory leading into this scene — read ONCE at scene start, not repeated.
What are the characters doing as the scene opens? What pressure is already active?
What emotional state are they in? Any unresolved tension from before?

Keep it to 2-4 tight paragraphs. Orient the narrator — don't write a plot summary.

Example:
Lyra has been tracking Brother Aldric for three days after he was spotted near the
Ashenveil ruins. She tracked him here not because she was ordered to, but because she
wants to know why a disgraced monk is poking around a place that got two of her former
colleagues killed. She doesn't know if he's a threat, a fool, or bait. She catches up
to him just as he is about to step through the entrance archway.>>


[scene-beats]
1. <<BEAT TITLE — short, all caps, evocative. E.g. THE APPROACH>>
   <<What happens in this beat — 2-4 directional sentences.
   Tell the narrator WHAT to show, not HOW to write it.
   Example: Lyra watches Aldric from cover in the treeline. Establish the atmosphere —
   the fog, the smell, the wrongness of this place. He hasn't seen her yet.>>

2. <<BEAT TITLE>>
   <<What happens in beat 2.>>
   [pause]

3. <<BEAT TITLE>>
   <<What happens in beat 3. Add or remove beats as needed. Min 3, max 10.
   Add [pause] on a new line under a beat to pause in semi-interactive mode.>>


[writing-instructions]
<<Scene-specific creative direction — read once at scene start.
Where should the narrator open? What to emphasise? What to avoid?
What tone or image should the scene close on?

Example:
Open on Lyra already in position — she has been watching for ten minutes.
Don't start with her arriving. The ruins should feel like a presence, not a backdrop.
Let Aldric be genuinely disarming in beat 2 — he should seem at peace with things
Lyra hasn't faced. End on an image, not an action.>>
"""


def write_blank_template(out_path_str: str):
    """Write the blank template with hints to disk and report."""
    out_path = Path(out_path_str)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(_BLANK_TEMPLATE, encoding="utf-8")
    hr("═")
    print(_c(f"  Blank template written: {out_path}", "success"))
    hr("═")
    print()
    print("  Open the file in your editor and replace every <<PLACEHOLDER>> field.")
    print("  When done, run it directly:")
    print(f"    python -m my_code {out_path}")
    print()
    print("  Or load it back into the scene builder for LLM-assisted beat editing:")
    print(f"    python my_code/scene_builder.py --load {out_path}")
    print()


# ── Template assembly (generated/loaded scenes) ───────────────────────────────

_TEMPLATE = """\
# ============================================================
# STORY ENGINE INPUT FILE
# ============================================================

[meta]
title: {title}
version: 1.0
mode: {mode}
pause_at: beat
output_file: {output_file}
output_format: prose
pov: {pov}
target_length: {target_length}
language: en
nsfw: {nsfw}


[narrator-prompt]
{narrator_prompt}


[writing-style]
{writing_style}


[author-note]
depth: {author_note_depth}
content: {author_note_content}


[world-info]
{world_info}


{character_blocks}

[scene-setup]
location: {location}
time: {time}
atmosphere: {atmosphere}


[scenario]
{scenario}


[scene-beats]
{beats_block}

[writing-instructions]
{writing_instructions}
"""


def _format_character_block(i: int, char: dict) -> str:
    lines = [
        f"[character-{i}]",
        f"name: {char['name']}",
        f"role: {char['role']}",
        f"triggers: {char['triggers']}",
        "description: >",
        f"  {char['description']}",
        f"personality: {char['personality']}",
    ]
    if char.get("backstory"):
        lines += ["backstory: >", f"  {char['backstory']}"]
    if char.get("speech_style"):
        lines.append(f"speech_style: {char['speech_style']}")
    return "\n".join(lines)


def _format_beats(beats: list) -> str:
    parts = []
    for i, beat in enumerate(beats, 1):
        instruction = beat["instruction"].strip()
        wrapped = textwrap.fill(
            instruction, width=72,
            initial_indent="   ",
            subsequent_indent="   ",
        )
        parts.append(f"{i}. {beat['title']}\n{wrapped}")
        if beat.get("pause"):
            parts.append("   [pause]")
        parts.append("")
    return "\n".join(parts)


def assemble(user_data: dict, generated: dict) -> str:
    char_blocks = "\n\n".join(
        _format_character_block(i, c)
        for i, c in enumerate(generated["characters"], 1)
    )
    beat_count = len(generated["beats"])
    depth = min(5, beat_count)
    setup = generated["scene_setup"]

    return _TEMPLATE.format(
        title=user_data["title"],
        mode=user_data["mode"],
        output_file=user_data["output_file"],
        pov=user_data["pov"],
        target_length=user_data["target_length"],
        nsfw=user_data["nsfw"],
        narrator_prompt=generated["narrator_prompt"],
        writing_style=generated["writing_style"],
        author_note_depth=depth,
        author_note_content=generated["author_note_content"],
        world_info=generated["world_info"],
        character_blocks=char_blocks,
        location=setup["location"],
        time=setup["time"],
        atmosphere=setup["atmosphere"],
        scenario=user_data["scenario"],
        beats_block=_format_beats(generated["beats"]),
        writing_instructions=generated["writing_instructions"],
    )


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Story Engine — Scene Builder")
    parser.add_argument("--out",      metavar="PATH", help="Output file path (skips the prompt)")
    parser.add_argument("--load",     metavar="PATH", help="Load and edit an existing scene file")
    parser.add_argument("--template", metavar="PATH", nargs="?", const="output/blank_scene.md",
                        help="Write a blank template with hints and exit "
                             "(default path: output/blank_scene.md)")
    parser.add_argument("--theme", choices=["dark", "light", "system"], default=None,
                        help="Color theme: dark | light | system (no colors). "
                             "Overrides SCENE_BUILDER_THEME env var.")
    args = parser.parse_args()

    # Apply theme (CLI arg beats env var)
    if args.theme:
        set_theme(args.theme)

    # ── Blank template mode — no LLM, no interview ────────────────────────────
    if args.template is not None:
        write_blank_template(args.template)
        sys.exit(0)

    hr("═")
    print(_c("  STORY ENGINE — SCENE BUILDER", "header"))
    print(_c(f"  endpoint : {BASE_URL}", "muted"))
    print(_c(f"  model    : {MODEL}", "muted"))
    print(_c(f"  theme    : {_THEME}", "muted"))
    hr("═")

    # ── Load mode ─────────────────────────────────────────────────────────────
    if args.load:
        print(_c(f"\n  Loading: {args.load}", "waiting"))
        try:
            user_data, generated = load_scene_file(args.load)
        except LoadError as e:
            print(_c(f"\n  ERROR: {e}", "error"))
            print("  File must be a valid Story Engine scene file.")
            sys.exit(1)

        print(_c(f"  Loaded: '{user_data['title']}' — {len(generated['beats'])} beats", "success"))

        # Allow overriding the output path after load
        if args.out:
            user_data["output_file"] = args.out
        else:
            new_out = ask(
                f"  Output file path?  [{user_data['output_file']}]\n"
                "  (Enter to overwrite the source file, or type a new path)"
            ).strip()
            if new_out:
                user_data["output_file"] = new_out

        context = {
            "title":      user_data["title"],
            "scenario":   user_data["scenario"],
            "world_info": generated["world_info"],
        }

        generated["beats"] = review_beats(generated["beats"], user_data["mode"], context)
        review_voice(generated)
        review_triggers(generated)

    # ── Fresh build mode ──────────────────────────────────────────────────────
    else:
        user_data = interview(default_output=args.out or "")

        try:
            generated = generate_full(user_data)
        except json.JSONDecodeError as e:
            print(_c(f"\nERROR: Model returned invalid JSON — {e}", "error"))
            print("Try a more capable model or simplify your inputs.")
            sys.exit(1)
        except Exception as e:
            print(_c(f"\nERROR: {e}", "error"))
            sys.exit(1)

        context = {
            "title":      user_data["title"],
            "scenario":   user_data["scenario"],
            "world_info": generated.get("world_info", ""),
        }

        generated["beats"] = review_beats(generated["beats"], user_data["mode"], context)
        review_voice(generated)
        review_triggers(generated)

    # ── Validate & write ──────────────────────────────────────────────────────
    if not run_validation(user_data, generated):
        print(_c("  Scene file NOT written. Fix the issues above and re-run.", "error"))
        print(_c("  Tip: if the model produces bad JSON, set SCENE_BUILDER_MODEL", "muted"))
        print(_c("       to a more capable model.", "muted"))
        sys.exit(1)

    content = assemble(user_data, generated)
    out_path = Path(user_data["output_file"])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")

    hr("═")
    print(_c(f"  Written: {out_path}", "success"))
    hr("═")
    print()
    print(_c("Run the scene:", "label"))
    print(f"  conda activate strandsagents")
    print(f"  python -m my_code {out_path}")
    print()


if __name__ == "__main__":
    main()
