from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable

from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout
from rich.console import Console
from rich.text import Text

from src.cast import Character
from src.engine import Engine, TurnResult
from src.transcript import entries as transcript_entries

_COLORS = ("cyan", "magenta", "green", "yellow", "blue")


class StreamPrinter:
    """Prints an F2F reply as it streams instead of revealing it all at once.

    F2F is a single screenplay block (see register.f2f_block), so raw deltas
    map straight onto it — no bubble-boundary reconciliation needed, unlike
    texting mode's multi-bubble split.
    """

    def __init__(self, console: Console, colors: dict[str, str], pad: int) -> None:
        self.console = console
        self.colors = colors
        self.pad = pad

    def on_speaker(self, character: Character) -> None:
        color = self.colors.get(character.name, "white")
        self.console.print(
            f"{character.name:<{self.pad}}  ", end="", style=f"bold {color}", highlight=False
        )

    def on_chunk(self, delta: str) -> None:
        self.console.print(delta, end="", markup=False, highlight=False)

    def finish(self) -> None:
        self.console.print()


class Terminal:
    def __init__(self, engine: Engine) -> None:
        self.console = Console()
        self.engine = engine
        self.colors = {
            c.name: _COLORS[i % len(_COLORS)]
            for i, c in enumerate(engine.scenario.characters)
        }
        self.pad = max(len(c.name) for c in engine.scenario.characters)
        self.session: PromptSession = PromptSession()

    def banner(self) -> None:
        scenario, policy = self.engine.scenario, self.engine.policy
        names = ", ".join(c.name for c in scenario.characters)
        self.console.print(f"[bold]{scenario.title}[/bold]  ·  {names}", highlight=False)
        tuning = "probed" if policy.probed else "UNPROBED — run: python -m src.probe"
        self.console.print(
            f"[dim]{self.engine.cfg.model} · reply≤{policy.reply_max_tokens}tok · {tuning}[/dim]"
        )
        commands = "/next <name> · /who · /state · /log · /regenerate [guidance] · /delete <n>"
        if policy.vision_capable:
            commands += " · /image <path> [caption]"
        self.console.print(f"[dim]{commands} · /quit[/dim]\n")

    async def pause_for_continuation(self) -> None:
        """A beat longer than the inter-bubble pause, so it reads as someone
        else picking up the thread rather than another bubble of the same reply."""
        await asyncio.sleep(1.1)

    def begin_stream(self) -> StreamPrinter:
        return StreamPrinter(self.console, self.colors, self.pad)

    def show_human(self, text: str) -> None:
        """Echo a generated "you" line — self-auto mode (src/autopilot.py)
        has no real stdin for the terminal to echo, unlike interactive typing."""
        self.console.print(f"[bold]{'you':<{self.pad}}[/bold]  {text}")

    def show_warnings(self, result: TurnResult) -> None:
        if result.tics:
            self.console.print(f"[dim red]{'':<{self.pad}}  ⚠ {', '.join(result.tics)}[/dim red]")
        if result.truncated:
            self.console.print(
                f"[dim red]{'':<{self.pad}}  ⚠ cut off at max_tokens, trimmed to last full sentence[/dim red]"
            )

    async def show(self, result: TurnResult) -> None:
        color = self.colors.get(result.speaker.name, "white")
        for i, bubble in enumerate(result.bubbles):
            if i:
                await asyncio.sleep(min(0.9, 0.25 + len(bubble) / 220))
            label = result.speaker.name if i == 0 else ""
            line = Text()
            line.append(f"{label:<{self.pad}}  ", style=f"bold {color}")
            line.append(bubble)
            self.console.print(line)
        self.show_warnings(result)
        self.console.print()

    def show_state(self) -> None:
        state = self.engine.state
        affect = state.affect
        self.console.print(
            f"[dim]mood {affect.mood} · energy {affect.energy} · closeness {affect.closeness}[/dim]"
        )
        for thread in state.threads:
            self.console.print(f"[dim]  thread  {thread.topic} ({thread.status})[/dim]")
        for trait in state.traits:
            self.console.print(f"[dim]  trait   {trait}[/dim]")
        for promise in state.promises:
            when = "done" if promise.fulfilled else time.strftime("%d %b %H:%M", time.localtime(promise.due))
            self.console.print(f"[dim]  promise {promise.text} — {promise.speaker or '?'}, {when}[/dim]")
        if not (state.threads or state.traits or state.promises):
            self.console.print("[dim]  nothing tracked yet[/dim]")
        self.console.print()

    def show_log(self) -> None:
        """Replay the full session: only user/assistant lines, not the
        internal speaker directives or state blocks appended between them.
        Assistant lines are tagged with their turn number — see
        `/delete <n>`, which addresses replies by this same number."""
        for entry in transcript_entries(self.engine.history):
            if entry.role == "user":
                suffix = f" [dim]\\[image: {entry.image_path}][/dim]" if entry.image_path else ""
                self.console.print(f"[bold]{'you':<{self.pad}}[/bold]  {entry.text}{suffix}")
            else:
                color = self.colors.get(entry.speaker, "white")
                tag = f"[dim]#{entry.turn_index}[/dim] "
                self.console.print(f"{tag}[bold {color}]{entry.speaker:<{self.pad}}[/bold {color}]  {entry.text}")
        self.console.print()

    async def ask(
        self,
        on_idle: Callable[[], Awaitable[None]] | None = None,
        idle_seconds: float = 0.0,
    ) -> str:
        """Block for input, but if `on_idle` is given and idle_seconds > 0,
        call it (repeatedly) instead of just sitting there once that much time
        passes with nothing typed. `patch_stdout` keeps whatever `on_idle`
        prints from corrupting the in-progress input line."""
        with patch_stdout():
            task: asyncio.Task[str] = asyncio.ensure_future(
                self.session.prompt_async(f"{'you':<{self.pad}}  ")
            )
            while True:
                timeout = idle_seconds if (on_idle and idle_seconds > 0) else None
                done, _ = await asyncio.wait({task}, timeout=timeout)
                if task in done:
                    return task.result()
                await on_idle()
