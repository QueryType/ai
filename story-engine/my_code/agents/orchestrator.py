"""OrchestratorAgent — entry point and execution loop.

Owns the beat iteration, delegates to sub-agents, manages retries and
human input. Handles all three execution modes (autonomous, interactive,
semi-interactive) via conditional logic.

See AGENT_DESIGN.md §1.1 and §4.
"""

from __future__ import annotations

import gc
import json
import logging
import re
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from strands.types.exceptions import MaxTokensReachedException

from my_code.agents.evaluator import create_evaluator, create_evaluator_single_pass
from my_code.agents.narrator import create_narrator
from my_code.agents.summariser import create_summariser
from my_code.tools.eval_tools import pop_last_emit
from my_code.tools.lore_tools import build_lore_block, get_character_card, scan_for_triggers
from my_code.models.data_models import (
    EvalResult,
    HumanInput,
    NarratorContext,
    ParsedScene,
)
from my_code.parser import parse_scene_file

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
_NARRATOR_RESUME_SUMMARY_WINDOW = 3
_NARRATOR_RESUME_SUMMARY_MAX_CHARS = 1200


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
# Run log
# ---------------------------------------------------------------------------

def _log_path(output_file: str) -> Path:
    """Derive the run log file path from the output file path, with a timestamp."""
    p = Path(output_file)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return p.parent / f"{p.stem}_{ts}.log"


def _attach_run_log(output_file: str) -> logging.FileHandler:
    """Add a FileHandler on the my_code package logger so only our control-flow
    logs go to the run log (excludes Strands SDK / httpx HTTP noise)."""
    lp = _log_path(output_file)
    lp.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(lp, mode="a", encoding="utf-8")
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logging.getLogger("my_code").addHandler(handler)
    return handler


