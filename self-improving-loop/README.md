# Self-Improving Loop

A local, self-hosted prompt optimizer: given a task and a starting prompt, it runs a **generate → critique → refine** loop against local LLMs (via `llama-server`) until the response scores well on a configurable rubric — no cloud APIs, no test-case datasets, just an LLM critic judging another LLM's output and rewriting the prompt to fix what's weak.

Also includes a **speed + quality benchmark harness** (`benchmark.py`) for comparing local GGUF models on the same tasks, so you can pick which model to use for which role (fast generator vs. strong critic) based on real numbers from your own hardware.

---

## Why this exists

Most "prompt engineering" is manual trial and error: write a prompt, run it, eyeball the output, tweak, repeat. This project automates that loop:

1. A **generator** model produces a response to a task using the current prompt.
2. A **critic** model scores the response 0–10 on each rubric dimension (accuracy, completeness, clarity, depth, relevance by default) and explains what's wrong.
3. A **refiner** model rewrites the prompt to address the critic's specific feedback.
4. Repeat with the improved prompt until the score clears a threshold, plateaus, or the iteration budget runs out.

Everything runs against local models over an OpenAI-compatible endpoint — the loop doesn't care whether generator/critic/refiner are the same model or three different ones, or whether they're served from one `llama-server` process or several.

---

## How it works

```
 ┌─────────────────────────────────────────────────────┐
 │  Task + Initial Prompt                              │
 └────────────────────┬────────────────────────────────┘
                      │
         ┌────────────▼────────────┐
         │   1. GENERATE           │  fast model (gemma-12b)
         │   task + prompt → LLM   │
         └────────────┬────────────┘
                      │ response
         ┌────────────▼────────────┐
         │   2. CRITIQUE           │  smart model (gemma-26b / qwen)
         │   score rubric 0-10     │  returns JSON: scores + reasoning
         │   per dimension         │  + 3 specific improvements
         └────────────┬────────────┘
                      │
              score ≥ threshold?
              YES → stop, save best
              score plateaued (N iters, no gain)?
              YES → stop, save best
                      │ NO
         ┌────────────▼────────────┐
         │   3. REFINE             │  smart model (same as critic)
         │   rewrite prompt using  │
         │   critic feedback       │
         └────────────┬────────────┘
                      │ improved prompt
                      └──────────── loop back to 1
```

The real system date is injected into every generate, critique, and refine call (via `tools.get_system_date()`) so the critic judges date-related claims against the actual current date instead of its own training-data assumptions about "today."

Rubric dimensions (configurable in `config.yaml`):

| Dimension    | What it measures                             |
|-------------|----------------------------------------------|
| accuracy    | Factual correctness and logical soundness     |
| completeness| All aspects of the task addressed             |
| clarity     | Well-structured, readable, no jargon          |
| depth       | Genuine analysis, not surface-level           |
| relevance   | On-task, no padding or tangents               |

---

## Quick start

```bash
conda activate lipi          # or any env with openai + pyyaml

# Interactive — asks for task and prompt
python loop.py

# Fully specified
python loop.py \
  --task "Explain the causes of the 2008 financial crisis" \
  --prompt "Answer the following task thoroughly and accurately."

# Task from a file, 8 iterations, stop at score 9.0
python loop.py --task-file my_task.txt --iterations 8 --threshold 9.0

# Review past runs
python loop.py --list
python loop.py --show 20260704_143022
```

---

## llama-server setup

Three options, from simplest to best quality:

### Option 1 — Single model (quick experiments)

```bash
/path/to/llama-server \
  -m /Volumes/d/aimodels/lmstudio-community/gemma-4-12B-it-QAT-GGUF/gemma-4-12B-it-QAT-Q4_0.gguf \
  --alias gemma-12b \
  --ctx-size 32768 \
  --n-gpu-layers 99 \
  --host 0.0.0.0 --port 8080
```

All three profiles in `config.yaml` should use `model: "gemma-12b"`.

