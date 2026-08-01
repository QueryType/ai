"""
phases.py — the three phases of the self-improving loop.

  generate(task, prompt, client, profile) → str
  critique(task, prompt, response, client, profile) → dict
  refine(task, prompt, response, critique_result, client, profile) → str
"""

import json
import re
from pathlib import Path

import openai

from config import cfg
from tools import get_system_date

_PROMPTS = Path(__file__).parent / "prompts"

_GEN_SYSTEM  = (_PROMPTS / "generator_system.md").read_text().strip()
_CRIT_SYSTEM = (_PROMPTS / "critic_system.md").read_text().strip()
_REF_SYSTEM  = (_PROMPTS / "refiner_system.md").read_text().strip()


def _build_critic_system() -> str:
    """Inject rubric dimensions from config into the critic system prompt."""
    dim_lines = []
    score_keys = []
    for d in cfg.rubric:
        dim_lines.append(f"- **{d['name']}**: {d['description']}")
        score_keys.append(f'    "{d["name"]}": <0-10>')

    rubric_block  = "\n".join(dim_lines)
    score_key_str = ",\n".join(score_keys)
    return (
        _CRIT_SYSTEM
        .replace("{{RUBRIC_DIMENSIONS}}", rubric_block)
        .replace("{{SCORE_KEYS}}", score_key_str)
    )


_CRITIC_SYSTEM_BUILT = _build_critic_system()


def _client(profile: dict) -> openai.OpenAI:
    return openai.OpenAI(
        base_url=profile["base_url"],
        api_key="local",
        timeout=120,
    )


def _call(client: openai.OpenAI, profile: dict, system: str, user: str) -> str:
    resp = client.chat.completions.create(
        model=profile["model"],
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
        temperature=profile["temperature"],
        max_tokens=profile["max_tokens"],
        # Some local models (Qwen3.6, gemma-4) default to emitting a
        # reasoning_content block before the final answer, which can burn
        # the whole max_tokens budget and leave content empty. Disable it
        # so responses are direct and token budgets are predictable.
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )
    return (resp.choices[0].message.content or "").strip()


# ── Phase 1: Generate ─────────────────────────────────────────────────────────

def generate(task: str, prompt: str, profile: dict, search_context: str = "") -> str:
    """Run the generator model. Returns the raw response text."""
    client = _client(profile)
    date_block = f"## Current date\n{get_system_date()}\n\n"
    ctx_block = f"## Web context\n{search_context}\n\n" if search_context else ""
    user = f"{date_block}{ctx_block}## Prompt\n{prompt}\n\n## Task\n{task}"
    return _call(client, profile, _GEN_SYSTEM, user)


# ── Phase 2: Critique ─────────────────────────────────────────────────────────

def critique(task: str, prompt: str, response: str, profile: dict) -> dict:
    """
    Score the response against the rubric.
    Returns a dict: {scores: {dim: int}, total: float, reasoning: str, improvements: [str]}
    Falls back to a penalty dict on parse failure.
    """
    client = _client(profile)
    user = (
        f"## Current date\n{get_system_date()}\n\n"
        f"## Task\n{task}\n\n"
        f"## Prompt used\n{prompt}\n\n"
        f"## Model response\n{response}"
    )
    raw = _call(client, profile, _CRITIC_SYSTEM_BUILT, user)
    return _parse_critique(raw)


def _parse_critique(raw: str) -> dict:
    # Strip markdown fences if the model wrapped in them anyway
    raw = re.sub(r"^```[a-z]*\n?", "", raw.strip())
    raw = re.sub(r"\n?```$", "", raw.strip())

    try:
        data = json.loads(raw)
        # Validate expected keys are present
        assert "scores" in data and "total" in data
        # Recompute total from scores in case model got it wrong
        scores = {k: int(v) for k, v in data["scores"].items()}
        total  = round(sum(scores.values()) / len(scores), 1) if scores else 0.0
        return {
            "scores":       scores,
            "total":        total,
            "reasoning":    data.get("reasoning", ""),
            "improvements": data.get("improvements", []),
            "_raw":         raw,
        }
    except Exception:
        # Fallback: score of 0 forces refinement, raw text preserved for debug
        dims = {d["name"]: 0 for d in cfg.rubric}
        return {
            "scores":       dims,
            "total":        0.0,
            "reasoning":    f"[Parse failed — raw output below]\n{raw}",
            "improvements": ["Fix: critic did not return valid JSON"],
            "_raw":         raw,
        }


# ── Phase 3: Refine ───────────────────────────────────────────────────────────

def refine(task: str, prompt: str, response: str, critique_result: dict, profile: dict) -> str:
    """
    Rewrite the prompt based on critique feedback.
    Returns the improved prompt text.
    """
    client = _client(profile)

    score_lines = "\n".join(
        f"  {k}: {v}/10" for k, v in critique_result["scores"].items()
    )
    improvements = "\n".join(f"- {imp}" for imp in critique_result["improvements"])

    user = (
        f"## Task\n{task}\n\n"
        f"## Current prompt\n{prompt}\n\n"
        f"## Response it produced\n{response}\n\n"
        f"## Critic scores\n{score_lines}\n"
        f"  total: {critique_result['total']}/10\n\n"
        f"## Critic reasoning\n{critique_result['reasoning']}\n\n"
        f"## Specific improvements needed\n{improvements}\n\n"
        f"Write the improved prompt now:"
    )
    return _call(client, profile, _REF_SYSTEM, user)