def _detach_run_log(handler: logging.FileHandler) -> None:
    """Remove the file handler from the my_code logger and close it."""
    logging.getLogger("my_code").removeHandler(handler)
    handler.close()


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

    # --- Attach run log (appends to output/<stem>.log for the duration of this run) ---
    run_log_handler = _attach_run_log(meta.output_file)
    logger.info("Run log: %s", _log_path(meta.output_file))
    logger.info("Scene: %s | Mode: %s | Beats: %d", meta.title, mode, len(scene.beats))

    try:
        # --- Load checkpoint ---
        checkpoint = _load_checkpoint(meta.output_file)
        checkpoint_beats: dict[str, str] = checkpoint["beats"]
        prior_summary: str = checkpoint.get("prior_summary", "")

        if checkpoint_beats:
            logger.info("Resuming from checkpoint: %d/%d beats already done", len(checkpoint_beats), len(scene.beats))

        # --- Create sub-agents ---
        # Narrator is created once — it must persist across beats to maintain
        # its SummarizingConversationManager state (KV cache continuity on port 8080).
        # Evaluator and summariser are stateless (NullConversationManager) and are
        # recreated each beat so Strands SDK metric objects don't accumulate in RAM.
        narrator = create_narrator(scene)
        logger.info("Agents ready: narrator | evaluator | summariser (lore injection is pure-Python)")

        # --- Serialise characters once for lore injector ---
        characters_json = json.dumps([asdict(c) for c in scene.characters], ensure_ascii=False)

        resume_story_summary = ""
        resume_context_pending = False
        if checkpoint_beats:
            resume_story_summary = _build_resume_story_summary(prior_summary)
            resume_context_pending = bool(resume_story_summary)
            logger.info(
                "Resume context prepared from checkpoint summary (beats=%d chars=%d)",
                len(checkpoint_beats),
                len(resume_story_summary),
            )

        # --- Beat loop ---
        for beat in scene.beats:
            key = str(beat.index)

            # Skip already-completed beats
            if key in checkpoint_beats:
                continue

            logger.info("--- Beat %d/%d ---", beat.index, len(scene.beats))

            # Fresh stateless agents per beat — prevents Strands SDK metric
            # objects from accumulating across beats in long runs.
            # gc.collect() ensures the previous beat's agent objects are freed
            # before we allocate new ones (relevant on Apple Silicon unified memory).
            gc.collect()
            summariser = create_summariser()

            # 1. Lore injection (pure Python — no LLM call)
            lore_context = _call_lore_injector(
                beat.text, beat.index, characters_json, scene.world_info
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
                prior_story_summary=resume_story_summary if resume_context_pending else None,
            )

            # 3. Narrate + evaluate loop (with retries)
            prose, retry_count, last_narrator_in, beat_start_state = _narrate_and_evaluate(
                narrator, ctx, scene.writing_style, prior_summary
            )

            if retry_count >= MAX_RETRIES:
                logger.warning("Beat %d: max retries hit, using best attempt", beat.index)

            # 4. Human input (mode-dependent)
            action = "continue"
            if mode == "interactive" or (mode == "semi-interactive" and beat.has_pause):
                action, prose = _handle_human_input(
                    beat, scene, prose, narrator, ctx, prior_summary, beat_start_state
                )

            if action == "stop":
                # Save checkpoint before exiting so we can resume later
                _save_checkpoint(meta.output_file, checkpoint_beats, prior_summary)
                break
            elif action == "skip":
                logger.info("Beat %d: skipped by user", beat.index)
                continue

            if resume_context_pending:
                resume_context_pending = False

            # 5. Proactive narrator context management.
            # Uses token-based threshold + direct message deletion to avoid KV cache eviction.
            # SummarizingConversationManager.reduce_context() makes a separate LLM call that
            # sends a different prompt to port 8080, destroying all SWA checkpoints and forcing
            # full context re-processing on every subsequent beat (+80-100s each). Direct
            # deletion accepts a one-time cache miss only when actually approaching ctx=12288.
            _trim_narrator_context(narrator, last_narrator_in)

            # 6. Summarise beat for coherence tracking, then save checkpoint
            checkpoint_beats[key] = prose
            is_last_beat = beat.index == scene.beats[-1].index
            if not is_last_beat:
                logger.info("Beat %d/%d: → summariser", beat.index, len(scene.beats))
                beat_summary = _summarise_beat(summariser, prose, beat.index)
                logger.info("Beat %d/%d: ← summariser", beat.index, len(scene.beats))
                prior_summary += f"\n\n### Beat {beat.index} Summary\n{beat_summary}"
            _save_checkpoint(meta.output_file, checkpoint_beats, prior_summary)
            logger.info("Beat %d: saved (%d words)", beat.index, len(prose.split()))

        # --- Final output ---
        # Assemble beats in order from checkpoint
        completed_beats = [checkpoint_beats[str(b.index)] for b in scene.beats if str(b.index) in checkpoint_beats]
        output_path = _save_final_output(completed_beats, meta)
        _clear_checkpoint(meta.output_file)
        logger.info("Output written to: %s", output_path)
        return output_path
    finally:
        _detach_run_log(run_log_handler)


# ---------------------------------------------------------------------------
# Sub-agent call helpers
# ---------------------------------------------------------------------------

_NARRATOR_TRIM_TOKEN_THRESHOLD = 10500  # ~85% of ctx=12288; trim only when actually close

def _trim_narrator_context(narrator, last_input_tokens: int) -> None:
    """Trim narrator conversation by direct message deletion when approaching ctx=12288.

    IMPORTANT: Do NOT call SummarizingConversationManager.reduce_context() here.
    reduce_context() makes a hidden LLM API call to port 8080 with a different prompt
    structure (summarization request). Due to Gemma 4 SWA, this destroys ALL cached
    KV checkpoints and forces full context re-processing on every subsequent beat
    (+80-100s per beat). Direct deletion is instant and only breaks the cache ONCE,
    at the moment trim fires.

    Only fires when last_input_tokens exceeds the threshold — for short scenes this
    never triggers, preserving perfect KV cache continuity throughout.
    """
    if last_input_tokens < _NARRATOR_TRIM_TOKEN_THRESHOLD:
        return

    msg_count = len(narrator.messages)
    preserve = narrator.conversation_manager.preserve_recent_messages

    # Separate system messages (fixed prefix) from conversation turns
    system_msgs = [m for m in narrator.messages if _msg_role(m) == "system"]
    other_msgs  = [m for m in narrator.messages if _msg_role(m) != "system"]

    if len(other_msgs) <= preserve:
        return

    narrator.messages[:] = system_msgs + other_msgs[-preserve:]
    logger.info(
        "Narrator context trimmed: %d → %d messages (input_tokens=%d)",
        msg_count, len(narrator.messages), last_input_tokens,
    )


