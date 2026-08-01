"""
benchmark.py — Speed + quality benchmark across local GGUF models.

Runs a fixed set of tasks through each model below, times generation
(wall time + tokens/sec), then scores every response with a single fixed
judge model so speed and quality are comparable across models without
self-grading bias.

Two-pass design matters under router mode (--models-max 1): all
generation for a model happens before moving to the next model, and
judging happens in one batch at the end — this keeps model reloads to
one-per-model-plus-one-for-the-judge instead of thrashing on every task.

Usage:
    conda activate lipi
    python benchmark.py
    python benchmark.py --models gemma-12b qwen-27b
    python benchmark.py --tasks-file my_tasks.json
    python benchmark.py --out benchmarks/run1.json
"""

import argparse
import json
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import openai

from config import PROFILES
from phases import _GEN_SYSTEM, critique
from tools import get_system_date

# label -> model field sent to the server. Must match a section name in
# router-preset.ini exactly (the router routes on this id, not the
# underlying --model filename).
MODELS = {
    "gemma-12b": "gemma-12b",
    "gemma-26b": "gemma-26b",
    "gemma-31b": "gemma-31b",
    "qwen-35b":  "qwen-35b",
    "qwen-27b":  "qwen-27b",
}

TASKS = [
    "Write a Python function to check if a number is prime, with tests.",
    "Explain the difference between TCP and UDP in simple terms.",
    "Summarize the causes of the 2008 financial crisis in 200 words.",
    "Write a short story opening (150 words) about a lighthouse keeper who finds a message in a bottle.",
    "What's the best way to identify a ripe avocado?",
    "Explain how a Bloom filter works and when to use one.",
    "Write a SQL query to find the second-highest salary in an employees table.",
    "Compare REST and GraphQL for a mobile app backend.",
    "Explain photosynthesis to a 10-year-old.",
    "Draft a polite email declining a meeting invite due to a scheduling conflict.",
]

BASE_URL = PROFILES["generator"]["base_url"]
JUDGE_PROFILE = PROFILES["critic"]  # fixed judge, independent of the model under test
GEN_TEMPERATURE = 0.3
GEN_MAX_TOKENS = 1024


def _client() -> openai.OpenAI:
    return openai.OpenAI(base_url=BASE_URL, api_key="local", timeout=180)


def timed_generate(task: str, model: str) -> dict:
    client = _client()
    user = f"## Current date\n{get_system_date()}\n\n## Task\n{task}"
    t0 = time.perf_counter()
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _GEN_SYSTEM},
            {"role": "user", "content": user},
        ],
        temperature=GEN_TEMPERATURE,
        max_tokens=GEN_MAX_TOKENS,
        # keep speed comparisons apples-to-apples across thinking/non-thinking models
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )
    elapsed = time.perf_counter() - t0
    text = (resp.choices[0].message.content or "").strip()
    usage = resp.usage
    completion_tokens = usage.completion_tokens if usage else None
    tok_per_sec = completion_tokens / elapsed if completion_tokens else None
    return {
        "response": text,
        "elapsed_s": round(elapsed, 2),
        "completion_tokens": completion_tokens,
        "tokens_per_sec": round(tok_per_sec, 1) if tok_per_sec else None,
    }


def run(models: dict, tasks: list, out_path: Path) -> list:
    generations = []
    for label, model in models.items():
        print(f"\n=== Generating: {label} ({model}) ===")
        for i, task in enumerate(tasks, 1):
            print(f"  [{i}/{len(tasks)}] {task[:60]}...", end=" ", flush=True)
            gen = timed_generate(task, model)
            print(f"{gen['elapsed_s']}s, {gen['tokens_per_sec']} tok/s")
            generations.append({"label": label, "model": model, "task": task, **gen})

    print(f"\n=== Scoring all responses with judge: {JUDGE_PROFILE['model']} ===")
    for i, g in enumerate(generations, 1):
        print(f"  [{i}/{len(generations)}] {g['label']} / {g['task'][:40]}...", end=" ", flush=True)
        crit = critique(g["task"], "(direct task, no prompt scaffold)", g["response"], JUDGE_PROFILE)
        g["quality_total"] = crit["total"]
        g["quality_scores"] = crit["scores"]
        print(f"quality {crit['total']}/10")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(generations, indent=2))
    print(f"\nSaved {len(generations)} results to {out_path}")
    _summarize(generations)
    return generations


def _summarize(results: list) -> None:
    by_label = defaultdict(list)
    for r in results:
        by_label[r["label"]].append(r)

    print("\n" + "=" * 72)
    print(f"{'model':<12} {'avg_s':>8} {'avg_tok/s':>10} {'avg_quality':>12}")
    print("-" * 72)
    rows = []
    for label, rs in by_label.items():
        avg_s = sum(r["elapsed_s"] for r in rs) / len(rs)
        toks = [r["tokens_per_sec"] for r in rs if r["tokens_per_sec"]]
        avg_tps = sum(toks) / len(toks) if toks else 0.0
        avg_q = sum(r["quality_total"] for r in rs) / len(rs)
        rows.append((label, avg_s, avg_tps, avg_q))

    for label, avg_s, avg_tps, avg_q in sorted(rows, key=lambda r: r[1]):
        print(f"{label:<12} {avg_s:>8.2f} {avg_tps:>10.1f} {avg_q:>12.1f}")
    print("=" * 72)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Benchmark local models on speed + quality")
    ap.add_argument("--models", nargs="+", default=list(MODELS), choices=list(MODELS),
                     help="Labels from router-preset.ini to benchmark (default: all)")
    ap.add_argument("--tasks-file", type=Path, help="Optional JSON file with a list of task strings")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    tasks = TASKS
    if args.tasks_file:
        tasks = json.loads(args.tasks_file.read_text())

    selected = {label: MODELS[label] for label in args.models}
    out = args.out or Path("benchmarks") / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    run(selected, tasks, out)
