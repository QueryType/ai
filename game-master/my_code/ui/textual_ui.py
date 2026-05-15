"""Textual TUI for the game-master adventure engine.

Optional UI mode — launched with --ui tui.  Implements the same interface
as Terminal so game_loop.py requires zero changes beyond the await calls
already in place.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Input, RichLog, Rule, Static
from rich.text import Text

if TYPE_CHECKING:
    from my_code.models.data_models import AdventureScene, GameState


_COMMANDS = ["/save", "/load", "/export", "/memory", "/note", "/mode", "/help", "/quit"]

_CSS = """
Screen {
    layout: vertical;
    background: $surface;
}

#title-bar {
    height: 3;
    background: $panel-darken-2;
    content-align: center middle;
    text-style: bold;
    color: $primary;
    border-bottom: solid $primary-darken-2;
}

#main {
    layout: horizontal;
    height: 1fr;
}

#story-area {
    width: 70%;
    layout: vertical;
}

#story-log {
    height: 1fr;
    padding: 0 1;
    border-right: solid $panel;
}

#streaming-area {
    width: 70%;
    height: auto;
    min-height: 0;
    max-height: 40%;
    padding: 0 1;
    color: $accent;
    text-style: italic;
    border-top: solid $panel-darken-2;
    border-right: solid $panel;
    background: $surface;
}


#sidebar {
    width: 30%;
    layout: vertical;
    padding: 1 1;
    background: $panel-darken-1;
    overflow-y: auto;
}

.sidebar-heading {
    color: $primary;
    text-style: bold;
}

.sidebar-body {
    color: $text-muted;
    padding: 0 0 1 0;
}

#meta-bar {
    height: 1;
    layout: horizontal;
    background: $panel-darken-2;
    padding: 0 1;
    border-top: solid $panel;
}

#turn-label {
    width: auto;
    color: $text-muted;
    margin-right: 2;
}

#meta-mode-label {
    width: auto;
    color: $warning;
}

#hints-bar {
    height: 1;
    background: $panel;
    padding: 0 1;
    color: $text-muted;
    border-top: solid $panel-darken-2;
}

#input-row {
    height: 3;
    layout: horizontal;
    align: left middle;
    border-top: solid $panel;
    padding: 0 1;
}

#prompt-label {
    width: auto;
    content-align: left middle;
    color: $primary;
    text-style: bold;
    padding: 0 1 0 0;
    margin-top: 1;
}

#game-input {
    width: 1fr;
    border: none;
    background: $surface;
}