def _snapshot_narrator_state(narrator):
    """Capture narrator conversation length so rejected drafts can be rolled back."""
    return len(narrator.messages)


def _restore_narrator_state(narrator, snapshot) -> None:
    """Restore narrator conversation state after a rejected or skipped attempt."""
    del narrator.messages[snapshot:]


def _msg_role(msg) -> str:
    """Extract role from a Strands message regardless of whether it's a dict or object."""
    if isinstance(msg, dict):
        return msg.get("role", "")
    return getattr(msg, "role", "")


def _call_lore_injector(
    beat_text: str, beat_index: int, characters_json: str, world_info: str
) -> str:
    """Build lore context using direct Python tool calls — no LLM required.

    The three lore tools are pure Python (regex, dict lookup, string assembly).
    Bypassing the agent eliminates one full KV-cache eviction per beat.
    """
    logger.debug("Beat %d: lore injection (pure-Python)", beat_index)
    matched_names = json.loads(scan_for_triggers(beat_text, characters_json))
    cards = []
    for name in matched_names:
        card = get_character_card(name, characters_json)
        if not card.startswith("Character not found"):
            cards.append(card)
    return build_lore_block(json.dumps(cards))


def _call_narrator(agent, ctx: NarratorContext) -> tuple[str, int]:
    """Call the NarratorAgent to write prose for a beat."""
    parts = [f"Write prose for beat {ctx.beat_index}/{ctx.beat_total}.\n"]

    if ctx.prior_story_summary:
        parts.append(f"## Story So Far\n{ctx.prior_story_summary}\n")

    parts.append(f"## Beat Instruction\n{ctx.beat_instruction}\n")
    if ctx.lore_context:
        parts.append(f"## Lore Context\n{ctx.lore_context}\n")

    if ctx.author_note:
        parts.append(f"## Author Note (reminder)\n{ctx.author_note}\n")

    if ctx.redirect_instruction:
        parts.append(f"## Redirect from Human\n{ctx.redirect_instruction}\n")

    prompt = "\n".join(parts)
    logger.debug(
        "Beat %d/%d: narrator prompt chars=%d (resume=%d instruction=%d lore=%d author_note=%d redirect=%d)",
        ctx.beat_index,
        ctx.beat_total,
        len(prompt),
        len(ctx.prior_story_summary or ""),
        len(ctx.beat_instruction),
        len(ctx.lore_context),
        len(ctx.author_note or ""),
        len(ctx.redirect_instruction or ""),
    )
    # Snapshot cumulative usage before this call so we can log per-beat deltas.
    # agent.event_loop_metrics accumulates across the agent's lifetime; result.metrics
    # is the same object, so subtracting the pre-call snapshot gives per-call usage.
    prev = agent.event_loop_metrics.accumulated_usage
    prev_in = prev.get("inputTokens", 0)
    prev_out = prev.get("outputTokens", 0)

    result = agent(prompt)

    usage = result.metrics.accumulated_usage
    beat_in = usage.get("inputTokens", 0) - prev_in
    beat_out = usage.get("outputTokens", 0) - prev_out
    logger.info(
        "Beat %d/%d: narrator tokens in=%d out=%d stop=%s (history=%d msgs)",
        ctx.beat_index,
        ctx.beat_total,
        beat_in,
        beat_out,
        result.stop_reason,
        len(agent.messages),
    )
    return str(result), beat_in


_EVALUATOR_PRIOR_SUMMARY_WINDOW = 10  # Keep only the last N beat summaries
_EVALUATOR_PRIOR_SUMMARY_MAX_CHARS = 4500  # Secondary hard cap after window trim
_EVALUATOR_SINGLE_PASS_PRIOR_SUMMARY_MAX_CHARS = 1800
_EVALUATOR_SINGLE_PASS_PROSE_MAX_CHARS = 4200
_SUMMARY_MAX_BULLETS = 5
_SUMMARY_MAX_BULLET_CHARS = 220
_SUMMARY_MAX_TOTAL_CHARS = 1000