The `--alias` flag sets what the `/v1/models` endpoint returns as the model id — useful for introspection, but not used for routing here.

---

### Option 2 — Router mode (recommended)

Router mode lets a single llama-server instance hot-swap models on demand. It reads the `model` field in each API request, loads the matching model (evicting others if `--models-max 1`), and serves the response — no restarts.

```bash
/Volumes/d/apps/llama.cpp/llama.cpp/build/bin/llama-server \
  --router \
  --models-dir /Volumes/d/aimodels \
  --models-preset /Volumes/d/code/aiml/self-improving-loop/router-preset.ini \
  --models-max 1 \
  --host 0.0.0.0 --port 8080
```

Then set profiles in `config.yaml`:
```yaml
profiles:
  generator:
    model: "gemma-12b"    # fast — matches [gemma-12b] in preset
  critic:
    model: "gemma-26b"    # smart — matches [gemma-26b] in preset
  refiner:
    model: "gemma-26b"    # same as critic
```

The loop calls generator, then critic, then refiner **serially** — the router swaps between them automatically. With `--models-max 1`, only one model is in VRAM at a time.

**router-preset.ini** is already configured for the models in `/Volumes/d/aimodels`. See that file for all available sections (`gemma-12b`, `gemma-26b`, `gemma-31b`, `qwen-35b`, `qwen-27b`).

Router mode flags (confirmed in build b9833):

| Flag | Description |
|------|-------------|
| `--router` | Enable router mode |
| `--models-dir PATH` | Directory containing GGUF files |
| `--models-preset PATH` | INI file with per-model flags |
| `--models-max N` | Max simultaneous models in VRAM (default 4; use 1 for hot-swap) |
| `--models-autoload` | Register all models at startup without loading them |

---

### Option 3 — Two server instances

Best latency (no swap delay), needs enough VRAM for two models simultaneously.

```bash
# Terminal 1 — generator (fast model, port 8080)
llama-server -m .../gemma-4-12B-it-QAT-Q4_0.gguf --alias gemma-12b --port 8080

# Terminal 2 — critic + refiner (smart model, port 8081)
llama-server -m .../Qwen3.6-35B-A3B-UD-Q4_K_M.gguf --alias qwen-35b --port 8081
```

```yaml
profiles:
  generator:
    base_url: "http://localhost:8080/v1"
    model: "gemma-12b"
  critic:
    base_url: "http://localhost:8081/v1"
    model: "qwen-35b"
  refiner:
    base_url: "http://localhost:8081/v1"
    model: "qwen-35b"
```

---

## Configuration reference

### `config.yaml` — profiles

```yaml
profiles:
  generator:
    base_url: "http://192.168.1.4:8080/v1"
    model: "gemma-12b"        # must match --alias or router preset section
    temperature: 0.3
    max_tokens: 2048

  critic:
    base_url: "http://192.168.1.4:8080/v1"
    model: "gemma-26b"
    temperature: 0.1          # low = consistent scores
    max_tokens: 1024

  refiner:
    base_url: "http://192.168.1.4:8080/v1"
    model: "gemma-26b"
    temperature: 0.4          # slightly higher = creative rewrites
    max_tokens: 1024
```

### `config.yaml` — loop settings

```yaml
loop:
  max_iterations: 6         # hard cap on cycles
  score_threshold: 8.0      # stop early when critic total ≥ this (out of 10)
  plateau_patience: 2       # stop early after this many consecutive iterations with no score improvement
  sessions_dir: "sessions"
```

### `config.yaml` — rubric

Add, remove, or rename dimensions. The critic system prompt and scoring rebuild automatically.

```yaml
rubric:
  - name: accuracy
    description: "Factual correctness and logical soundness of claims"
  - name: completeness
    description: "All meaningful aspects of the task are addressed"
  - name: clarity
    description: "Well-structured, readable, no unnecessary jargon"
  - name: depth
    description: "Goes beyond surface-level; genuine analysis or insight"
  - name: relevance
    description: "Stays on task; no padding, repetition, or tangents"
```

