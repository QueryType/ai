#!/usr/bin/env python3
"""
loop.py — Self-improving prompt optimizer.

Usage:
  python loop.py                              # interactive mode
  python loop.py --task "..." --prompt "..."  # single-shot
  python loop.py --task-file task.txt         # task from file
  python loop.py --show SESSION_ID            # review a saved session
  python loop.py --list                       # list saved sessions

Options:
  --iterations N        Max generate→critique→refine cycles (default: config)
  --threshold N         Stop early when score >= N out of 10 (default: config)
  --gen-profile P       Generator profile name (default: generator)
  --crit-profile P      Critic profile name (default: critic)
  --ref-profile P       Refiner profile name (default: refiner)
  --search              Pre-search the web before each generate (requires TAVILY_API_KEY)
  --search-depth DEPTH  Tavily depth: basic (default) | advanced
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from config import cfg, PROFILES
from phases import generate, critique, refine

# ── ANSI helpers ──────────────────────────────────────────────────────────────

_B  = "\033[1m"
_D  = "\033[2m"
_C  = "\033[36m"
_G  = "\033[32m"
_Y  = "\033[33m"
_R  = "\033[0m"
_ER = "\033[31m"

def _h(text):  print(f"\n{_B}{text}{_R}")
def _ok(text): print(f"  {_G}✓{_R} {text}")
def _warn(text): print(f"  {_Y}⚠{_R} {text}")
def _dim(text): print(f"  {_D}{text}{_R}")
def _sep():    print(f"  {_D}{'─' * 60}{_R}")


# ── Session persistence ───────────────────────────────────────────────────────

def _session_path(sid: str) -> Path:
    cfg.sessions_dir.mkdir(parents=True, exist_ok=True)
    return cfg.sessions_dir / f"{sid}.json"


def _save_session(sid: str, data: dict):
    _session_path(sid).write_text(json.dumps(data, indent=2))


def _load_session(sid: str) -> dict | None:
    p = _session_path(sid)
    if p.exists():
        return json.loads(p.read_text())
    return None


def _new_session_id() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


# ── Display helpers ───────────────────────────────────────────────────────────

def _score_color(score: float) -> str:
    return _G if score >= 8 else (_Y if score >= 5 else _ER)


def _print_scores(scores: dict, total: float):
    for dim, score in scores.items():
        bar_len = int(score)
        bar = "█" * bar_len + "░" * (10 - bar_len)
        print(f"    {dim:<14} {_score_color(score)}{bar}{_R}  {score}/10")
    print(f"    {'TOTAL':<14} {_score_color(total)}{total:.1f}/10{_R}")


def _print_iteration_summary(history: list, best_iteration: int):
    _h("Iteration summary")
    _sep()
    dims = list(history[0]["scores"].keys())
    header = f"    {'Iter':<6}" + "".join(f"{d[:4].title():>7}" for d in dims) + f"{'Total':>8}"
    print(f"\n{header}")
    for it in history:
        marker = " *" if it["iteration"] == best_iteration else ""
        row = f"    {it['iteration']:<6}"
        for d in dims:
            score = it["scores"][d]
            row += f"{_score_color(score)}{score:>7}{_R}"
        total_color = _score_color(it["total"])
        print(f"{row}{total_color}{it['total']:>8.1f}{_R}{marker}")
    print(f"\n    {_D}* = best-scoring iteration{_R}")


def _print_iteration(i: int, result: dict):
    _h(f"Iteration {i}")
    _sep()

    print(f"\n{_B}  Prompt:{_R}")
    for line in result["prompt"].splitlines():
        print(f"    {line}")

    print(f"\n{_B}  Response:{_R}")
    for line in result["response"].splitlines():
        print(f"    {line}")

    print(f"\n{_B}  Critique:{_R}")
    _print_scores(result["scores"], result["total"])
    print(f"\n    {_D}Reasoning:{_R} {result['reasoning']}")
    if result.get("improvements"):
        print(f"\n    {_D}Improvements:{_R}")
        for imp in result["improvements"]:
            print(f"      • {imp}")


def _show_session(sid: str):
    data = _load_session(sid)
    if not data:
        print(f"Session not found: {sid}")
        sys.exit(1)

    print(f"\n{_B}Session:{_R} {sid}")
    print(f"{_B}Task:{_R} {data['task']}")
    print(f"{_B}Iterations:{_R} {len(data['history'])}")

    for i, it in enumerate(data["history"], 1):
        _print_iteration(i, it)

    best = data["best"]
    if len(data["history"]) > 1:
        _print_iteration_summary(data["history"], best["iteration"])
    _h("Best result")
    _sep()
    print(f"\n{_B}  Prompt:{_R}")
    for line in best["prompt"].splitlines():
        print(f"    {line}")
    print(f"\n{_B}  Response:{_R}")
    for line in best["response"].splitlines():
        print(f"    {line}")
    print(f"\n{_B}  Score:{_R} {_G}{best['total']:.1f}/10{_R}  (iteration {best['iteration']})")


def _list_sessions():
    cfg.sessions_dir.mkdir(parents=True, exist_ok=True)
    sessions = sorted(cfg.sessions_dir.glob("*.json"), reverse=True)
    if not sessions:
        print("No sessions found.")
        return
    print(f"\n{'Session ID':<22}  {'Score':>6}  {'Iters':>5}  Task")
    print("─" * 80)
    for p in sessions:
        try:
            d = json.loads(p.read_text())
            sid   = p.stem
            score = d.get("best", {}).get("total", 0)
            iters = len(d.get("history", []))
            task  = d.get("task", "")[:50]
            print(f"{sid:<22}  {score:>6.1f}  {iters:>5}  {task}")
        except Exception:
            print(f"{p.stem:<22}  (unreadable)")


# ── Core loop ─────────────────────────────────────────────────────────────────

def run_loop(
    task: str,
    initial_prompt: str,
    max_iterations: int,
    threshold: float,
    gen_profile: dict,
    crit_profile: dict,
    ref_profile: dict,
    search: bool = False,
    search_depth: str = "basic",
    plateau_patience: int = cfg.plateau_patience,
) -> dict:
    """
    Run the generate→critique→refine loop.
    Returns the full session dict.
    """
    sid = _new_session_id()
    history = []
    prompt = initial_prompt

    print(f"\n{_B}Session:{_R} {sid}")
    print(f"{_B}Task:{_R} {task}")
    print(f"{_B}Max iterations:{_R} {max_iterations}  {_B}Threshold:{_R} {threshold}/10  "
          f"{_B}Plateau patience:{_R} {plateau_patience}")
    if search:
        print(f"{_B}Web search:{_R} enabled ({search_depth})")
    _sep()

    # Pre-search: run once before the first iteration, reuse across all iterations.
    # Grounding context is fixed for the task — only the prompt changes each cycle.
    search_context = ""
    if search:
        from tools import web_search
        print(f"\n  {_C}▶ Searching web for task context...{_R}")
        t0 = time.time()
        search_context = web_search(task, search_depth=search_depth)
        _dim(f"Search done in {time.time()-t0:.1f}s  ({len(search_context.split())} words)")

    best_result = None
    stale_streak = 0

    for i in range(1, max_iterations + 1):
        _h(f"Iteration {i}/{max_iterations}")

        # Phase 1: Generate
        print(f"\n  {_C}▶ Generating...{_R}")
        t0 = time.time()
        response = generate(task, prompt, gen_profile, search_context=search_context)
        _dim(f"Generated in {time.time()-t0:.1f}s  ({len(response.split())} words)")
        print(f"\n  {_B}Prompt used:{_R}")
        for line in prompt.splitlines():
            print(f"    {line}")
        print(f"\n  {_B}Response:{_R}")
        for line in response.splitlines():
            print(f"    {line}")

        # Phase 2: Critique
        print(f"\n  {_C}▶ Critiquing...{_R}")
        t0 = time.time()
        crit = critique(task, prompt, response, crit_profile)
        _dim(f"Critiqued in {time.time()-t0:.1f}s")

        _print_scores(crit["scores"], crit["total"])
        print(f"\n    {_D}Reasoning:{_R} {crit['reasoning']}")
        if crit.get("improvements"):
            print(f"\n    {_D}Improvements:{_R}")
            for imp in crit["improvements"]:
                print(f"      • {imp}")

        iteration_record = {
            "iteration":    i,
            "prompt":       prompt,
            "response":     response,
            "scores":       crit["scores"],
            "total":        crit["total"],
            "reasoning":    crit["reasoning"],
            "improvements": crit["improvements"],
        }
        history.append(iteration_record)

        if best_result is None or crit["total"] > best_result["total"]:
            best_result = iteration_record
            stale_streak = 0
        else:
            stale_streak += 1

        # Early stop
        if crit["total"] >= threshold:
            _ok(f"Score {crit['total']:.1f} ≥ threshold {threshold} — stopping early")
            break

        if stale_streak >= plateau_patience:
            _warn(f"Score plateaued for {stale_streak} iterations — stopping early")
            break

        if i == max_iterations:
            _warn(f"Reached max iterations ({max_iterations})")
            break

        # Phase 3: Refine
        print(f"\n  {_C}▶ Refining prompt...{_R}")
        t0 = time.time()
        new_prompt = refine(task, prompt, response, crit, ref_profile)
        _dim(f"Refined in {time.time()-t0:.1f}s")

        if new_prompt.strip() == prompt.strip():
            _warn("Refiner returned the same prompt — stopping")
            break

        prompt = new_prompt

    # Final summary
    if len(history) > 1:
        _print_iteration_summary(history, best_result["iteration"])
    _h("Best result")
    _sep()
    print(f"\n{_B}  Prompt:{_R}")
    for line in best_result["prompt"].splitlines():
        print(f"    {line}")
    print(f"\n{_B}  Response:{_R}")
    for line in best_result["response"].splitlines():
        print(f"    {line}")
    print(f"\n{_B}  Score:{_R} {_G}{best_result['total']:.1f}/10{_R}  (iteration {best_result['iteration']})")

    session = {
        "session_id": sid,
        "task":       task,
        "history":    history,
        "best":       best_result,
    }
    _save_session(sid, session)
    _ok(f"Session saved → sessions/{sid}.json")
    return session


# ── CLI ───────────────────────────────────────────────────────────────────────

def _prompt_multiline(label: str) -> str:
    print(f"{label} (end with a blank line):")
    lines = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line == "" and lines and lines[-1] == "":
            break
        lines.append(line)
    return "\n".join(lines).strip()


def main():
    ap = argparse.ArgumentParser(description="Self-improving prompt optimizer")
    ap.add_argument("--task",         help="Task description")
    ap.add_argument("--prompt",       help="Initial prompt")
    ap.add_argument("--task-file",    help="Load task from text file")
    ap.add_argument("--show",         metavar="SESSION_ID", help="Show a saved session")
    ap.add_argument("--list",         action="store_true",  help="List saved sessions")
    ap.add_argument("--iterations",   type=int,   default=cfg.max_iterations)
    ap.add_argument("--threshold",    type=float, default=cfg.score_threshold)
    ap.add_argument("--plateau-patience", type=int, default=cfg.plateau_patience,
                    help="Stop early after this many consecutive iterations with no score improvement")
    ap.add_argument("--gen-profile",   default="generator")
    ap.add_argument("--crit-profile",  default="critic")
    ap.add_argument("--ref-profile",   default="refiner")
    ap.add_argument("--search",        action="store_true",
                    help="Pre-search web for task context via Tavily (requires TAVILY_API_KEY)")
    ap.add_argument("--search-depth",  default="basic", choices=["basic", "advanced"],
                    help="Tavily search depth: basic (1 credit) or advanced (2 credits)")
    args = ap.parse_args()

    if args.list:
        _list_sessions()
        return

    if args.show:
        _show_session(args.show)
        return

    # Resolve profiles
    for name in (args.gen_profile, args.crit_profile, args.ref_profile):
        if name not in PROFILES:
            print(f"Unknown profile '{name}'. Available: {list(PROFILES)}")
            sys.exit(1)

    gen_profile  = PROFILES[args.gen_profile]
    crit_profile = PROFILES[args.crit_profile]
    ref_profile  = PROFILES[args.ref_profile]

    # Resolve task
    if args.task_file:
        task = Path(args.task_file).read_text().strip()
    elif args.task:
        task = args.task
    else:
        task = _prompt_multiline("\nTask")

    if not task:
        print("No task provided.")
        sys.exit(1)

    # Resolve initial prompt
    if args.prompt:
        initial_prompt = args.prompt
    else:
        print("\nInitial prompt (press Enter for a generic default):")
        initial_prompt = input().strip()
        if not initial_prompt:
            initial_prompt = "Answer the following task thoroughly and accurately."

    run_loop(
        task=task,
        initial_prompt=initial_prompt,
        max_iterations=args.iterations,
        threshold=args.threshold,
        gen_profile=gen_profile,
        crit_profile=crit_profile,
        ref_profile=ref_profile,
        search=args.search,
        search_depth=args.search_depth,
        plateau_patience=args.plateau_patience,
    )


if __name__ == "__main__":
    main()