def _build_resume_story_summary(prior_summary: str) -> str:
    """Build a compact narrator seed for the first beat after checkpoint resume."""
    trimmed = _trim_prior_summary(prior_summary, window=_NARRATOR_RESUME_SUMMARY_WINDOW)
    return _cap_prior_summary_chars(trimmed, max_chars=_NARRATOR_RESUME_SUMMARY_MAX_CHARS)


def _trim_prior_summary(prior_summary: str, window: int = _EVALUATOR_PRIOR_SUMMARY_WINDOW) -> str:
    """Return the last `window` beat summaries from the accumulated prior_summary string.

    Each summary block starts with '### Beat N Summary'. Older summaries are dropped
    to keep the evaluator prompt within the 9B model's context window.
    """
    if not prior_summary:
        return prior_summary
    # Split on section headers, keeping the delimiter
    parts = re.split(r'(?=### Beat \d+ Summary)', prior_summary.strip())
    parts = [p for p in parts if p.strip()]
    if len(parts) <= window:
        return prior_summary
    return "\n\n" + "\n\n".join(parts[-window:])


def _cap_prior_summary_chars(
    prior_summary: str, max_chars: int = _EVALUATOR_PRIOR_SUMMARY_MAX_CHARS
) -> str:
    """Apply a hard character budget to evaluator prior-summary context.

    Keeps the most recent beat-summary blocks first, then truncates to tail as fallback.
    """
    if not prior_summary or len(prior_summary) <= max_chars:
        return prior_summary

    parts = re.split(r'(?=### Beat \d+ Summary)', prior_summary.strip())
    parts = [p for p in parts if p.strip()]
    kept: list[str] = []
    total = 0
    for part in reversed(parts):
        add = len(part) + (2 if kept else 0)
        if total + add > max_chars:
            break
        kept.append(part)
        total += add

    if kept:
        return "\n\n" + "\n\n".join(reversed(kept))

    # Fallback when a single newest block is already above budget.
    return prior_summary[-max_chars:]


def _normalize_summary_for_budget(summary_text: str) -> str:
    """Normalize and cap BeatSummariser output to a stable size budget."""
    lines = [line.strip() for line in summary_text.splitlines() if line.strip()]
    if not lines:
        return summary_text[:_SUMMARY_MAX_TOTAL_CHARS].strip()

    bullets: list[str] = []
    for line in lines:
        text = re.sub(r'^([-*•]\s+|\d+[\).]\s+)', '', line).strip()
        if not text:
            continue
        if len(text) > _SUMMARY_MAX_BULLET_CHARS:
            text = text[: _SUMMARY_MAX_BULLET_CHARS - 3].rstrip() + "..."
        bullets.append(f"- {text}")
        if len(bullets) >= _SUMMARY_MAX_BULLETS:
            break

    normalized = "\n".join(bullets).strip()
    if len(normalized) <= _SUMMARY_MAX_TOTAL_CHARS:
        return normalized
    return normalized[: _SUMMARY_MAX_TOTAL_CHARS - 3].rstrip() + "..."


def _truncate_middle(text: str, max_chars: int) -> str:
    """Truncate long text by preserving both the beginning and end segments."""
    if not text or len(text) <= max_chars:
        return text
    if max_chars <= 5:
        return text[:max_chars]
    head = int(max_chars * 0.65)
    tail = max_chars - head - 5
    return f"{text[:head].rstrip()}\n...\n{text[-tail:].lstrip()}"


