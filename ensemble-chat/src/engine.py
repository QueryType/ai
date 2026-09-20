"""Chat engine: append-only history, cache-stable prompt, streaming turns."""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from openai import AsyncOpenAI

from src import vision
from src.cast import Character, Scenario
from src.config import Config
from src.policy import Policy
from src.prompt import build_system_prompt, speaker_directive
from src.register import (
    f2f_block,
    find_tics,
    split_bubbles,
    strip_speaker_prefix,
    trim_incomplete_sentence,
)
from src.rut import RutTracker
from src.selector import Selector
from src.state import State, render
from src.tracker import StateTracker

_CLASSIFIER_TAIL = 14


@dataclass
class TurnResult:
    speaker: Character
    text: str
    bubbles: list[str]
    tics: list[str]
    truncated: bool = False
    reasoning_tokens: int = 0


@dataclass
class _TurnCheckpoint:
    """Enough to undo everything from one turn() call onward. One is
    recorded per turn that actually produced a reply (see Engine.turn()) —
    Engine.regenerate() only ever needs the last one, Engine.delete_from()
    can rewind to any of them.

    `history_end` on the last checkpoint is what pins regenerate down: it's
    only valid while nothing has been appended to history since (a new turn,
    a continuation, a state-block sync all change len(history) and
    invalidate it), so validity is just a length comparison.
    """

    directive_start: int
    history_end: int
    speaker: str
    debt_snapshot: dict[str, float]
    last_speaker_before: str | None
    rut_snapshot: dict[str, object]