#game-input:focus {
    border: none;
}
"""


class _GameApp(App):
    """Textual application shell — runs run_adventure as an async worker."""

    CSS = _CSS
    BINDINGS = [Binding("ctrl+c", "request_quit", "Quit", show=False)]

    def __init__(self, scene: AdventureScene, tui: TextualUI) -> None:
        super().__init__()
        self._scene = scene
        self._tui = tui

    def compose(self) -> ComposeResult:
        yield Static(self._scene.meta.title, id="title-bar")
        with Horizontal(id="main"):
            with Vertical(id="story-area"):
                yield RichLog(id="story-log", highlight=False, markup=False, wrap=True)
            with Vertical(id="sidebar"):
                yield Static("MEMORY", classes="sidebar-heading")
                yield Static("", id="memory-content", classes="sidebar-body")
                yield Rule()
                yield Static("AUTHOR'S NOTE", classes="sidebar-heading")
                yield Static("", id="note-content", classes="sidebar-body")
                yield Rule()
        yield Static("", id="streaming-area")
        with Horizontal(id="meta-bar"):
            yield Static("Turn: 0", id="turn-label")
            yield Static("Mode: ACTION", id="meta-mode-label")
        yield Static("", id="hints-bar")
        with Horizontal(id="input-row"):
            yield Static("[ACTION]", id="prompt-label")
            yield Input(placeholder="enter your action...", id="game-input")

    def on_mount(self) -> None:
        self.query_one("#game-input", Input).focus()
        self.query_one("#hints-bar", Static).display = False
        self.query_one("#streaming-area", Static).display = False
        self._tui._set_app(self)
        self.run_worker(self._run_game(), exclusive=True)

    async def _run_game(self) -> None:
        from my_code.game_loop import run_adventure
        await run_adventure(self._scene, self._tui)
        self.exit()

    def on_input_changed(self, event: Input.Changed) -> None:
        value = event.value
        hints_bar = self.query_one("#hints-bar", Static)
        if value.startswith("/"):
            prefix = value.lower()
            matches = [c for c in _COMMANDS if c.startswith(prefix)]
            if matches:
                hints_bar.update("  ".join(matches))
                hints_bar.display = True
            else:
                hints_bar.display = False
        else:
            hints_bar.display = False

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        value = event.value.strip()
        event.input.clear()
        self.query_one("#hints-bar", Static).display = False
        await self._tui._input_queue.put(value)

    async def action_request_quit(self) -> None:
        await self._tui._input_queue.put("/quit")


# ---------------------------------------------------------------------------
# TextualUI — public interface
# ---------------------------------------------------------------------------

class TextualUI:
    """Textual TUI implementing the same interface as Terminal."""

    def __init__(self) -> None:
        self._app: _GameApp | None = None
        self._input_queue: asyncio.Queue[str] = asyncio.Queue()
        self._stream_buffer: list[str] = []
        self._update_pending: bool = False
        self.last_streamed: str = ""

    def _set_app(self, app: _GameApp) -> None:
        self._app = app

    def run(self, scene: AdventureScene) -> None:
        """Create and run the Textual app. Blocks until the game exits."""
        _GameApp(scene, self).run()

    # ------------------------------------------------------------------
    # Structural output
    # ------------------------------------------------------------------

    def banner(self, title: str) -> None:
        if self._app:
            self._app.query_one("#title-bar", Static).update(title)

    def panel(self, content: str, title: str = "") -> None:
        if not self._app:
            return
        log = self._app.query_one("#story-log", RichLog)
        if title:
            log.write(Text(f"── {title} ──", style="bold cyan"))
        log.write(Text(content))
        log.write(Text(""))

    def system(self, message: str) -> None:
        if not self._app:
            return
        self._app.query_one("#story-log", RichLog).write(
            Text.from_markup(f"[dim yellow]✦ {message}[/dim yellow]")
        )

    # ------------------------------------------------------------------
    # GM streaming output
    # ------------------------------------------------------------------

    def gm_start(self) -> None:
        self._stream_buffer = []
        self._update_pending = False
        if self._app:
            self._app.call_later(self._show_streaming)

    def _show_streaming(self) -> None:
        if self._app:
            area = self._app.query_one("#streaming-area", Static)
            area.update("")
            area.display = True

    def gm_chunk(self, text: str) -> None:
        self._stream_buffer.append(text)
        if not self._update_pending and self._app:
            self._update_pending = True
            self._app.call_later(self._flush_streaming)

    def _flush_streaming(self) -> None:
        self._update_pending = False
        if self._app:
            self._app.query_one("#streaming-area", Static).update(
                Text("".join(self._stream_buffer), style="italic cyan")
            )

    def gm_end(self) -> None:
        full = "".join(self._stream_buffer)
        self.last_streamed = full
        if self._app:
            self._app.call_later(self._finalise_stream, full)

    def _finalise_stream(self, full: str) -> None:
        if not self._app:
            return
        log = self._app.query_one("#story-log", RichLog)
        log.write(Text(full, style="italic cyan"))
        log.write(Text(""))
        area = self._app.query_one("#streaming-area", Static)
        area.update("")
        area.display = False

    def gm_stream_text(self, text: str) -> None:
        """Display pre-written text (used for opening narration)."""
        self.last_streamed = text
        if not self._app:
            return
        log = self._app.query_one("#story-log", RichLog)
        log.write(Text(text, style="italic cyan"))
        log.write(Text(""))

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------

    async def prompt(self, label: str) -> str | None:
        if self._app:
            self._app.call_later(self._update_prompt_label, label)
        try:
            return await self._input_queue.get()
        except asyncio.CancelledError:
            return None

    def _update_prompt_label(self, label: str) -> None:
        if self._app:
            self._app.query_one("#prompt-label", Static).update(label)

    async def confirm(self, message: str) -> bool:
        self.system(f"{message}  (type y to confirm)")
        if self._app:
            self._app.call_later(self._update_prompt_label, "[y/N]")
        try:
            value = await self._input_queue.get()
            return value.lower().strip() in ("y", "yes")
        except asyncio.CancelledError:
            return False

    # ------------------------------------------------------------------
    # Sidebar
    # ------------------------------------------------------------------

    def refresh_sidebar(self, state: GameState) -> None:
        if self._app:
            self._app.call_later(self._do_refresh_sidebar, state)

    def _do_refresh_sidebar(self, state: GameState) -> None:
        if not self._app:
            return
        self._app.query_one("#memory-content", Static).update(state.memory or "(empty)")
        self._app.query_one("#note-content", Static).update(state.author_note or "(empty)")
        self._app.query_one("#turn-label", Static).update(f"Turn: {state.turn_count}")
        self._app.query_one("#meta-mode-label", Static).update(
            f"Mode: {state.input_mode.upper()}"
        )

    # ------------------------------------------------------------------
    # Null variant (for silent checkpoint saves)
    # ------------------------------------------------------------------

    @classmethod
    def _null(cls) -> "_NullTextualUI":
        return _NullTextualUI()


class _NullTextualUI(TextualUI):
    """Silent TextualUI — discards all output (used for checkpoint saves)."""

    def banner(self, title: str) -> None: pass
    def panel(self, content: str, title: str = "") -> None: pass
    def system(self, message: str) -> None: pass
    def gm_start(self) -> None: self._stream_buffer = []
    def gm_chunk(self, text: str) -> None: self._stream_buffer.append(text)
    def gm_end(self) -> None: pass
    def gm_stream_text(self, text: str) -> None: pass
    async def prompt(self, label: str) -> str | None: return None
    async def confirm(self, message: str) -> bool: return False
    def refresh_sidebar(self, state: GameState) -> None: pass