def _call_evaluator_single_pass(
    beat_instruction: str, prose: str, writing_style: str, prior_summary: str
) -> EvalResult | None:
    """Fallback evaluator path with no tool-calling to avoid recursive tool loops."""
    trimmed_summary = _trim_prior_summary(prior_summary)
    capped_summary = _cap_prior_summary_chars(
        trimmed_summary,
        max_chars=_EVALUATOR_SINGLE_PASS_PRIOR_SUMMARY_MAX_CHARS,
    )
    compact_prose = _truncate_middle(prose, _EVALUATOR_SINGLE_PASS_PROSE_MAX_CHARS)
    prompt = (
        "Evaluate this beat's prose and return strict JSON only.\n\n"
        f"## Beat Instruction\n{beat_instruction}\n\n"
        f"## Prose Output\n{compact_prose}\n\n"
        f"## Writing Style\n{writing_style}\n\n"
        f"## Prior Beats Summary\n{capped_summary if capped_summary else '(first beat — no prior context)'}"
    )

    logger.warning(
        "EVALUATOR RECOVERY: switching to single-pass mode (prompt chars=%d, prose chars=%d)",
        len(prompt),
        len(compact_prose),
    )

    try:
        result = create_evaluator_single_pass()(prompt)
        raw = str(result)
    except Exception as exc:
        logger.warning(
            "EVALUATOR RECOVERY FAILED: %s in single-pass mode",
            type(exc).__name__,
        )
        return None

    try:
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
                evaluated=True,
                fallback_reason=None,
                issues=data.get("issues", []),
            )
    except (json.JSONDecodeError, KeyError):
        logger.warning("EVALUATOR RECOVERY FAILED: single-pass JSON parse failed")

    return None


def _call_evaluator(
    agent, beat_instruction: str, prose: str, writing_style: str, prior_summary: str
) -> EvalResult:
    """Call the EvaluatorAgent and parse its verdict."""
    trimmed_summary = _trim_prior_summary(prior_summary)
    capped_summary = _cap_prior_summary_chars(trimmed_summary)
    prompt = (
        f"Evaluate this beat's prose.\n\n"
        f"## Beat Instruction\n{beat_instruction}\n\n"
        f"## Prose Output\n{prose}\n\n"
        f"## Writing Style\n{writing_style}\n\n"
        f"## Prior Beats Summary\n{capped_summary if capped_summary else '(first beat — no prior context)'}"
    )
    logger.debug(
        "Evaluator prompt chars=%d (instruction=%d prose=%d style=%d prior_raw=%d prior_window=%d prior_capped=%d)",
        len(prompt),
        len(beat_instruction),
        len(prose),
        len(writing_style),
        len(prior_summary),
        len(trimmed_summary),
        len(capped_summary),
    )
    try:
        result = agent(prompt)
        raw = str(result)
        usage = result.metrics.accumulated_usage
        logger.info(
            "Evaluator tokens in=%d out=%d total=%d stop=%s",
            usage.get("inputTokens", 0),
            usage.get("outputTokens", 0),
            usage.get("totalTokens", 0),
            result.stop_reason,
        )

        # Prefer the side-channel JSON from emit_eval_result over str(result).
        # Local models often wrap the tool output in prose ("I have evaluated...")
        # rather than echoing raw JSON, so str(result) parsing fails for them.
        emitted = pop_last_emit()
        if emitted:
            try:
                data = json.loads(emitted)
                logger.debug("Evaluator: using emit_eval_result side-channel JSON")
                return EvalResult(
                    result=data.get("result", "pass"),
                    score=data.get("score", 1.0),
                    reason=data.get("reason", ""),
                    beat_coverage=data.get("beat_coverage", True),
                    style_compliant=data.get("style_compliant", True),
                    coherent=data.get("coherent", True),
                    evaluated=True,
                    fallback_reason=None,
                    issues=data.get("issues", []),
                )
            except (json.JSONDecodeError, KeyError):
                logger.warning("Evaluator: side-channel JSON parse failed, falling back to str(result)")

        if result.stop_reason == "max_tokens":
            logger.warning(
                "EVALUATOR FALLBACK: stop_reason=max_tokens — context limit hit, "
                "verdict will be defaulted to pass. "
                "Prompt chars=%d; consider reducing ctx or trimming input.",
                len(prompt),
            )
            recovered = _call_evaluator_single_pass(
                beat_instruction,
                prose,
                writing_style,
                prior_summary,
            )
            if recovered is not None:
                return recovered
            return EvalResult(
                result="pass", score=1.0, reason="Evaluator fallback: max_tokens",
                beat_coverage=True, style_compliant=True, coherent=True,
                evaluated=False, fallback_reason="max_tokens",
            )
    except Exception as exc:
        logger.warning(
            "EVALUATOR FALLBACK: %s raised mid-call — defaulting to pass",
            type(exc).__name__,
        )
        recovered = _call_evaluator_single_pass(
            beat_instruction,
            prose,
            writing_style,
            prior_summary,
        )
        if recovered is not None:
            return recovered
        return EvalResult(
            result="pass", score=1.0, reason=f"Evaluator fallback: {type(exc).__name__}",
            beat_coverage=True, style_compliant=True, coherent=True,
            evaluated=False, fallback_reason=type(exc).__name__,
        )

    # Try to extract JSON from the response
    try:
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
                evaluated=True,
                fallback_reason=None,
                issues=data.get("issues", []),
            )
    except (json.JSONDecodeError, KeyError):
        logger.warning("EVALUATOR FALLBACK: JSON parse failed — defaulting to pass. raw=%r", raw[:200])
        recovered = _call_evaluator_single_pass(
            beat_instruction,
            prose,
            writing_style,
            prior_summary,
        )
        if recovered is not None:
            return recovered

    # Default to pass if parsing fails
    return EvalResult(
        result="pass", score=1.0, reason="Evaluator fallback: JSON parse failed",
        beat_coverage=True, style_compliant=True, coherent=True,
        evaluated=False, fallback_reason="json_parse_failed",
    )


