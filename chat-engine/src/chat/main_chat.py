"""CLI entry point for chat-engine Phase 1.

Usage:
    python -m src.chat.main_chat examples/ashenveil_chat1.md
    python -m src.chat.main_chat path/to/any_chat.md
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from src.chat.chat_logger import ChatLogger
from src.chat.gm_agent import GMAgent
from src.chat.history_summarizer import HistorySummarizer, format_history_with_summary
from src.chat.models.provider import context_limit, history_window_override, model_label
from src.chat.orchestrator import ChatOrchestrator
from src.chat.orchestrator_agent import OrchestratorAgent
from src.chat.parser import CharacterCard, ParsedChat, parse_chat_file
from src.chat.planner import ChatPlanner


# ---------------------------------------------------------------------------
# Display constants
# ---------------------------------------------------------------------------

_DIV  = "─" * 54
_HELP = """\
  Enter            continue (GM picks next speaker)
  [as Name] text   speak as that character
  [director] text  hidden note to GM for next turn only
  /next Name       force who speaks next (GM generates)
  /pause           toggle pause-every-turn mode
  /status          show turn count and speaking stats
  /stop            end session and save outputs
  /help            show this message"""


# ---------------------------------------------------------------------------
# ChatSession
# ---------------------------------------------------------------------------

class ChatSession:
    """Owns all runtime state for one chat session."""

    def __init__(self, chat: ParsedChat, input_path: str):
        self.chat        = chat
        self.config      = chat.config
        self.input_path  = input_path

        # Env var overrides .md file value — lets you tune for local vs remote
        # without editing the scenario file.
        hw_override = history_window_override()
        if hw_override is not None:
            self.config.history_window = hw_override

        self.logger = ChatLogger(
            title=chat.meta.title,
            input_file=input_path,
            model_label=model_label(),
        )
        self.history_summarizer = HistorySummarizer() if chat.config.history_summary_chars > 0 else None
        self.history_summary = ""
        self._summarized_turns = 0
        self.planner = ChatPlanner(chat.characters, chat.phases)
        self._llm_combined = chat.config.turn_selection == "llm"
        if chat.config.turn_selection == "llm":
            self.orc = None
        else:
            self.orc = ChatOrchestrator(chat.characters, chat.config, planner=self.planner)
        self.gm  = GMAgent(
            world_info=chat.world_info,
            gm_prompt=chat.gm_prompt,
            writing_style=chat.writing_style,
            scenario=chat.scenario,
            characters=chat.characters,
            config=chat.config,
        )

        # Mutable loop state
        self.stopped          = False
        self.pause_mode       = False          # True = pause after every turn
        self.force_speaker: str | None = None
        self.pending_director: str | None = None
        self.end_reason       = "max turns reached"

        # Resolve output paths once at init so autosave doesn't recompute each turn
        root = Path(input_path).parent.parent
        self._transcript_path = str(root / chat.meta.output_transcript)
        self._runlog_path     = str(root / chat.meta.output_runlog)

    # -----------------------------------------------------------------------
    # Main loop
    # -----------------------------------------------------------------------

    def run(self) -> None:
        _print_header(self.chat.meta.title, self.input_path)
        _warn_context(self)

        try:
            while not self.stopped:
                # Max turns guard
                if self._at_hard_turn_limit():
                    hard_limit = self._hard_turn_limit()
                    print(f"\n[Turn limit ({hard_limit}) reached.]")
                    self.end_reason = f"turn limit ({hard_limit})"
                    break

                self._gm_turn()

                if self.stopped:
                    break

                # Auto-pause every N turns, or if pause_mode is on
                tc = self.logger.turn_count()
                if self.pause_mode or (
                    self.config.pause_every > 0
                    and tc % self.config.pause_every == 0
                ):
                    self._handle_pause()

        except KeyboardInterrupt:
            print("\n\n[Interrupted]")
            self.end_reason = "keyboard interrupt"

        self._end_session()

    # -----------------------------------------------------------------------
    # GM turn
    # -----------------------------------------------------------------------

    def _gm_turn(self) -> None:
        turns   = self.logger.turns
        history = self._build_history_context(turns)
        phase_context = self._build_turn_guidance(turns)
        director_used      = self.pending_director
        self.pending_director = None

        if self._llm_combined:
            fixed_speaker = self.force_speaker or self._opening_speaker(turns)
            self.force_speaker = None

            try:
                if fixed_speaker:
                    prompt = self.gm.build_turn_prompt(
                        history=history,
                        speaker=fixed_speaker,
                        director_note=director_used,
                        phase_context=phase_context,
                    )
                    result = self.gm.generate(prompt, fixed_speaker)
                    speaker = fixed_speaker
                    rule = "forced" if turns and fixed_speaker == self.force_speaker else "opening_turn"
                else:
                    prompt = self.gm.build_selected_turn_prompt(
                        history=history,
                        available_speakers=[c.name for c in self.chat.characters],
                        phase_context=phase_context,
                        director_note=director_used,
                    )
                    result = self.gm.generate_selected_turn(
                        prompt,
                        [c.name for c in self.chat.characters],
                    )
                    speaker = result.speaker
                    rule = "llm_combined_turn"
            except Exception as exc:
                print(f"\n[GM error: {exc}]")
                print("  Options: Enter = retry | /stop = quit")
                raw = _read_input().strip()
                if raw == "/stop":
                    self.stopped    = True
                    self.end_reason = "user /stop (after GM error)"
                return
        else:
            sel     = self.orc.select_next_speaker(turns, self.force_speaker)
            self.force_speaker = None
            tone    = self.orc.get_tone_hint(turns, sel.speaker)
            prompt  = self.gm.build_turn_prompt(
                history        = history,
                speaker        = sel.speaker,
                tone_hint      = tone,
                director_note  = director_used,
                phase_context  = phase_context,
            )

            try:
                result = self.gm.generate(prompt, sel.speaker)
            except Exception as exc:
                print(f"\n[GM error: {exc}]")
                print("  Options: Enter = retry | /stop = quit")
                raw = _read_input().strip()
                if raw == "/stop":
                    self.stopped    = True
                    self.end_reason = "user /stop (after GM error)"
                return

            speaker = sel.speaker
            rule = sel.rule

        self.logger.append_turn(
            speaker       = speaker,
            text          = result.dialogue,
            generator     = "gm",
            rule          = rule,
            tokens        = result.tokens,
            director_note = director_used,
        )

        _print_turn(self.logger.turn_count(), speaker, result.dialogue)
        self._autosave()

    def _build_history_context(self, turns) -> str:
        self._refresh_history_summary(turns)
        recent_history = self.logger.get_history(self.config.history_window)
        return format_history_with_summary(self.history_summary, recent_history)

    def _refresh_history_summary(self, turns) -> None:
        if not self.history_summarizer or self.config.history_window <= 0:
            return

        cutoff = max(0, len(turns) - self.config.history_window)
        if cutoff <= self._summarized_turns:
            return

        turns_to_summarize = turns[self._summarized_turns:cutoff]
        if not turns_to_summarize:
            return

        try:
            update = self.history_summarizer.update_summary(
                self.history_summary,
                turns_to_summarize,
                self.config.history_summary_chars,
            )
        except Exception:
            return

        self.history_summary = update.text
        self._summarized_turns = cutoff

    def _opening_speaker(self, turns) -> str | None:
        if turns:
            return None
        name = self.config.opening_speaker
        if name != "auto":
            char = _find_character(name, self.chat.characters)
            return char.name if char else None
        for char in self.chat.characters:
            if char.role == "player-character":
                return char.name
        return self.chat.characters[0].name if self.chat.characters else None

    def _hard_turn_limit(self) -> int:
        if self.config.max_turns <= 0:
            return 0
        return self.config.max_turns + max(0, self.config.ending_grace_turns)

    def _at_hard_turn_limit(self) -> bool:
        hard_limit = self._hard_turn_limit()
        return hard_limit > 0 and self.logger.turn_count() >= hard_limit

    def _build_turn_guidance(self, turns) -> str | None:
        phase_context = self.planner.phase_prompt(turns)
        ending_context = self._ending_prompt(turns)
        parts = [part for part in (phase_context, ending_context) if part]
        return "\n\n".join(parts) if parts else None

    def _ending_prompt(self, turns) -> str | None:
        if self.config.max_turns <= 0:
            return None

        next_turn = len(turns) + 1
        turns_until_target = self.config.max_turns - next_turn
        hard_limit = self._hard_turn_limit()
        turns_until_hard_limit = hard_limit - next_turn

        if turns_until_target >= max(0, self.config.ending_countdown_turns):
            return None

        if next_turn <= self.config.max_turns:
            remaining = max(0, self.config.max_turns - next_turn + 1)
            turn_word = "turn" if remaining == 1 else "turns"
            return (
                "ENDING WINDOW:\n"
                f"The planned chat length is nearly reached. Begin landing the current scene within the next {remaining} {turn_word}. "
                "Move toward a natural stopping beat, decision, reveal, or transition. Do not open major new threads."
            )

        remaining = max(0, turns_until_hard_limit + 1)
        turn_word = "turn" if remaining == 1 else "turns"
        return (
            "FINAL LANDING WINDOW:\n"
            f"The chat is beyond its planned length. Use the next {remaining} {turn_word} to finish the current scene cleanly. "
            "Close loops already in motion, keep lines concise, and avoid introducing any new subplot or cast pivot."
        )

    # -----------------------------------------------------------------------
    # Human pause prompt
    # -----------------------------------------------------------------------

    def _handle_pause(self) -> None:
        """Print the pause divider and handle one round of human input."""
        tc    = self.logger.turn_count()
        stats = self.logger.speaking_stats()
        mode  = "  [pause mode ON]" if self.pause_mode else ""
        print(f"\n{_DIV}")
        print(f"Turn {tc}{mode}  │  " + "  ".join(f"{n}: {c}" for n, c in stats.items()))
        print(_DIV)

        while True:
            raw = _read_input("  Enter to continue, or type a command: ").strip()

            # ---- Enter: continue ----------------------------------------
            if not raw:
                return

            # ---- /stop --------------------------------------------------
            if raw == "/stop":
                self.stopped    = True
                self.end_reason = "user /stop"
                return

            # ---- /pause -------------------------------------------------
            if raw == "/pause":
                self.pause_mode = not self.pause_mode
                flag = "ON — pausing after every turn" if self.pause_mode else "OFF"
                print(f"  Pause mode: {flag}")
                return

            # ---- /status ------------------------------------------------
            if raw == "/status":
                _print_status(self.logger)
                continue

            # ---- /help --------------------------------------------------
            if raw == "/help":
                print(_HELP)
                continue

            # ---- /next Name ---------------------------------------------
            if raw.lower().startswith("/next "):
                name = raw[6:].strip()
                char = _find_character(name, self.chat.characters)
                if char:
                    self.force_speaker = char.name
                    print(f"  → {char.name} will speak next.")
                else:
                    print(f"  Unknown character: '{name}'")
                    print("  Known: " + ", ".join(c.name for c in self.chat.characters))
                return

            # ---- [as Name] text -----------------------------------------
            m = re.match(r'\[as\s+(.+?)\]\s*(.*)', raw, re.DOTALL)
            if m:
                name = m.group(1).strip()
                text = m.group(2).strip()
                char = _find_character(name, self.chat.characters)
                if not char:
                    print(f"  Unknown character: '{name}'")
                    print("  Known: " + ", ".join(c.name for c in self.chat.characters))
                    continue
                if not text:
                    print("  No dialogue text provided after character name.")
                    continue
                if not char.can_be_taken_over:
                    print(f"  {char.name} cannot be taken over (can_be_taken_over: false).")
                    continue
                self.logger.append_turn(
                    speaker   = char.name,
                    text      = text,
                    generator = "human",
                    rule      = "human_injection",
                    cmd       = raw,
                )
                _print_turn(self.logger.turn_count(), char.name, text)
                self._autosave()
                return

            # ---- [director] note ----------------------------------------
            m = re.match(r'\[director\]\s*(.*)', raw, re.DOTALL)
            if m:
                note = m.group(1).strip()
                if not note:
                    print("  No director note text provided.")
                    continue
                self.pending_director = note
                print("  Director note saved — will be passed to GM on next turn.")
                return

            # ---- unknown ------------------------------------------------
            print("  Unrecognised input. Type /help for commands.")


    # -----------------------------------------------------------------------
    # Autosave + session end
    # -----------------------------------------------------------------------

    def _autosave(self) -> None:
        """Write both output files after every turn so nothing is lost on crash."""
        self.logger.save_transcript(self._transcript_path)
        self.logger.save_runlog(self._runlog_path, end_reason="in progress")

    def _end_session(self) -> None:
        print(f"\n{_DIV}")
        print(f"Session ended — {self.end_reason}")

        self.logger.save_transcript(self._transcript_path)
        self.logger.save_runlog(self._runlog_path, end_reason=self.end_reason)

        print(f"Transcript  → {self._transcript_path}")
        print(f"Run log     → {self._runlog_path}")

        stats = self.logger.speaking_stats()
        print(f"\nTotal turns : {self.logger.turn_count()}")
        for name, count in stats.items():
            print(f"  {name:<20} {count} turns")
        print(_DIV)


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def _print_header(title: str, input_path: str) -> None:
    print(f"\n{_DIV}")
    print(f"  {title}")
    print(f"  {input_path}")
    print(_DIV)
    print()


def _warn_context(session: "ChatSession") -> None:
    """Rough token estimate at startup. Warns if the session looks oversized for the
    configured context limit. Uses chars/4 as a token approximation — good enough
    for a sanity check.
    """
    from src.chat.gm_agent import _build_system_prompt  # local import to avoid circularity

    system_prompt = _build_system_prompt(
        gm_prompt=session.chat.gm_prompt,
        writing_style=session.chat.writing_style,
        world_info=session.chat.world_info,
        scenario=session.chat.scenario,
        characters=session.chat.characters,
        response_length=session.config.response_length,
    )

    # Average turn: ~80 chars of dialogue + speaker prefix + quotes
    avg_turn_chars = 120
    history_chars  = session.config.history_window * avg_turn_chars
    # Full card for one character (the per-turn speaker card injection)
    avg_card_chars = max(
        (len(c.description or "") + len(c.personality or "") + len(c.speech_style or "") + len(c.backstory or ""))
        for c in session.chat.characters
    )
    summary_chars = session.config.history_summary_chars

    total_chars  = len(system_prompt) + history_chars + avg_card_chars + summary_chars
    total_tokens = total_chars // 4  # chars-to-tokens approximation

    limit = context_limit()
    if total_tokens > limit:
        print(f"  [CONTEXT WARNING] Estimated max prompt size: ~{total_tokens} tokens "
              f"(limit: {limit}).")
        print(f"  Consider reducing history_window (currently {session.config.history_window}) "
              f"or set CHAT_ENGINE_HISTORY_WINDOW in .env.")
        print()


def _print_turn(turn_number: int, speaker: str, text: str) -> None:
    print(f'[T{turn_number:03d}] {speaker}: "{text}"')


def _print_status(logger: ChatLogger) -> None:
    print(f"  Turn count  : {logger.turn_count()}")
    print(f"  Last speaker: {logger.last_speaker()}")
    stats = logger.speaking_stats()
    for name, count in stats.items():
        print(f"    {name:<20} {count} turns")


# ---------------------------------------------------------------------------
# Input helper (thin wrapper so __main__ tests can patch it)
# ---------------------------------------------------------------------------

def _read_input(prompt: str = "") -> str:
    try:
        return input(prompt)
    except EOFError:
        return "/stop"


# ---------------------------------------------------------------------------
# Character name resolver — fuzzy match for human commands
# ---------------------------------------------------------------------------

def _find_character(name: str, characters: list[CharacterCard]) -> CharacterCard | None:
    """Resolve a name (possibly short or a trigger word) to a CharacterCard."""
    lower = name.lower()
    # 1. Exact full-name match
    for c in characters:
        if c.name.lower() == lower:
            return c
    # 2. Full name starts with input (e.g. "Lyra" → "Lyra Voss")
    for c in characters:
        if c.name.lower().startswith(lower):
            return c
    # 3. Any trigger word matches (e.g. "the monk" → Brother Aldric)
    for c in characters:
        if any(t.lower() == lower for t in c.triggers):
            return c
    return None


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> None:
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print("Usage: python -m src.chat.main_chat <input_file.md>")
        sys.exit(1)

    input_path = args[0]

    # Resolve relative to cwd
    p = Path(input_path)
    if not p.is_absolute():
        p = Path.cwd() / p

    if not p.exists():
        print(f"Error: file not found: {p}")
        sys.exit(1)

    try:
        chat = parse_chat_file(str(p))
    except Exception as exc:
        print(f"Error parsing input file: {exc}")
        sys.exit(1)

    session = ChatSession(chat, str(p))
    session.run()


if __name__ == "__main__":
    main()