@dataclass
class Engine:
    scenario: Scenario
    cfg: Config
    policy: Policy
    client: AsyncOpenAI
    history: list[dict] = field(default_factory=list)
    state: State = field(default_factory=State)
    last_speaker: str | None = None
    # Only used when `turn()` is called with an image; harmless default for
    # callers (harness.py) that never do.
    attachments_dir: Path = field(default_factory=lambda: Path("."))
    state_error: str = ""
    _state_block: str = ""
    _task: asyncio.Task | None = None
    _pending: bool = False
    _checkpoints: list[_TurnCheckpoint] = field(default_factory=list)
    selector: Selector = field(init=False)
    rut: RutTracker = field(init=False)
    tracker: StateTracker = field(init=False)
    system_prompt: str = field(init=False)

    def __post_init__(self) -> None:
        self.selector = Selector(self.scenario)
        self.rut = RutTracker()
        self.tracker = StateTracker(self.client, self.cfg, self.policy, self.state)
        self.system_prompt = build_system_prompt(self.scenario)

    def _sync_state(self) -> None:
        """Append the state block only when it changed, keeping history append-only.

        Nothing is emitted until the classifier has run at least once — an
        unmeasured default would assert a mood and closeness it cannot know.
        """
        if not self.state.updated:
            return
        block = render(self.state, self.policy.state_block_tokens)
        if block != self._state_block:
            self._state_block = block
            self.history.append({"role": "system", "content": block})

    def _classifier_tail(self) -> list[dict]:
        spoken = [m for m in self.history if m["role"] in ("user", "assistant")]
        return vision.hydrate(spoken[-_CLASSIFIER_TAIL:], self.attachments_dir)

    async def _update_state(self, speaker: str) -> None:
        """Re-runs if turns arrived while this was in flight, so nothing is dropped."""
        while True:
            try:
                await self.tracker.update(self._classifier_tail(), speaker=speaker)
                self.state_error = ""
            except Exception as exc:
                self.state_error = f"{type(exc).__name__}: {exc}"
            if not self._pending:
                return
            self._pending = False

    def _schedule_state_update(self, speaker: str) -> None:
        """Always fire-and-forget, however many slots the server has.

        With one slot the request simply queues server-side and the user's
        typing pause absorbs it. Awaiting it here would stall the input prompt
        instead, which measured 2.1x slower per turn and is never what you want.
        """
        if not self.tracker.enabled:
            return
        if self._task and not self._task.done():
            self._pending = True
            return
        self._pending = False
        self._task = asyncio.create_task(self._update_state(speaker))

    async def drain(self) -> None:
        if self._task and not self._task.done():
            await asyncio.wait({self._task}, timeout=30)

    async def turn(
        self,
        user_text: str,
        on_chunk: Callable[[str], None],
        force_speaker: str | None = None,
        extra_directive: str = "",
        image: bytes | None = None,
        on_speaker: Callable[[Character], None] | None = None,
    ) -> TurnResult:
        self._sync_state()
        debt_snapshot = dict(self.selector.debt)
        last_speaker_before = self.last_speaker
        rut_snapshot = self.rut.snapshot()
        if image is not None:
            if not self.policy.vision_capable:
                raise ValueError("this model doesn't accept image input")
            path = vision.save_attachment(image, self.attachments_dir, self.cfg.vision_max_dimension)
            content_parts: list[dict] = []
            if user_text:
                content_parts.append({"type": "text", "text": user_text})
            content_parts.append(vision.image_ref(path, self.attachments_dir))
            self.history.append({"role": "user", "content": content_parts})
        elif user_text:
            self.history.append({"role": "user", "content": user_text})

        forced = self.scenario.by_name(force_speaker) if force_speaker else None
        if forced:
            speaker = forced
            self.selector.charge(forced)
        else:
            speaker = self.selector.select(user_text, self.last_speaker)
        if on_speaker:
            on_speaker(speaker)
        directive = speaker_directive(speaker.name)
        if nudge := self.rut.nudge(speaker.name):
            directive = f"{directive} {nudge}"
        if extra_directive:
            directive = f"{directive} {extra_directive}"
        directive_start = len(self.history)
        self.history.append({"role": "system", "content": directive})

        parts: list[str] = []
        finish_reason: str | None = None
        reasoning_tokens = 0
        stream = await self.client.chat.completions.create(
            model=self.cfg.model,
            messages=[{"role": "system", "content": self.system_prompt}]
            + vision.hydrate(self.history, self.attachments_dir),
            max_tokens=self.policy.reply_max_tokens,
            temperature=self.cfg.temperature,
            stream=True,
            stream_options={"include_usage": True},
        )
        async for chunk in stream:
            if chunk.usage and chunk.usage.completion_tokens_details:
                reasoning_tokens = chunk.usage.completion_tokens_details.reasoning_tokens or 0
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            delta = choice.delta.content
            if delta:
                parts.append(delta)
                on_chunk(delta)
            if choice.finish_reason:
                finish_reason = choice.finish_reason

        truncated = finish_reason == "length"
        text = strip_speaker_prefix(
            "".join(parts).strip(), [c.name for c in self.scenario.characters]
        )
        if truncated:
            text = trim_incomplete_sentence(text)
        if text:
            self.history.append({"role": "assistant", "content": f"{speaker.name}: {text}"})
            self.last_speaker = speaker.name
            self.rut.record(speaker.name, text)

        self._schedule_state_update(speaker.name)

        # Only recorded when a reply actually landed — keeps this list in
        # exact 1:1 order with the assistant entries transcript.py exposes,
        # which is what delete_from()'s turn_index addresses.
        if text:
            self._checkpoints.append(_TurnCheckpoint(
                directive_start=directive_start,
                history_end=len(self.history),
                speaker=speaker.name,
                debt_snapshot=debt_snapshot,
                last_speaker_before=last_speaker_before,
                rut_snapshot=rut_snapshot,
            ))

        bubbles = f2f_block(text) if self.scenario.mode == "f2f" else split_bubbles(text)
        return TurnResult(
            speaker=speaker,
            text=text,
            bubbles=bubbles,
            tics=find_tics(text),
            truncated=truncated,
            reasoning_tokens=reasoning_tokens,
        )

    @property
    def turn_count(self) -> int:
        """Replies actually produced so far — what autopilot.py's turn cap
        counts against, and what last_turn_index()/delete_from() address."""
        return len(self._checkpoints)

    def last_turn_index(self) -> int | None:
        """The checkpoint index of the reply turn() just produced, for
        callers (ui/web.py) that need to hand it back to the client so a
        later delete_from() can address it. None if nothing's been said yet."""
        return len(self._checkpoints) - 1 if self._checkpoints else None

    def can_regenerate(self) -> bool:
        """Only the most recent reply, and only while it's still the last
        thing that happened — anything appended since invalidates it."""
        return bool(self._checkpoints) and len(self.history) == self._checkpoints[-1].history_end

    def _restore_checkpoint(self, cp: _TurnCheckpoint) -> None:
        self.history = self.history[: cp.directive_start]
        self.selector.debt.clear()
        self.selector.debt.update(cp.debt_snapshot)
        self.last_speaker = cp.last_speaker_before
        self.rut.restore(cp.rut_snapshot)

    async def regenerate(
        self,
        on_chunk: Callable[[str], None],
        guidance: str = "",
        on_speaker: Callable[[Character], None] | None = None,
    ) -> TurnResult:
        """Redo the last reply, same speaker, with an optional short
        guidance nudge for the retry. A genuine history mutation — one of
        the two deliberate exceptions to the append-only rule in DESIGN.md
        (delete_from() is the other), accepted because it only fires on
        explicit user action and only ever touches the still-last turn.
        Pays a full cache-reprocess on the next request since the prefix
        changed; see BACKLOG.md.

        State (mood/threads/traits) is not rolled back — the background
        classifier may have already updated it from the discarded reply.
        Left alone deliberately: it self-corrects on the very next real
        turn's classification, so a briefly stale read is an accepted rough
        edge rather than a bug to chase.
        """
        if not self.can_regenerate():
            raise ValueError("nothing to regenerate — the last reply is no longer the most recent thing")
        cp = self._checkpoints.pop()
        self._restore_checkpoint(cp)
        return await self.turn(
            "", on_chunk, force_speaker=cp.speaker, extra_directive=guidance, on_speaker=on_speaker
        )

    def delete_from(self, turn_index: int) -> None:
        """Removes the turn_index'th reply (0-based, in the order replies
        were produced — matches transcript.entries()'s assistant turn_index)
        and everything generated after it, including any later turns and
        continuations. The other deliberate exception to append-only; see
        regenerate() above and BACKLOG.md. Callers are expected to have
        already confirmed this with the user — it's irreversible once the
        session autosaves.

        Same State caveat as regenerate(): not rolled back, self-corrects on
        the next real turn.
        """
        if not 0 <= turn_index < len(self._checkpoints):
            raise ValueError(f"no turn #{turn_index} to delete")
        cp = self._checkpoints[turn_index]
        self._restore_checkpoint(cp)
        del self._checkpoints[turn_index:]