# ---------------------------------------------------------------------------
# Narrate + evaluate loop
# ---------------------------------------------------------------------------

def _narrate_and_evaluate(
    narrator, ctx: NarratorContext, writing_style: str, prior_summary: str
) -> tuple[str, int, int, list]:
    """Run the narrator → evaluator loop with retries.

    Returns (prose, retry_count, last_narrator_input_tokens, beat_start_state).
    """
    retry_count = 0
    beat_start_state = _snapshot_narrator_state(narrator)
    logger.info("Beat %d/%d: → narrator (attempt 1)", ctx.beat_index, ctx.beat_total)
    prose, last_narrator_in = _call_narrator(narrator, ctx)
    logger.info("Beat %d/%d: ← narrator (%d words)", ctx.beat_index, ctx.beat_total, len(prose.split()))

    while retry_count < MAX_RETRIES:
        logger.info("Beat %d/%d: → evaluator", ctx.beat_index, ctx.beat_total)
        gc.collect()
        evaluator = create_evaluator()
        eval_result = _call_evaluator(evaluator, ctx.beat_instruction, prose, writing_style, prior_summary)
        if eval_result.evaluated:
            logger.info(
                "Beat %d/%d: ← evaluator %s score=%.2f | %s",
                ctx.beat_index, ctx.beat_total,
                eval_result.result, eval_result.score, eval_result.reason,
            )
        else:
            logger.warning(
                "Beat %d/%d: ← evaluator fallback accepted output (%s)",
                ctx.beat_index,
                ctx.beat_total,
                eval_result.fallback_reason,
            )

        if eval_result.result == "pass":
            break

        retry_count += 1
        if retry_count < MAX_RETRIES:
            _restore_narrator_state(narrator, beat_start_state)
            logger.info(
                "Beat %d/%d: → narrator (retry %d/%d)",
                ctx.beat_index, ctx.beat_total, retry_count + 1, MAX_RETRIES,
            )
            # Append evaluator feedback to context for the retry
            ctx.redirect_instruction = f"[Evaluator feedback — please address]: {eval_result.reason}"
            prose, last_narrator_in = _call_narrator(narrator, ctx)
            logger.info(
                "Beat %d/%d: ← narrator (%d words)",
                ctx.beat_index, ctx.beat_total, len(prose.split()),
            )

    return prose, retry_count, last_narrator_in, beat_start_state


# ---------------------------------------------------------------------------
# Human input handling
# ---------------------------------------------------------------------------

