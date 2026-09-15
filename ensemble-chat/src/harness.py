"""Scripted evaluation runs.

The human side is a fixed script, not a model. That is deliberate. A scripted
human makes score changes reflect changes to the engine rather than variance in
a simulated user, and it removes any chance of the contamination in
`faaltoo-chat`, where the simulated human is primed with the bot's own persona
and both sides end up sounding alike.

Replies still vary run to run at temperature 0.9, so read a single composite as
approximate — a 2-3 point move is noise, a 10 point move is real.

Evaluation never touches a saved session: the engine is built with empty history
and nothing is written unless you pass --save.
"""
from __future__ import annotations

import argparse
import asyncio
import random
import tempfile
import time
from dataclasses import dataclass, replace
from pathlib import Path

from rich.console import Console
from rich.table import Table

from src.cast import load_scenario, resolve_scenario
from src.config import load_config
from src.continuation import decide
from src.engine import Engine, TurnResult
from src.metrics import Turn, evaluate
from src.policy import load_policy
from src.provider import get_client
from src.vision import synthetic_png

@dataclass(frozen=True)
class Suite:
    name: str
    script: list[str]
    # What the script deliberately puts in front of the memory layer. None means
    # the run is too short to fairly demand anything.
    expect: dict[str, int] | None = None
    # script index -> image bytes to attach on that turn. Requires a
    # vision-capable model; run_suite skips the suite with a clear message
    # rather than failing if the configured model doesn't support it.
    images: dict[int, bytes] | None = None


SHORT_SCRIPT = [
    "anyone up",
    "cant sleep again",
    "priya did you actually quit or was that a bit",
    "work has been rough honestly",
    "im gonna try to sleep. night",
]

LONG_SCRIPT = [
    "anyone up",
    "cant sleep. brain wont shut up",
    "work has been a nightmare this week honestly",
    "priya how do you deal with a manager who cc's your skip on everything",
    "ha. i wish i had that kind of spine",
    "anyway. enough about that",
    "dev did you ever finish that thing you were building",
    "that sounds genuinely exhausting",
    "i think i might be burning out for real this time",
    "not sleeping, not eating properly, the usual",
    "meera you've gone quiet",
    "thats fair",
    "my sister's wedding is in three weeks and i havent booked anything",
    "i know i know",
    "will one of you remind me to book the flights this week",
    "ok good",
    "changing the subject entirely, has anyone watched anything decent lately",
    "i cant handle anything with subtitles right now, my brain is soup",
    "priya you always recommend things nobody else likes",
    "lol fair",
    "i should sleep",
    "one more thing",
    "do you think i should actually quit or am i just tired",
    "ok. thanks. genuinely",
]

VISION_SCRIPT = [
    "anyone up? bored out of my mind",
    "ok random but check this out",
    "anyway hows everyone doing",
    "yeah fair enough, same tbh",
    "ok random one -- what color was that pic i sent earlier?",
]

SUITES = {
    "short": Suite("short", SHORT_SCRIPT),
    # Only assert what the script itself guarantees as input. Turns 9-10 describe
    # not eating or sleeping, and several turns open topics that go unresolved —
    # both are the human's own words, so the memory layer has no excuse.
    # Promises are deliberately NOT asserted: turn 15 asks for a reminder, but a
    # character is free to refuse (Priya does, often), so a missing promise says
    # nothing about whether memory works. The count is still reported.
    "long": Suite("long", LONG_SCRIPT, expect={"traits": 1, "threads": 2}),
    # An image attached on turn 2, referred back to on turn 5 — three turns and
    # two unrelated replies later. Exercises hydrate() persisting real image
    # content across turns, not just the one right after it (see DESIGN.md's
    # "Vision" section — that persistence is the whole point of the
    # reference+hydrate design over describe-once-and-discard). Whether a
    # character *correctly* recalls the color isn't asserted — that needs the
    # model's cooperation, same reasoning as promises above — read the
    # transcript for that; run_suite does assert the reference mechanically
    # survived in history.
    "vision": Suite("vision", VISION_SCRIPT, images={1: synthetic_png((230, 120, 20))}),
}


def _print_turn(console: Console, result: TurnResult, elapsed: float) -> None:
    for i, bubble in enumerate(result.bubbles):
        label = result.speaker.name if i == 0 else ""
        console.print(f"[cyan]{label:<8}[/cyan] {bubble}")
    console.print(f"[dim]{'':<8} {elapsed:.1f}s[/dim]")


