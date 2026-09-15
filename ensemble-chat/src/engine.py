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
from src.register import find_tics, split_bubbles, strip_speaker_prefix
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
    selector: Selector = field(init=False)
    tracker: StateTracker = field(init=False)
    system_prompt: str = field(init=False)

    def __post_init__(self) -> None:
        self.selector = Selector(self.scenario)
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
    ) -> TurnResult:
        self._sync_state()
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
        directive = speaker_directive(speaker.name)
        if extra_directive:
            directive = f"{directive} {extra_directive}"
        self.history.append({"role": "system", "content": directive})

        parts: list[str] = []
        stream = await self.client.chat.completions.create(
            model=self.cfg.model,
            messages=[{"role": "system", "content": self.system_prompt}]
            + vision.hydrate(self.history, self.attachments_dir),
            max_tokens=self.policy.reply_max_tokens,
            temperature=self.cfg.temperature,
            stream=True,
        )
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta.content
            if delta:
                parts.append(delta)
                on_chunk(delta)

        text = strip_speaker_prefix("".join(parts).strip(), speaker.name)
        if text:
            self.history.append({"role": "assistant", "content": f"{speaker.name}: {text}"})
            self.last_speaker = speaker.name

        self._schedule_state_update(speaker.name)

        return TurnResult(
            speaker=speaker,
            text=text,
            bubbles=split_bubbles(text),
            tics=find_tics(text),
        )