def _handle_human_input(
    beat, scene, prose, narrator, ctx, prior_summary, beat_start_state
) -> tuple[str, str]:
    """Handle human input pause. Returns (action, final_prose)."""
    while True:
        human = _prompt_human(beat.index, len(scene.beats), prose)

        logger.info("Beat %d/%d: human action=%s", beat.index, len(scene.beats), human.action)

        if human.action == "continue":
            return "continue", prose

        elif human.action == "stop":
            _restore_narrator_state(narrator, beat_start_state)
            return "stop", prose

        elif human.action == "skip":
            _restore_narrator_state(narrator, beat_start_state)
            return "skip", prose

        elif human.action == "retry":
            _restore_narrator_state(narrator, beat_start_state)
            ctx.redirect_instruction = None
            logger.info("Beat %d/%d: → narrator (human retry)", beat.index, len(scene.beats))
            prose, _ = _call_narrator(narrator, ctx)
            logger.info("Beat %d/%d: ← narrator (%d words)", beat.index, len(scene.beats), len(prose.split()))
            logger.info("Beat %d/%d: → evaluator (human retry)", beat.index, len(scene.beats))
            gc.collect()
            eval_result = _call_evaluator(create_evaluator(), ctx.beat_instruction, prose, scene.writing_style, prior_summary)
            if eval_result.evaluated:
                logger.info("Beat %d/%d: ← evaluator %s score=%.2f", beat.index, len(scene.beats), eval_result.result, eval_result.score)
            else:
                logger.warning("Beat %d/%d: ← evaluator fallback accepted output (%s)", beat.index, len(scene.beats), eval_result.fallback_reason)
            continue  # Show to human again

        elif human.action == "redirect":
            _restore_narrator_state(narrator, beat_start_state)
            ctx.redirect_instruction = human.text
            logger.info("Beat %d/%d: → narrator (human redirect)", beat.index, len(scene.beats))
            prose, _ = _call_narrator(narrator, ctx)
            logger.info("Beat %d/%d: ← narrator (%d words)", beat.index, len(scene.beats), len(prose.split()))
            logger.info("Beat %d/%d: → evaluator (human redirect)", beat.index, len(scene.beats))
            gc.collect()
            eval_result = _call_evaluator(create_evaluator(), ctx.beat_instruction, prose, scene.writing_style, prior_summary)
            if eval_result.evaluated:
                logger.info("Beat %d/%d: ← evaluator %s score=%.2f", beat.index, len(scene.beats), eval_result.result, eval_result.score)
            else:
                logger.warning("Beat %d/%d: ← evaluator fallback accepted output (%s)", beat.index, len(scene.beats), eval_result.fallback_reason)
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

def _summarise_beat(agent, prose: str, beat_index: int) -> str:
    """Call the BeatSummariserAgent to produce bullet-point summary of a beat.
    
    On MaxTokensReachedException, progressively truncate prose and retry.
    """
    max_retries = 5
    truncation_factor = 1.0
    
    for attempt in range(max_retries):
        try:
            # Apply truncation if this is a retry after overflow
            current_prose = prose
            if attempt > 0:
                truncate_chars = int(len(prose) * truncation_factor)
                # Keep the end of the prose (most recent/relevant narrative)
                current_prose = prose[-truncate_chars:] if truncate_chars > 0 else prose[:100]
                logger.warning(
                    "Beat %d: summariser retry attempt %d with truncation (%.1f%% of original %d chars)",
                    beat_index,
                    attempt,
                    truncation_factor * 100,
                    len(prose),
                )
            
            prompt = f"Summarise beat {beat_index}:\n\n{current_prose}"
            logger.debug(
                "Beat %d: summariser prompt chars=%d (prose=%d)",
                beat_index,
                len(prompt),
                len(current_prose),
            )
            result = agent(prompt)
            raw_summary = str(result).strip()
            capped_summary = _normalize_summary_for_budget(raw_summary)
            if capped_summary != raw_summary:
                logger.debug(
                    "Beat %d: summary normalized/capped raw_chars=%d capped_chars=%d",
                    beat_index,
                    len(raw_summary),
                    len(capped_summary),
                )
            return capped_summary
            
        except MaxTokensReachedException as e:
            if attempt == max_retries - 1:
                logger.error(
                    "Beat %d: summariser failed after %d truncation attempts",
                    beat_index,
                    attempt + 1,
                )
                raise
            # Reduce prose to 70% of previous attempt (exponential backoff)
            truncation_factor *= 0.7
            logger.info(
                "Beat %d: MaxTokensReachedException caught, retrying with reduced prose...",
                beat_index,
            )
