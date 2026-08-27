"""Deterministic composition of final positive/negative prompts from a scene +
the story bible. No LLM call here -- consistency comes from injecting the exact
same fixed descriptor text for a character/setting every time it appears.

Different model families expect structurally different prompts:

- "prose": full natural-language sentences (subject -> environment -> style),
  no negative prompt. Matches FLUX.2 (Klein/pro/max) and Z-Image, which run
  a T5/Qwen-style text encoder trained on narrative descriptions, not
  comma-separated tags, and are typically run at cfg=1 / guidance=0 where a
  negative prompt has no effect at all.
- "tags": comma-separated keyword/phrase list following the
  (Subject/Action), (Environment), (Style), (Lighting), (Technical) formula,
  plus an effective negative prompt. Matches SDXL-family checkpoints
  (Juggernaut XL and similar), run with CLIP text encoders and cfg 6-7.

MODEL_FAMILY_STYLES maps a few known checkpoints to their style as a
convenience default for --model-family; --prompt-style overrides it directly
for anything not listed.
"""

from __future__ import annotations

PROMPT_STYLES = ("prose", "tags")

MODEL_FAMILY_STYLES = {
    "flux2": "prose",
    "zimage": "prose",
    "sdxl": "tags",
}

# Hedge phrases the bible stage sometimes emits when a chunk gave the LLM
# nothing concrete to describe -- e.g. "appearance remains undefined". These
# read as filler/apology text if injected verbatim into a prompt, so a
# character/setting whose fixed text contains one of these is dropped from
# the composed prompt entirely rather than describing the absence of a
# description.
_UNGROUNDED_MARKERS = (
    "no concrete visual description",
    "not provided in the",
    "remains undefined",
    "not specified",
    "no visual description",
    "not described",
)


def _is_grounded(text: str) -> bool:
    lowered = text.lower()
    return bool(text.strip()) and not any(marker in lowered for marker in _UNGROUNDED_MARKERS)


def _index_by_name(entries: list[dict], name_key: str = "name") -> dict:
    idx = {}
    for e in entries:
        idx[e[name_key].lower()] = e
        for alias in e.get("aliases", []):
            idx[alias.lower()] = e
    return idx


def _sentence(text: str) -> str:
    text = text.strip()
    if not text:
        return text
    text = text[0].upper() + text[1:]
    if text[-1] not in ".!?":
        text += "."
    return text


def _entity_clauses(names: list[str], idx: dict, desc_key: str) -> list[str]:
    clauses = []
    for name in names:
        entry = idx.get(name.lower())
        if not entry:
            continue
        desc = entry[desc_key].strip()
        if not _is_grounded(desc):
            continue
        # Appositive form ("Jeeves, a highly competent valet...") reads as a
        # clause in both prose and tag composition, and avoids the
        # "Name: description" label/colon look of a data dump.
        canonical = entry["name"]
        if desc.lower().startswith(canonical.lower()):
            clauses.append(desc)
        else:
            clauses.append(f"{canonical}, {desc}")
    return clauses


def _build_prose(scene: dict, char_clauses: list[str], setting_clauses: list[str], style_suffix: str) -> str:
    sentences = [_sentence(scene["description"])]
    sentences += [_sentence(c) for c in char_clauses]
    sentences += [_sentence(c) for c in setting_clauses]
    if style_suffix:
        sentences.append(_sentence(f"Rendered in {style_suffix}"))
    return " ".join(sentences)


def _build_tags(scene: dict, char_clauses: list[str], setting_clauses: list[str], style_suffix: str) -> str:
    parts = [scene["description"].strip()] + char_clauses + setting_clauses
    if style_suffix:
        parts.append(style_suffix)
    return ", ".join(p for p in parts if p)


def build_prompt(
    scene: dict,
    bible: dict,
    global_negative_prompt: str = "",
    seed: int | None = None,
    style: str = "prose",
) -> dict:
    if style not in PROMPT_STYLES:
        raise ValueError(f"unknown prompt style {style!r}, expected one of {PROMPT_STYLES}")

    char_idx = _index_by_name(bible.get("characters", []))
    setting_idx = _index_by_name(bible.get("settings", []))

    char_clauses = _entity_clauses(scene.get("characters_present", []), char_idx, "fixed_appearance")
    setting_clauses = _entity_clauses(scene.get("settings_present", []), setting_idx, "fixed_desc")
    style_suffix = bible.get("global_style", {}).get("descriptor_suffix", "").strip()

    if style == "tags":
        prompt = _build_tags(scene, char_clauses, setting_clauses, style_suffix)
        neg_parts = [p for p in (bible.get("negative_defaults", ""), global_negative_prompt) if p]
        negative_prompt = ", ".join(neg_parts)
    else:
        prompt = _build_prose(scene, char_clauses, setting_clauses, style_suffix)
        negative_prompt = ""  # unsupported by prose-family models (cfg=1 / guidance=0)

    result = {
        "id": scene["id"],
        "anchor": scene.get("anchor", ""),
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "chunk_id": scene.get("chunk_id"),
        "characters_present": scene.get("characters_present", []),
        "settings_present": scene.get("settings_present", []),
        "orientation": scene.get("orientation") if scene.get("orientation") in ("portrait", "landscape", "square") else "square",
    }
    if seed is not None:
        result["seed"] = seed
    return result
