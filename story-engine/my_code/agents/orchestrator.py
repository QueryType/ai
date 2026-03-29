"""OrchestratorAgent — entry point and execution loop.

Owns the beat iteration, delegates to sub-agents, manages retries and
human input. Handles all three execution modes (autonomous, interactive,
semi-interactive) via conditional logic.

See AGENT_DESIGN.md §1.1 and §4.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path

from my_code.agents.evaluator import create_evaluator
from my_code.agents.lore_injector import create_lore_injector
from my_code.agents.narrator import create_narrator
from my_code.models.data_models import (
    EvalResult,
    HumanInput,
    NarratorContext,
    ParsedScene,
)
from my_code.parser import parse_scene_file

logger = logging.getLogger(__name__)

MAX_RETRIES = 3


# ---------------------------------------------------------------------------
# Checkpoint persistence
# ---------------------------------------------------------------------------

def _checkpoint_path(output_file: str) -> Path:
    """Derive the checkpoint file path from the output file path."""
    p = Path(output_file)
    return p.parent / f".{p.stem}.checkpoint.json"


def _load_checkpoint(output_file: str) -> dict:
    """Load existing checkpoint if present. Returns dict with beats and summary."""
    cp = _checkpoint_path(output_file)
    if cp.exists():
        try:
            data = json.loads(cp.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "beats" in data:
                return data
        except (json.JSONDecodeError, KeyError):
            logger.warning("Corrupt checkpoint file, starting fresh")
    return {"beats": {}, "prior_summary": ""}


def _save_checkpoint(output_file: str, completed_beats: dict[str, str], prior_summary: str):
    """Write checkpoint after each beat. beats is {beat_index_str: prose}."""
    cp = _checkpoint_path(output_file)
    cp.parent.mkdir(parents=True, exist_ok=True)
    data = {"beats": completed_beats, "prior_summary": prior_summary}
    cp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _clear_checkpoint(output_file: str):
    """Remove checkpoint file after successful completion."""
    cp = _checkpoint_path(output_file)
    if cp.exists():
        cp.unlink()
        logger.info("Checkpoint cleared: %s", cp)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_scene(file_path: str) -> str:
    """Run the full story engine pipeline for a scene file.

    Supports resume: if a previous run was interrupted, completed beats
    are loaded from a checkpoint file and only remaining beats are generated.

    Args:
        file_path: Path to the scene .md file.

    Returns:
        Path to the written output file.
    """
    # --- Parse ---
    scene = parse_scene_file(file_path)
    meta = scene.meta
    mode = meta.mode
    logger.info("Scene: %s | Mode: %s | Beats: %d", meta.title, mode, len(scene.beats))

    # --- Load checkpoint ---
    checkpoint = _load_checkpoint(meta.output_file)
    checkpoint_beats: dict[str, str] = checkpoint["beats"]
    prior_summary: str = checkpoint.get("prior_summary", "")

    if checkpoint_beats:
        logger.info("Resuming from checkpoint: %d/%d beats already done", len(checkpoint_beats), len(scene.beats))

    # --- Create sub-agents ---
    lore_injector = create_lore_injector()
    narrator = create_narrator(scene)
    evaluator = create_evaluator()

    # --- Serialise characters once for lore injector ---
    characters_json = json.dumps([asdict(c) for c in scene.characters], ensure_ascii=False)

    # --- Replay completed beats into narrator conversation for context ---
    if checkpoint_beats:
        for beat in scene.beats:
            key = str(beat.index)
            if key in checkpoint_beats:
                # Feed the beat instruction + prose as a conversation turn
                # so the narrator has context continuity
                narrator(
                    f"[Previously written — beat {beat.index}/{len(scene.beats)}]\n"
                    f"Instruction: {beat.text}\n\n"
                    f"Output:\n{checkpoint_beats[key]}"
                )
                logger.info("Beat %d: restored from checkpoint", beat.index)

    # --- Beat loop ---
    for beat in scene.beats:
        key = str(beat.index)

        # Skip already-completed beats
        if key in checkpoint_beats:
            continue

        logger.info("--- Beat %d/%d ---", beat.index, len(scene.beats))

        # 1. Lore injection
        lore_context = _call_lore_injector(
            lore_injector, beat.text, beat.index, characters_json, scene.world_info
        )

        # 2. Build narrator context
        author_note_text = None
        if scene.author_note and beat.index > 0 and beat.index % scene.author_note.depth == 0:
            author_note_text = scene.author_note.content

        ctx = NarratorContext(
            beat_instruction=beat.text,
            lore_context=lore_context,
            beat_index=beat.index,
            beat_total=len(scene.beats),
            author_note=author_note_text,
        )

        # 3. Narrate + evaluate loop (with retries)
        prose, retry_count = _narrate_and_evaluate(
            narrator, evaluator, ctx, scene.writing_style, prior_summary
        )

        if retry_count >= MAX_RETRIES:
            logger.warning("Beat %d: max retries hit, using best attempt", beat.index)

        # 4. Human input (mode-dependent)
        action = "continue"
        if mode == "interactive" or (mode == "semi-interactive" and beat.has_pause):
            action, prose = _handle_human_input(
                beat, scene, prose, narrator, evaluator, ctx, prior_summary, checkpoint_beats
            )

        if action == "stop":
            # Save checkpoint before exiting so we can resume later
            _save_checkpoint(meta.output_file, checkpoint_beats, prior_summary)
            break
        elif action == "skip":
            logger.info("Beat %d: skipped by user", beat.index)
            continue

        # 5. Save beat to checkpoint immediately
        checkpoint_beats[key] = prose
        prior_summary += f"\nBeat {beat.index}: {_one_line_summary(prose)}"
        _save_checkpoint(meta.output_file, checkpoint_beats, prior_summary)
        logger.info("Beat %d: saved (%d words)", beat.index, len(prose.split()))

    # --- Final output ---
    # Assemble beats in order from checkpoint
    completed_beats = [checkpoint_beats[str(b.index)] for b in scene.beats if str(b.index) in checkpoint_beats]
    output_path = _save_final_output(completed_beats, meta)
    _clear_checkpoint(meta.output_file)
    logger.info("Output written to: %s", output_path)
    return output_path


# ---------------------------------------------------------------------------
# Sub-agent call helpers
# ---------------------------------------------------------------------------

def _call_lore_injector(
    agent, beat_text: str, beat_index: int, characters_json: str, world_info: str
) -> str:
    """Call the LoreInjectorAgent to build lore context for a beat."""
    prompt = (
        f"Build lore context for this beat.\n\n"
        f"Beat text: {beat_text}\n\n"
        f"Beat index: {beat_index}\n\n"
        f"Characters: {characters_json}\n\n"
        f"World info: {world_info}"
    )
    result = agent(prompt)
    return str(result)


def _call_narrator(agent, ctx: NarratorContext) -> str:
    """Call the NarratorAgent to write prose for a beat."""
    parts = [f"Write prose for beat {ctx.beat_index}/{ctx.beat_total}.\n"]
    parts.append(f"## Beat Instruction\n{ctx.beat_instruction}\n")
    parts.append(f"## Lore Context\n{ctx.lore_context}\n")

    if ctx.author_note:
        parts.append(f"## Author Note (reminder)\n{ctx.author_note}\n")

    if ctx.redirect_instruction:
        parts.append(f"## Redirect from Human\n{ctx.redirect_instruction}\n")

    result = agent("\n".join(parts))
    return str(result)


def _call_evaluator(
    agent, beat_instruction: str, prose: str, writing_style: str, prior_summary: str
) -> EvalResult:
    """Call the EvaluatorAgent and parse its verdict."""
    prompt = (
        f"Evaluate this beat's prose.\n\n"
        f"## Beat Instruction\n{beat_instruction}\n\n"
        f"## Prose Output\n{prose}\n\n"
        f"## Writing Style\n{writing_style}\n\n"
        f"## Prior Beats Summary\n{prior_summary if prior_summary else '(first beat — no prior context)'}"
    )
    result = agent(prompt)
    raw = str(result)

    # Try to extract JSON from the response
    try:
        # Find JSON in the response
        json_start = raw.find("{")
        json_end = raw.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            data = json.loads(raw[json_start:json_end])
            return EvalResult(
                result=data.get("result", "pass"),
                score=data.get("score", 1.0),
                reason=data.get("reason", ""),
                beat_coverage=data.get("beat_coverage", True),
                style_compliant=data.get("style_compliant", True),
                coherent=data.get("coherent", True),
                issues=data.get("issues", []),
            )
    except (json.JSONDecodeError, KeyError):
        logger.warning("Could not parse evaluator response, defaulting to pass")

    # Default to pass if parsing fails
    return EvalResult(
        result="pass", score=1.0, reason="Evaluator parse fallback",
        beat_coverage=True, style_compliant=True, coherent=True,
    )


# ---------------------------------------------------------------------------
# Narrate + evaluate loop
# ---------------------------------------------------------------------------

def _narrate_and_evaluate(
    narrator, evaluator, ctx: NarratorContext, writing_style: str, prior_summary: str
) -> tuple[str, int]:
    """Run the narrator → evaluator loop with retries. Returns (prose, retry_count)."""
    retry_count = 0
    prose = _call_narrator(narrator, ctx)

    while retry_count < MAX_RETRIES:
        eval_result = _call_evaluator(evaluator, ctx.beat_instruction, prose, writing_style, prior_summary)
        logger.info(
            "Eval: %s (score=%.2f) %s",
            eval_result.result, eval_result.score, eval_result.reason,
        )

        if eval_result.result == "pass":
            break

        retry_count += 1
        if retry_count < MAX_RETRIES:
            logger.info("Retrying beat (attempt %d/%d): %s", retry_count + 1, MAX_RETRIES, eval_result.reason)
            # Append evaluator feedback to context for the retry
            ctx.redirect_instruction = f"[Evaluator feedback — please address]: {eval_result.reason}"
            prose = _call_narrator(narrator, ctx)

    return prose, retry_count


# ---------------------------------------------------------------------------
# Human input handling
# ---------------------------------------------------------------------------

def _handle_human_input(
    beat, scene, prose, narrator, evaluator, ctx, prior_summary, completed_beats
) -> tuple[str, str]:
    """Handle human input pause. Returns (action, final_prose)."""
    while True:
        human = _prompt_human(beat.index, len(scene.beats), prose)

        if human.action == "continue":
            return "continue", prose

        elif human.action == "stop":
            return "stop", prose

        elif human.action == "skip":
            return "skip", prose

        elif human.action == "retry":
            ctx.redirect_instruction = None
            prose = _call_narrator(narrator, ctx)
            # Re-evaluate
            eval_result = _call_evaluator(evaluator, ctx.beat_instruction, prose, scene.writing_style, prior_summary)
            logger.info("Retry eval: %s (score=%.2f)", eval_result.result, eval_result.score)
            continue  # Show to human again

        elif human.action == "redirect":
            ctx.redirect_instruction = human.text
            prose = _call_narrator(narrator, ctx)
            eval_result = _call_evaluator(evaluator, ctx.beat_instruction, prose, scene.writing_style, prior_summary)
            logger.info("Redirect eval: %s (score=%.2f)", eval_result.result, eval_result.score)
            continue  # Show to human again

    return "continue", prose


def _prompt_human(beat_index: int, beat_total: int, prose: str) -> HumanInput:
    """Display prose and get human input."""
    print(f"\n{'='*60}")
    print(f"  Beat {beat_index}/{beat_total} complete")
    print(f"{'='*60}\n")
    print(prose)
    print(f"\n{'─'*60}")
    print("Commands: Enter=continue | /skip | /stop | /retry | free text=redirect")

    try:
        user_input = input("> ").strip()
    except EOFError:
        logger.info("No terminal attached — auto-continuing")
        return HumanInput(action="continue")

    if not user_input:
        return HumanInput(action="continue")
    elif user_input == "/skip":
        return HumanInput(action="skip")
    elif user_input == "/stop":
        return HumanInput(action="stop")
    elif user_input == "/retry":
        return HumanInput(action="retry")
    else:
        return HumanInput(action="redirect", text=user_input)


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def _save_final_output(completed_beats: list[str], meta) -> str:
    """Write the final assembled output file."""
    output_format = meta.output_format
    title = meta.title
    output_file = meta.output_file

    parts: list[str] = []

    if output_format == "adventure":
        parts.append(f"# {title}\n")
        for i, prose in enumerate(completed_beats, 1):
            parts.append(f"## Beat {i}\n\n{prose}\n")
    elif output_format == "script":
        parts.append(f"# {title}\n")
        for i, prose in enumerate(completed_beats, 1):
            parts.append(f"---\n**BEAT {i}**\n\n{prose}\n")
    else:
        parts.append(f"# {title}\n")
        for prose in completed_beats:
            parts.append(f"{prose}\n")

    content = "\n".join(parts)

    path = Path(output_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

    return str(path)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _one_line_summary(prose: str) -> str:
    """Extract a one-line summary from prose (first sentence, max 100 chars)."""
    # Take first sentence
    for end in (".", "!", "?"):
        idx = prose.find(end)
        if 0 < idx < 150:
            return prose[: idx + 1]
    # Fallback: first 100 chars
    return prose[:100].rsplit(" ", 1)[0] + "..."
