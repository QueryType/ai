"""Rich terminal UI for faaltoo-chat."""
from __future__ import annotations

import asyncio

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.theme import Theme

_THEME = Theme({
    "bot": "italic cyan",
    "system": "dim yellow",
    "user": "bold white",
    "title": "bold magenta",
})


class Terminal:
    def __init__(self, quiet: bool = False):
        self._quiet = quiet
        self._console = Console(theme=_THEME, highlight=False)

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

    def bot_start(self) -> None:
        self._console.print()

    def bot_chunk(self, text: str) -> None:
        self._console.print(text, style="bot", end="", highlight=False)

    def bot_end(self) -> None:
        self._console.print()
        self._console.print()

    async def prompt(self, label: str) -> str | None:
        try:
            return await asyncio.to_thread(
                Prompt.ask, f"[user]{label}[/user]", console=self._console
            )
        except (EOFError, KeyboardInterrupt):
            return None


# ---------------------------------------------------------------------------
# Dimension picker
# ---------------------------------------------------------------------------

def dimension_picker(
    preset: dict | None = None,
    ui: Terminal | None = None,
) -> dict[str, str]:
    console = ui._console if ui else Console(theme=_THEME, highlight=False)
    selections: dict[str, str] = {}

    if preset:
        selections = dict(preset)
        console.print("[system]Preset loaded:[/system]")
        from my_code.dimensions import DIMENSIONS
        for k, v in selections.items():
            label = DIMENSIONS[k]["label"]
            console.print(f"  [dim]{label}:[/dim] [bold]{v}[/bold]")
        console.print()
        return selections

    from my_code.dimensions import DIMENSIONS

    required = [(k, v) for k, v in DIMENSIONS.items() if v["required"]]
    optional = [(k, v) for k, v in DIMENSIONS.items() if not v["required"]]

    for key, dim in required:
        opts = dim["options"]
        console.print(f"\n[bold]{dim['label'].upper()}[/bold] [dim](required)[/dim]")
        for i, opt in enumerate(opts, 1):
            console.print(f"  [dim]{i}.[/dim] {opt}")
        while True:
            raw = Prompt.ask(f"  Pick 1-{len(opts)}", console=console)
            try:
                idx = int(raw.strip()) - 1
                if 0 <= idx < len(opts):
                    selections[key] = opts[idx]
                    break
            except ValueError:
                pass
            console.print(f"  [red]Enter a number between 1 and {len(opts)}[/red]")

    console.print("\n[dim]── Optional  (Enter to skip) ───────────────[/dim]")

    for key, dim in optional:
        opts = dim["options"]
        console.print(f"\n[bold]{dim['label'].upper()}[/bold]")
        for i, opt in enumerate(opts, 1):
            console.print(f"  [dim]{i}.[/dim] {opt}")
        raw = Prompt.ask(f"  Pick 1-{len(opts)} or Enter to skip", default="", console=console)
        raw = raw.strip()
        if raw:
            try:
                idx = int(raw) - 1
                if 0 <= idx < len(opts):
                    selections[key] = opts[idx]
            except ValueError:
                pass

    # Summary
    lines = [f"[dim]{DIMENSIONS[k]['label']}:[/dim] [bold]{v}[/bold]"
             for k, v in selections.items()]
    console.print()
    console.print(Panel("\n".join(lines), title="Your Persona", border_style="cyan"))
    console.print()

    return selections
