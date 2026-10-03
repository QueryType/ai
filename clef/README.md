# clef — experiments with llama.cpp decision models (`/v1/systemone`)

Learning and testing the "decision model" support added to llama.cpp in
[PR #29818](https://github.com/ggml-org/llama.cpp/pull/29818) (ngxson, merged 2026-10-02):
a `POST /v1/systemone` endpoint that answers typed questions about a `state` in one forward pass, with no token generation.

The folder is named after [Cloudflare/clef](https://huggingface.co/Cloudflare/clef), whose llama.cpp support is still
in progress (see [clef status](#clef-status)). Everything here currently runs on **Laya** and **lev**.

## Files

| File | What it is |
|---|---|
| `serve.sh` | Starts `llama-server` with a decision model: `./serve.sh laya` (port 8081) or `./serve.sh lev` (port 8082) |
| `systemone.py` | Stdlib-only client with 8 experiments (`basic`, `order`, `criteria`, `score`, `paraphrase`, `sweep`, `many`, `compare`) |
| `laya.log`, `lev.log` | Server logs from the last runs |

## Setup

Nothing is installed or built in this folder. It uses:

| Thing | Location | Override |
|---|---|---|
| `llama-server` (master, includes PR #29818) | `/Volumes/d/apps/llama.cpp/llama.cpp/build/bin/llama-server` | `LLAMA_SERVER=...` |
| Models | `/Volumes/d/aimodels/ggml-org/{Laya-GGUF,lev-GGUF}/` | `MODELS_DIR=...` |
| Python | `strandsagents` conda env (`/Volumes/d/conda/conda_envs/strandsagents/bin/python`) | — |

Models used (from the pre-converted `ggml-org` repos on Hugging Face):

| Model | File | Size | Architecture |
|---|---|---|---|
| Laya | `ggml-org/Laya-GGUF/Laya-Q8_0.gguf` | 449 MB | ModernBERT encoder + decision head |
| lev | `ggml-org/lev-GGUF/lev-Q4_K_M.gguf` | 3.0 GB | causal LM (Qwen-based), label logits |

To check that a `llama-server` build has the endpoint:

```bash
strings "$(dirname "$LLAMA_SERVER")/libllama-server-impl.dylib" | grep -m1 /v1/systemone
```

## Quick start

```bash
cd /Volumes/d/code/aiml/clef
PY=/Volumes/d/conda/conda_envs/strandsagents/bin/python

./serve.sh laya          # terminal 1
./serve.sh lev           # terminal 2 (optional)

$PY systemone.py basic                                   # against laya (8081)
$PY systemone.py order --url http://127.0.0.1:8082       # against lev
$PY systemone.py compare --url2 http://127.0.0.1:8082    # laya vs lev, same request

pkill -f build/bin/llama-server                          # stop both
```

No special flag turns the endpoint on: `llama-server` enables it when the GGUF has `<arch>.decision.type` metadata.
A model without it returns `501`.

## The API

```bash
curl -s localhost:8081/v1/systemone -H 'Content-Type: application/json' -d '{
  "state": "I was charged twice for order #4471, refund me",
  "questions": {
    "team":    {"type": "choice", "instructions": "Which team?", "criteria": {"billing": null, "shipping": null}},
    "refund":  {"type": "noul",   "instructions": "Is a refund requested?"},
    "urgency": {"type": "score",  "instructions": "How urgent?", "criteria": ["can wait", "today", "right now"]}
  }
}' | jq
```

| `type` | `criteria` | Answer |
|---|---|---|
| `choice` | `{option: description or null}` | `choice`, `probabilities` (sum to 1), `confidence = (p_max − 1/n) / (1 − 1/n)` |
| `score` | array of 2–10 levels, lowest first | `score` = Σ i·pᵢ (can fall between levels), `legend`, `probabilities`, `confidence` |
| `noul` | optional `{"true": ..., "false": ...}` | `noul` = P(true) |

- `state` and `instructions` can be strings, objects or arrays; non-strings are given to the model as JSON.
- Each question is answered independently. `usage.input_tokens` counts every question's full prompt; `output_tokens` is always 0.
- `images` (data URLs) only work with OpenJev plus its `--mmproj`.
- Probabilities are scaled with temperatures stored in the GGUF (`<arch>.decision.temperature.*`).
  They are **not** calibrated for your data.

`noul` is the API's yes/no type. For Laya, Kev and OpenJev it is a two-option choice (`false`/`true`).
lev was trained on a 9-point rating scale instead (0 = certainly no, 8 = certainly yes), and the server returns the
expected value Σ pᵢ·i/8. So on lev, a value near 0.5 often means "unsure", not "half likely".

## How the models produce scores

From `tools/server/server-decision.cpp` and `src/models/modern-bert.cpp` in the PR.
The model families differ only in **where the scores are read**:

| Type | Model | Prompt layout | Score read from |
|---|---|---|---|
| `laya` | ModernBERT encoder | `[CLS] question [SEP] ([MASK] option)* [SEP] state [SEP]` | Extra full-attention head blocks + scorer MLP at each `[MASK]`, run once per question type with its own token-type embedding |
| `openjev` | causal LM (+ vision) | options labelled `A`…`Z`, `a`…`z` (max 52) | next-token logits of the label tokens |
| `lev` | causal LM | labels `A`…`ZZ` (single-token ones, max 255), JSON keys sorted | label logits; `choice` asked twice (forward + reversed order) and averaged; `noul` from a 9-point rating |
| `kev` | Qwen 4B | each option ends with `<\|box_end\|>` | dot product of the last token's hidden state with each option's end-token hidden state |

Consequences:
- **Prefix sharing**: only the causal models (openjev, lev, kev) reuse the shared `state` prefix across questions
  in one request. Laya re-encodes everything per question.
- **Truncation**: Laya cuts the question and options to `max_head_tokens` (from the GGUF), the same way it was trained.
- Laya's prompts are shorter, so it uses ~3× fewer tokens than lev on the same request.

## Experiments

`python systemone.py <name> [--url URL] [--url2 URL] [-n N] [--raw | -q]`

Every call prints what was **sent** (state, each question with its type and criteria) and what was **received**
(the answer, all probabilities sorted, confidence, latency, input tokens), followed by the experiment's summary:

```
┌─ #1 SENT  POST http://127.0.0.1:8081/v1/systemone
│ state: The package arrived broken, I want my money back.
│ r [noul]: Is a refund requested?
├─ RECEIVED  17 ms  input_tokens=42  model=Laya-Q8_0.gguf
│ r → P(true) = 0.9134
└─
```

- `--raw`: the exact request and response JSON of every call instead.
- `-q`: only the summary.

This shows the API request, not the final prompt: the server renders the model's `systemone` chat template
(and, for Laya, truncates and inserts `[MASK]` markers) before the forward pass, and the API doesn't return that prompt.

| Name | Question it answers |
|---|---|
| `basic` | Does the README example work? Full JSON output |
| `order` | All 24 orders of 4 options: does the order change the probabilities? |
| `criteria` | `noul` bare vs with true/false descriptions vs with swapped descriptions |
| `score` | Expected `score` vs the most likely level, and how `confidence` behaves |
| `paraphrase` | Same question reworded 5 ways: how stable is P(true)? |
| `sweep` | A state that gradually becomes a refund request: where does P(refund) jump? |
| `many` | 16 questions in one request vs 16 requests: latency and tokens |
| `compare` | Same request on two servers, side by side |

## Results (M4 Pro, 64 GB, 2026-10-02)

### Laya vs lev on one ticket

State: *"Hi, I was charged twice for my order #4471 and I want a refund. This is the third time I'm writing!"*

| | Laya (449 MB, Q8) | lev (3 GB, Q4) |
|---|---|---|
| intent | refund 0.997 | refund 0.896 |
| refund (P true) | 0.92 | 0.95 |
| urgent (P true) | 0.07 | 0.33 |
| frustration (0–3) | 2.48 | 1.33 |
| latency | **68 ms** | 865 ms |
| input tokens | 229 | 671 |

The models agree on the clear questions and disagree on the subjective ones.

### Option order

| | Top pick | Mean P(billing) | Spread across 24 orders |
|---|---|---|---|
| Laya | billing in all 24 | 0.93 | 0.09 |
| lev | billing in all 24 | 0.86 | 0.08 |

lev's reversed second pass doesn't remove the order effect: it cancels a bias toward the first position only.
Options in the middle barely move when the list is reversed, and the options still influence each other.

### `noul` behaviour

| Test | Laya | lev |
|---|---|---|
| "Where is my order?" → refund? (should be ~0) | **0.0006** | 0.45 |
| criteria: bare / described / swapped (refund ticket) | 0.92 / 0.94 / 0.84 | 0.95 / 0.94 / 0.93 |
| 4 plain rewordings of the question | 0.86–0.92 | 0.92–0.95 |
| "satisfied *only if* the charge is reversed" | 0.79 | 0.55 |

- Neither model reads the true/false descriptions closely: put definitions in `instructions`.
- lev is steadier under rewording but drifts toward 0.5 when unsure (the 9-point scale).

### Sweep: P(refund) as the state changes

| State | Laya | lev |
|---|---|---|
| The package arrived. | 0.00 | 0.02 |
| …but the box was dented. | 0.05 | 0.13 |
| …but the charger inside is cracked. | 0.02 ✓ | **0.92 ✗** |
| …arrived broken, I want a **replacement**. | **0.82 ✗** | 0.13 ✓ |
| …arrived broken, I want my money back. | 0.91 | 0.97 |
| …broken and I was charged twice. Refund me now. | 1.00 | 0.97 |

Each model makes a different mistake. Asking both and only acting when they agree is worth testing.

### Score

`score` is an expected value, not a level. Laya on *"Still no reply. This is getting ridiculous."* (5 levels):
`score` 2.89, most likely level 3, with 0.28 on level 4. `confidence` stays at 0.25–0.6 whenever neighbouring levels
split the probability. For routing, use the mode or the full distribution, not `round(score)`.

### Prefix sharing (`many`, 16 questions, longer state)

| | One request | 16 requests | Speedup |
|---|---|---|---|
| lev | 2,700 ms | 6,967 ms | **2.6×** |
| Laya | 682 ms | 761 ms | 1.1× (none, as expected) |

## Bug: Laya aborts the server on multi-question requests

With default batch settings (`-ub 512`) and `-np 4`, a request with several questions and a longer state crashed
`llama-server` (exit 134):

```
llama-context.cpp:1503: GGML_ASSERT(cparams.n_ubatch >= n_tokens && "encoder requires n_ubatch >= n_tokens") failed
```

An encoder has to process its whole batch in one micro-batch, but the server packs several slots' prompts
(here 4 × ~600 tokens) into one `encode()` call. **Workaround** (already in `serve.sh`): `-b 8192 -ub 8192` for Laya.
Not yet re-tested without the workaround on the current build, and not yet reported upstream.

## clef status

Cloudflare's clef needs [PR #29831](https://github.com/ggml-org/llama.cpp/pull/29831) (ngxson, **open** as of 2026-10-02).
Instead of reading one token per option, clef averages hidden states over **spans** of tokens (the question, and each
option). The PR adds a libllama API to tag them:

```
llama_batch_ext_set_decision_order(batch, idx, order)   // 0 text, 1/2/3 question (noul/choice/score), 4 option
```

Known limits in the PR: no vision yet (needs #29622), one sequence per batch (so no prefix sharing), and no official
GGUF yet ("make gguf" is still a TODO). A third-party GGUF converted before the PR merges may not load afterwards.

When it merges:
1. Update and rebuild `/Volumes/d/apps/llama.cpp/llama.cpp`.
2. Download the official GGUF to `/Volumes/d/aimodels/ggml-org/clef-GGUF/`.
3. Add a `clef)` case to `serve.sh`; `systemone.py` works unchanged.

## Next steps

The experiments above show behaviour, not accuracy. To choose a model for real use:

1. Label 50–200 real examples with the expected answer per question.
2. Measure accuracy for `choice` and AUC for `noul`.
3. Pick `noul` thresholds from the data instead of 0.5 (Laya scored "I want a replacement" at 0.82 for refund).
4. Check calibration: bucket predictions (0.0–0.1, 0.1–0.2, …) and compare with the share actually true.
5. Try OpenJev (`ggml-org/OpenJev-GGUF`, 19 GB Q4 + mmproj) for image input, and the "nimble" model from PR #29844,
   which is already in the local llama.cpp checkout.