async def run_suite(
    name: str, scenario_arg: str | None, console: Console, continuations: bool
) -> tuple[str, float | None]:
    suite = SUITES[name]
    script = suite.script
    cfg = load_config()
    # Suites default to continuations off so scores stay comparable run to run;
    # --continuations exercises the feature separately, where more variance is
    # expected. See PLAN_CONTINUATIONS.md.
    if not continuations:
        cfg = replace(cfg, continuation_max=0)
    scenario_path = resolve_scenario(cfg, scenario_arg)
    scenario = load_scenario(scenario_path)
    policy = load_policy(cfg)

    if suite.images and not policy.vision_capable:
        console.print(
            f"[yellow]skipping {name}: {cfg.model} isn't vision-capable "
            f"(or hasn't been probed — run python -m src.probe)[/yellow]\n"
        )
        return name, None

    rng = random.Random()

    console.rule(f"[bold]{scenario.title} · {name} · {len(script)} turns[/bold]")
    console.print(f"[dim]{cfg.model} · reply≤{policy.reply_max_tokens}tok · "
                  f"{'probed' if policy.probed else 'UNPROBED'}"
                  f"{' · continuations on' if continuations else ''}[/dim]\n")

    # A real attachments_dir even for suites with no images — Engine defaults
    # to Path(".") otherwise, which would litter the repo root with .jpg
    # files the moment a suite does attach one. Cleaned up on exit; nothing
    # here should outlive the run, same as the rest of the harness.
    with tempfile.TemporaryDirectory(prefix="ensemble-chat-harness-") as tmp_dir:
        engine = Engine(
            scenario=scenario,
            cfg=cfg,
            policy=policy,
            client=get_client(cfg),
            attachments_dir=Path(tmp_dir),
        )

        turns: list[Turn] = []
        for i, line in enumerate(script):
            image = (suite.images or {}).get(i)
            console.print(f"[bold]you[/bold]      {line}{'  [dim](+ image)[/dim]' if image else ''}")
            started = time.perf_counter()
            result = await engine.turn(line, lambda _: None, image=image)
            elapsed = time.perf_counter() - started
            _print_turn(console, result, elapsed)
            turns.append(Turn(speaker=result.speaker.name, text=result.text, elapsed=elapsed))

            depth = 0
            while True:
                cont = decide(scenario, result, depth, cfg, rng)
                if cont is None:
                    break
                started = time.perf_counter()
                result = await engine.turn(
                    "", lambda _: None, force_speaker=cont.speaker, extra_directive=cont.directive
                )
                elapsed = time.perf_counter() - started
                _print_turn(console, result, elapsed)
                turns.append(Turn(speaker=result.speaker.name, text=result.text, elapsed=elapsed))
                depth += 1

        await engine.drain()

        if suite.images:
            surviving = sum(
                1 for m in engine.history
                if m["role"] == "user" and isinstance(m["content"], list)
                and any(p.get("type") == "image_ref" for p in m["content"])
            )
            expected = len(suite.images)
            colour = "green" if surviving == expected else "red"
            console.print(
                f"[{colour}]image reference persisted in history: "
                f"{surviving}/{expected}[/{colour}]\n"
            )

    metrics, composite = evaluate(turns, list(scenario.characters), engine.state, suite.expect)

    table = Table(show_edge=False, pad_edge=False, box=None)
    table.add_column("metric", style="bold")
    table.add_column("score", justify="right")
    table.add_column("wt", justify="right", style="dim")
    table.add_column("detail", style="dim")
    for m in metrics:
        if not m.applicable:
            table.add_row(m.name, "[dim]n/a[/dim]", "[dim]—[/dim]", m.detail)
            continue
        colour = "green" if m.score >= 0.8 else "yellow" if m.score >= 0.5 else "red"
        table.add_row(m.name, f"[{colour}]{m.score:.2f}[/{colour}]", f"{m.weight:g}", m.detail)

    console.print()
    console.print(table)
    mean_latency = sum(t.elapsed for t in turns) / len(turns)
    console.print(
        f"\n[bold]composite {composite:.1f}/100[/bold]  "
        f"[dim]mean turn {mean_latency:.1f}s[/dim]"
    )
    if engine.state_error:
        console.print(f"[red]state error: {engine.state_error}[/red]")
    console.print()

    return name, composite


async def run(
    names: list[str], scenario_arg: str | None, save: Path | None, continuations: bool
) -> None:
    console = Console(record=save is not None)
    results = [await run_suite(n, scenario_arg, console, continuations) for n in names]

    if len(results) > 1:
        console.rule("[bold]summary[/bold]")
        for name, score in results:
            console.print(f"  {name:<6} {'skipped' if score is None else f'{score:5.1f}/100'}")
        console.print()

    if save:
        save.parent.mkdir(parents=True, exist_ok=True)
        save.write_text(console.export_text(), encoding="utf-8")
        console.print(f"[dim]written -> {save}[/dim]")


def main() -> None:
    parser = argparse.ArgumentParser(prog="ensemble-chat eval")
    parser.add_argument("suite", nargs="?", default="all", choices=["short", "long", "vision", "all"])
    parser.add_argument("--scenario", help="name under SCENARIO_LOC, or a path")
    parser.add_argument("--save", type=Path, help="write the report to a file")
    parser.add_argument(
        "--continuations", action="store_true", help="exercise continuation turns (more variance)"
    )
    args = parser.parse_args()

    names = ["short", "long"] if args.suite == "all" else [args.suite]
    try:
        asyncio.run(run(names, args.scenario, args.save, args.continuations))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
