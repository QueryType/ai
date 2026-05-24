"""Rich terminal UI for the game-master adventure engine."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.text import Text
from rich.theme import Theme

if TYPE_CHECKING:
    from my_code.models.data_models import GameState


_THEME = Theme({
    "gm": "italic cyan",
    "system": "dim yellow",
    "player": "bold white",
    "title": "bold magenta",
})


class Terminal:
    """Wraps Rich console for all game-master UI operations."""

    def __init__(self, quiet: bool = False):
        self._quiet = quiet
        self._console = Console(theme=_THEME, highlight=False)
        self.last_streamed: str = ""

    # ------------------------------------------------------------------
    # Structural output
    # ------------------------------------------------------------------

    def banner(self, title: str) -> None:
        self._console.print()
        self._console.print(Panel(
            f"[title]{title}[/title]",
            border_style="magenta",
            padding=(1, 4),
        ))
        self._console.print()

    def panel(self, content: str, title: str = "") -> None:
        self._console.print(Panel(content, title=title, border_style="dim cyan"))

    def system(self, message: str) -> None:
        if not self._quiet:
            self._console.print(f"[system]{message}[/system]")

    # ------------------------------------------------------------------
    # GM streaming output
    # ------------------------------------------------------------------

    def gm_start(self) -> None:
        self._console.print()

    def gm_chunk(self, text: str) -> None:
        self._console.print(text, style="gm", end="", highlight=False)

    def gm_end(self) -> None:
        self._console.print()
        self._console.print()

    def gm_stream_text(self, text: str) -> None:
        """Display pre-written text as if streamed (used for opening narration)."""
        self.last_streamed = text
        self._console.print()
        self._console.print(Text(text, style="gm"))
        self._console.print()

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------

    async def prompt(self, label: str) -> str | None:
        """Read player input. Returns None on EOF/Ctrl-D."""
        try:
            return await asyncio.to_thread(
                Prompt.ask, f"[player]{label}[/player]", console=self._console
            )
        except (EOFError, KeyboardInterrupt):
            return None

    async def confirm(self, message: str) -> bool:
        try:
            return await asyncio.to_thread(
                Confirm.ask, message, console=self._console, default=False
            )
        except (EOFError, KeyboardInterrupt):
            return False

    def refresh_sidebar(self, state: GameState) -> None:
        pass  # no-op — terminal has no sidebar

    # ------------------------------------------------------------------
    # Null terminal (for silent operations like checkpoint saves)
    # ------------------------------------------------------------------

    @classmethod
    def _null(cls) -> "_NullTerminal":
        return _NullTerminal()


class _NullTerminal(Terminal):
    """Silent terminal that discards all output."""

    def __init__(self):
        self._quiet = True
        self._console = Console(file=open("/dev/null", "w"), highlight=False)
        self.last_streamed = ""

    def system(self, message: str) -> None:
        pass

    def gm_start(self) -> None:
        pass

    def gm_chunk(self, text: str) -> None:
        pass

    def gm_end(self) -> None:
        pass

    async def prompt(self, label: str) -> str | None:
        return None

    async def confirm(self, message: str) -> bool:
        return False
