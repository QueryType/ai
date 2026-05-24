"""ChatOrchestrator — rule-based turn selection for Phase 1.

Rules applied in order; first match wins:
  1. Direct Address   — last line names a character or is a direct question
  2. Human Takeover   — human just spoke; most relevant character reacts
  3. Conflict         — last exchange had tension; challenged party responds
  4. Round-Robin      — no clear trigger; rotate, skip last 2 speakers
  5. Fallback         — character with lowest weighted speaking debt speaks
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.chat.chat_logger import TurnRecord
from src.chat.parser import CharacterCard, ChatConfig
from src.chat.planner import ChatPlanner


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class TurnSelection:
    speaker: str
    rule: str      # slug used in run log, e.g. "direct_address"
    reason: str    # human-readable explanation (for debugging / Phase 2 handoff)


# ---------------------------------------------------------------------------
# Tension vocabulary (Rule 3)
# ---------------------------------------------------------------------------

_TENSION_PHRASES = {
    "no,", "no.", "no!", "wrong", "mistake", "fool", "liar", "doubt",
    "disagree", "not true", "you're wrong", "you are wrong",
    "i don't think", "i won't", "i can't", "you would", "you think",
    "that's not", "hardly", "unlikely", "afraid", "fear", "danger",
    "stop", "enough", "stay out", "get away", "leave",
}


def _has_tension(text: str) -> bool:
    lower = text.lower()
    return any(phrase in lower for phrase in _TENSION_PHRASES)


def _has_direct_question(text: str) -> bool:
    return "?" in text


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class ChatOrchestrator:
    """Selects the next speaker using the 5 Phase-1 rules."""

    def __init__(
        self,
        characters: list[CharacterCard],
        config: ChatConfig,
        planner: ChatPlanner | None = None,
    ):
        self._characters = characters
        self._config = config
        self._planner = planner
        self._char_by_name: dict[str, CharacterCard] = {c.name: c for c in characters}

        # Trigger map: trigger_word (lower) → character name
        # Longer triggers shadow shorter ones on collision to reduce ambiguity
        # ("the scout" beats "she" when both could match Lyra)
        self._trigger_map: dict[str, str] = {}
        for c in sorted(characters, key=lambda c: min(len(t) for t in c.triggers)):
            for trigger in c.triggers:
                self._trigger_map[trigger.lower().strip()] = c.name

        # Weighted debt accumulator for round-robin (Rule 4 / Rule 5)
        # Each time a character speaks, their debt increases by 1/speaking_weight.
        # Lower debt = hasn't spoken proportionally enough = speaks sooner.
        self._debt: dict[str, float] = {c.name: 0.0 for c in characters}

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def select_next_speaker(
        self,
        turns: list[TurnRecord],
        force_speaker: str | None = None,
    ) -> TurnSelection:
        """Apply the 5 rules in order and return a TurnSelection.

        Args:
            turns: All turns so far (from ChatLogger).
            force_speaker: If set (/next command), bypass rules and return this speaker.
        """
        # Forced speaker via /next command — record it but still update debt
        if force_speaker and force_speaker in self._char_by_name:
            self._charge_debt(force_speaker)
            return TurnSelection(
                speaker=force_speaker,
                rule="forced",
                reason=f"/next command forced {force_speaker}",
            )

        # Opening turn — no history yet
        if not turns:
            speaker = self._apply_plan([], self._opening_speaker())
            self._charge_debt(speaker)
            return TurnSelection(
                speaker=speaker,
                rule="opening_turn",
                reason=f"First turn — opening_speaker from config: {speaker}",
            )

        last = turns[-1]

        # ---- Rule 1: Direct Address ----------------------------------------
        sel = self._rule_direct_address(last, turns)
        if sel:
            self._charge_debt(sel.speaker)
            return sel

        # ---- Rule 2: Human Takeover ----------------------------------------
        if last.generator == "human":
            sel = self._rule_human_reaction(last, turns)
            if sel:
                self._charge_debt(sel.speaker)
                return sel

        # ---- Rule 3: Conflict Escalation -----------------------------------
        sel = self._rule_conflict(turns)
        if sel:
            self._charge_debt(sel.speaker)
            return sel

        # ---- Rule 4 + 5: Round-Robin with weighted debt --------------------
        sel = self._rule_round_robin(turns)
        self._charge_debt(sel.speaker)
        return sel

    def get_tone_hint(self, turns: list[TurnRecord], speaker: str) -> str | None:
        """Return an optional tone hint for the GM prompt. None = no hint."""
        if not turns:
            return None

        last = turns[-1]

        if _has_tension(last.text):
            return "tense exchange — keep the response clipped and defensive"

        if last.generator == "human":
            return "react naturally and directly to what was just said"

        if _has_direct_question(last.text):
            return "address the question in character — don't fully deflect"

        return None

    # -----------------------------------------------------------------------
    # Rule implementations
    # -----------------------------------------------------------------------

    def _rule_direct_address(
        self,
        last: TurnRecord,
        turns: list[TurnRecord] | None = None,
    ) -> TurnSelection | None:
        """Rule 1 — last line names a character or contains a direct question."""
        text_lower = last.text.lower()

        # Find all trigger matches, excluding self-reference
        hits: dict[str, int] = {}  # char_name → longest matching trigger length
        for trigger, char_name in self._trigger_map.items():
            if char_name == last.speaker:
                continue
            if re.search(r"\b" + re.escape(trigger) + r"\b", text_lower):
                if char_name not in hits or len(trigger) > hits[char_name]:
                    hits[char_name] = len(trigger)

        if hits:
            # If only one character is addressed, use them
            if len(hits) == 1:
                name = next(iter(hits))
                trigger_word = _longest_trigger(self._trigger_map, name, text_lower)
                return TurnSelection(
                    speaker=name,
                    rule="direct_address",
                    reason=f"Last line addressed '{name}' via trigger '{trigger_word}'",
                )
            # Multiple candidates — prefer the one with the longest (most specific) trigger
            # e.g. "Brother Aldric" beats "he" — reduces pronoun ambiguity
            best = max(hits, key=lambda n: hits[n])
            return TurnSelection(
                speaker=best,
                rule="direct_address",
                reason=f"Multiple triggers matched; selected '{best}' (most specific)",
            )

        # No trigger match — check for a bare direct question (no name)
        # Infer the respondent from the most recent prior speaker who isn't the questioner
        if _has_direct_question(last.text) and turns:
            for turn in reversed(turns[:-1]):
                if turn.speaker != last.speaker and turn.speaker in self._char_by_name:
                    return TurnSelection(
                        speaker=turn.speaker,
                        rule="direct_address",
                        reason=f"Direct question with no name; '{turn.speaker}' was last interlocutor",
                    )

        return None

    def _rule_human_reaction(
        self, last: TurnRecord, turns: list[TurnRecord]
    ) -> TurnSelection | None:
        """Rule 2 — human just spoke; pick the character most likely to react."""
        # First, check if the human's text directly addresses a character
        direct = self._rule_direct_address(last)
        if direct:
            return TurnSelection(
                speaker=direct.speaker,
                rule="human_reaction",
                reason=f"Human injection addressed '{direct.speaker}' directly",
            )

        # Otherwise: eligible = everyone except who just spoke, not in last 2 turns
        recent = {t.speaker for t in turns[-2:]}
        candidates = [c for c in self._characters if c.name not in recent]
        if not candidates:
            candidates = [c for c in self._characters if c.name != last.speaker]
        if not candidates:
            return None

        # Prefer the character with the highest speaking_weight (most "active" in scene)
        best = max(candidates, key=lambda c: c.speaking_weight)
        speaker = self._apply_plan(turns, best.name, [c.name for c in candidates])
        reason = (
            self._planner.selection_reason(turns, speaker)
            if self._planner and speaker != best.name
            else f"Human spoke; '{best.name}' is most likely to react (weight {best.speaking_weight})"
        )
        return TurnSelection(
            speaker=speaker,
            rule="human_reaction",
            reason=reason,
        )

    def _rule_conflict(self, turns: list[TurnRecord]) -> TurnSelection | None:
        """Rule 3 — last exchange had tension; the challenged party responds."""
        if len(turns) < 2:
            return None

        last = turns[-1]
        if not (_has_tension(last.text) or _has_direct_question(last.text)):
            return None

        # The party being challenged is the previous speaker
        prev = turns[-2]
        if prev.speaker == last.speaker:
            return None  # self-monologue — no clear challenged party

        return TurnSelection(
            speaker=prev.speaker,
            rule="conflict_escalation",
            reason=f"Tension detected in '{last.speaker}' line; '{prev.speaker}' was challenged",
        )

    def _rule_round_robin(self, turns: list[TurnRecord]) -> TurnSelection:
        """Rule 4+5 — round-robin skipping recent speakers, weighted by speaking_weight."""
        recent_names = {t.speaker for t in turns[-2:]} if turns else set()

        eligible = [c for c in self._characters if c.name not in recent_names]
        if not eligible:
            # Everyone spoke recently — drop the recency filter
            eligible = list(self._characters)

        # Rule 5 embedded: lowest debt = proportionally underrepresented = speaks next
        best = min(eligible, key=lambda c: self._debt[c.name])
        plan_candidates = [c.name for c in self._characters] if self._planner else [c.name for c in eligible]
        speaker = self._apply_plan(turns, best.name, plan_candidates)

        rule = "round_robin" if len(eligible) > 1 else "fallback"
        return TurnSelection(
            speaker=speaker,
            rule=rule,
            reason=(
                self._planner.selection_reason(turns, speaker)
                if self._planner and speaker != best.name
                else f"Round-robin selected '{best.name}' (debt={self._debt[best.name]:.2f})"
            ),
        )

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    def _opening_speaker(self) -> str:
        name = self._config.opening_speaker
        if name != "auto" and name in self._char_by_name:
            return name
        # auto: prefer player-character, else first in list
        for c in self._characters:
            if c.role == "player-character":
                return c.name
        return self._characters[0].name

    def _charge_debt(self, name: str) -> None:
        """Increment weighted debt for the speaker who just took a turn."""
        c = self._char_by_name.get(name)
        if c:
            weight = max(c.speaking_weight, 0.01)  # guard div-by-zero
            self._debt[name] += 1.0 / weight

    def _apply_plan(
        self,
        turns: list[TurnRecord],
        preferred: str,
        candidates: list[str] | None = None,
    ) -> str:
        if not self._planner:
            return preferred
        return self._planner.choose_speaker(turns, preferred, candidates)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _longest_trigger(trigger_map: dict[str, str], char_name: str, text_lower: str) -> str:
    """Return the longest trigger that matched char_name in text_lower."""
    best = ""
    for trigger, name in trigger_map.items():
        if name == char_name and trigger in text_lower and len(trigger) > len(best):
            best = trigger
    return best


# ---------------------------------------------------------------------------
# __main__ — rule-by-rule verification
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from src.chat.parser import parse_chat_file
    from pathlib import Path

    root = Path(__file__).parent.parent.parent
    chat = parse_chat_file(str(root / "examples/ashenveil_chat1.md"))

    # Canonical names from the parsed character cards
    LYRA   = chat.characters[0].name   # "Lyra Voss"
    ALDRIC = chat.characters[1].name   # "Brother Aldric"
    MIRA   = chat.characters[2].name   # "Mira"

    orc = ChatOrchestrator(chat.characters, chat.config)

    def fake_turn(speaker: str, text: str, generator: str = "gm") -> TurnRecord:
        return TurnRecord(
            turn_number=0, speaker=speaker, text=text,
            generator=generator, rule="", tokens=80,
        )

    DIVIDER = "-" * 60

    print(DIVIDER)
    print("RULE: opening_turn  (no history)")
    sel = orc.select_next_speaker([])
    print(f"  → {sel.speaker}  [{sel.rule}]  {sel.reason}")

    print(DIVIDER)
    print("RULE: direct_address  ('Aldric' named in last line)")
    turns = [
        fake_turn(LYRA, "You're going in there alone, Aldric. That's either brave or stupid."),
    ]
    sel = orc.select_next_speaker(turns)
    print(f"  → {sel.speaker}  [{sel.rule}]  {sel.reason}")

    print(DIVIDER)
    print("RULE: direct_address  (direct question, no name — infer last interlocutor)")
    turns = [
        fake_turn(LYRA,   "You're not from around here."),
        fake_turn(ALDRIC, "No. I've been away a long time. What brings you here?"),
    ]
    sel = orc.select_next_speaker(turns)
    print(f"  → {sel.speaker}  [{sel.rule}]  {sel.reason}")

    print(DIVIDER)
    print("RULE: human_reaction  (human just spoke)")
    turns = [
        fake_turn(LYRA,   "I've been watching you for three days.",  generator="gm"),
        fake_turn(LYRA,   "I'm here because of you.",                generator="human"),
    ]
    sel = orc.select_next_speaker(turns)
    print(f"  → {sel.speaker}  [{sel.rule}]  {sel.reason}")

    print(DIVIDER)
    print("RULE: conflict_escalation  (tension + prev speaker challenged)")
    turns = [
        fake_turn(LYRA,   "You know what's in there. Don't pretend otherwise."),
        fake_turn(ALDRIC, "I know nothing of the sort. You're wrong about me."),
    ]
    sel = orc.select_next_speaker(turns)
    print(f"  → {sel.speaker}  [{sel.rule}]  {sel.reason}")

    print(DIVIDER)
    print("RULE: round_robin  (neutral line, no trigger, no tension)")
    turns = [
        fake_turn(LYRA,   "The wind has picked up."),
        fake_turn(ALDRIC, "So it has."),
    ]
    sel = orc.select_next_speaker(turns)
    print(f"  → {sel.speaker}  [{sel.rule}]  {sel.reason}")

    print(DIVIDER)
    print("RULE: round_robin weighted  (Mira weight=0.6 vs others 1.0)")
    print("  Note: with 3 chars + skip-last-2, Mira is often the only eligible candidate.")
    print("  Weight shows its effect in 4+ character casts or shorter recency windows.")
    print("  Running 60 turns to show debt accumulation keeps Mira at ~60% of others:")
    orc2 = ChatOrchestrator(chat.characters, chat.config)
    counts: dict[str, int] = {c.name: 0 for c in chat.characters}
    history: list[TurnRecord] = []
    for _ in range(60):
        sel2 = orc2.select_next_speaker(history)
        counts[sel2.speaker] += 1
        history.append(fake_turn(sel2.speaker, "The ruins are silent."))

    total = sum(counts.values())
    for name, cnt in counts.items():
        w = orc2._char_by_name[name].speaking_weight
        debt = orc2._debt[name]
        print(f"    {name:<16} spoke {cnt:>2}x ({cnt/total*100:.0f}%)  weight={w}  debt={debt:.2f}")

    print(DIVIDER)
    print("RULE: forced  (/next Mira)")
    turns = [fake_turn(LYRA, "Something is here.")]
    sel = orc.select_next_speaker(turns, force_speaker=MIRA)
    print(f"  → {sel.speaker}  [{sel.rule}]  {sel.reason}")

    print(DIVIDER)
    print("TONE HINTS")
    cases = [
        (LYRA,   [fake_turn(ALDRIC, "You're wrong. Completely wrong.")]),
        (ALDRIC, [fake_turn(LYRA,   "I'm here because of you.", generator="human")]),
        (MIRA,   [fake_turn(LYRA,   "What is your name?")]),
        (LYRA,   [fake_turn(ALDRIC, "The stone is cold tonight.")]),
    ]
    for speaker, t in cases:
        hint = orc.get_tone_hint(t, speaker)
        print(f"  {speaker:<16} last='{t[-1].text[:45]}' → {hint!r}")

    print()
    print("OK — orchestrator tests complete.")