---

## CLI reference

```
python loop.py [options]

Input:
  --task TEXT          Task description (inline)
  --task-file PATH     Load task from a text file
  --prompt TEXT        Initial prompt (default: generic fallback)

Loop control:
  --iterations N          Max generate→critique→refine cycles (default: 6)
  --threshold N           Stop early when total score ≥ N (default: 8.0)
  --plateau-patience N    Stop early after N consecutive iterations with no
                          score improvement (default: 2)

Model profiles:
  --gen-profile NAME   Profile for generator (default: generator)
  --crit-profile NAME  Profile for critic    (default: critic)
  --ref-profile NAME   Profile for refiner   (default: refiner)

Web search:
  --search              Pre-search the web for task context via Tavily
  --search-depth DEPTH  basic (default, 1 credit) | advanced (2 credits)

Session management:
  --list               List all saved sessions with scores
  --show SESSION_ID    Display full session history
```

Every run prints the response, the exact prompt that produced it, the critic's reasoning, and its improvement suggestions live for each iteration — not just when replayed with `--show`. After the loop ends (if more than one iteration ran), a colored per-iteration score table is printed, marking which iteration was kept as "best":

```
    Iter     Accu   Comp   Clar   Dept   Rele   Total
    1          10     10     10      5     10     9.0
    2          10     10     10      9     10     9.8 *
    3          10     10     10      9     10     9.8

    * = best-scoring iteration
```

---

## File structure

```
self-improving-loop/
├── loop.py              # CLI + orchestration (generate → critique → refine)
├── phases.py            # generate() / critique() / refine() — plain openai client calls
├── benchmark.py         # speed + quality benchmark harness across local models
├── benchmarks/          # auto-created; one JSON per benchmark run
├── tools.py             # get_system_date(), web_search(), fetch_url() (Tavily)
├── config.py            # loads config.yaml, exports cfg + PROFILES
├── config.yaml          # model profiles, loop settings, rubric
├── router-preset.ini    # llama-server router mode model config
├── prompts/
│   ├── generator_system.md
│   ├── critic_system.md    # rubric dimensions injected at load
│   └── refiner_system.md
├── sessions/            # auto-created; one JSON per loop run
└── requirements.txt
```

---

## Sessions

Every `loop.py` run saves to `sessions/<timestamp>.json`:

```json
{
  "session_id": "20260704_143022",
  "task": "...",
  "history": [
    {
      "iteration": 1,
      "prompt": "...",
      "response": "...",
      "scores": {"accuracy": 6, "completeness": 5, ...},
      "total": 6.2,
      "reasoning": "...",
      "improvements": ["...", "..."]
    }
  ],
  "best": { ... }
}
```

Sessions are plain JSON — easy to diff, post-process, or feed into another analysis.

---

## Web search (Tavily)

Pass `--search` to pre-fetch web context for the task before the first generate call. The results are injected into the generator's context and reused across all iterations (the task is fixed — only the prompt changes each cycle).

```bash
export TAVILY_API_KEY="tvly-..."

python loop.py \
  --task "Analyze the current state of open-source LLM inference" \
  --search                    # basic depth, 1 credit per search
  --search-depth advanced     # deeper results, 2 credits
```

**Why pre-search instead of per-iteration search:**
The web context grounds factual content for the task. Since the task doesn't change between iterations, fetching once is sufficient and avoids burning Tavily credits on each cycle.

**`fetch_url`** is also available in `tools.py` if you want to pull a specific URL's content before running a loop:

```python
from tools import fetch_url
context = fetch_url("https://example.com/article")
```

**Setup:**
```bash
pip install tavily-python   # already in requirements.txt
export TAVILY_API_KEY="tvly-..."   # add to ~/.zshrc or .env
```

---

## Model benchmark

`benchmark.py` answers a different question than the loop itself: *which local model should play which role?* It runs a fixed set of 10 tasks (code with tests, technical explanation, summarization, creative writing, SQL, technology comparison, ELI5, email drafting, etc.) through each candidate model, times generation (wall time + tokens/sec), then scores every response with a single fixed judge model — so speed and quality are comparable across models without any model grading its own work.

```bash
conda activate lipi
python benchmark.py                              # all 5 models, 10 built-in tasks
python benchmark.py --models gemma-12b qwen-27b   # subset
python benchmark.py --tasks-file my_tasks.json    # custom task list
python benchmark.py --out benchmarks/run1.json
```

It's a **two-pass design**: all generation for one model completes before moving to the next, and judging happens in one batch at the end. Under router mode (`--models-max 1`) this keeps model reloads to one-per-model-plus-one-for-the-judge instead of thrashing on every task.

### Results (`benchmarks/full_run_20260711_212918.json` — 10 tasks × 5 models, judged by gemma-26b)

| Model      | Avg tok/s | Avg time/task | Avg quality (/10) | Avg completion tokens |
|------------|----------:|--------------:|-------------------:|-----------------------:|
| gemma-26b  | **64.98** | 9.01s          | 9.74                | 588 |
| qwen-35b   | 42.74     | 15.79s         | 9.60                | 548 |
| gemma-12b  | 28.50     | 19.93s         | 9.70                | 566 |
| gemma-31b  | 11.51     | 45.56s         | **9.78**            | 507 |
| qwen-27b   | 8.52      | 67.20s         | 9.64                | 561 |

**Takeaways from this run:**
- **gemma-26b is the sweet spot** — fastest by a wide margin (nearly 5x gemma-31b's throughput) while landing within 0.04 of the top quality score. This is why `config.yaml` defaults critic/refiner to gemma-26b.
- **gemma-31b scores highest on quality** but at 5-7x the latency of gemma-26b/qwen-35b — worth it for a single high-stakes critique pass, not for a fast iterate-many-times refine loop.
- **gemma-12b holds up surprisingly well on quality** (9.70, second place) despite being the smallest model, which validates using it as the generator — it's "good enough" at a fraction of the cost of the smart models, leaving the critic/refiner to do the heavy lifting.
- **qwen-27b was the slowest model tested** on this hardware despite being similar in size to gemma-26b, without a quality edge to justify it.

Re-run `python benchmark.py` any time model files, hardware, or `router-preset.ini` change — these numbers are specific to the local `/Volumes/d/aimodels` GGUF builds and the machine they were measured on, not universal model rankings.

---

## Loop results so far

Early validation runs (4 sessions, gemma-26b critic/refiner) converged quickly on well-scoped tasks and took more iterations on open-ended ones — behaving as designed:

- Prime-number check tasks: scored 9.8–10.0/10 in 1–4 iterations.
- Mango-ripeness task: scored 9.6/10 in a single iteration.

---

## Tips

**For analysis/research tasks** — use a higher `--threshold` (9.0) and more `--iterations` (8-10). The critic is strict by design; 8+ is genuinely good.

**For best critique quality** — route critic + refiner to `gemma-26b` or `qwen-35b`. The generator can stay on `gemma-12b` for speed. With router mode this is a one-line config change.

**Custom rubrics** — for domain-specific optimization (e.g. financial analysis), add dimensions like `data_citation` or `risk_acknowledgement` to the rubric in `config.yaml`. No code changes needed.

**The initial prompt matters** — a better starting point reaches threshold faster. Giving a structured prompt (e.g. "Analyze X. Cover Y, Z. Format as bullet points.") is better than a blank slate.

**Plateau stalls happen** — sometimes the refiner keeps rewording a prompt without moving the score (e.g. adding more formatting instructions once accuracy/depth are already maxed). `--plateau-patience` (default 2) stops the loop once this happens instead of burning through all `--iterations`. Lower it to 1 for faster stops, or raise it if your critic profile's scores are noisy from run to run.
