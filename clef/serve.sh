#!/usr/bin/env bash
# usage: ./serve.sh laya|lev [port]
# no special flag: llama-server enables /v1/systemone when the GGUF has "<arch>.decision.type"
set -euo pipefail
cd "$(dirname "$0")"
LLAMA_SERVER="${LLAMA_SERVER:-/Volumes/d/apps/llama.cpp/llama.cpp/build/bin/llama-server}"
MODELS_DIR="${MODELS_DIR:-/Volumes/d/aimodels}"

MODEL="${1:-laya}"
PORT="${2:-}"
case "$MODEL" in
  # laya is a non-causal encoder: all slots' prompts batched together must fit in one ubatch,
  # otherwise GGML_ASSERT(n_ubatch >= n_tokens) aborts the server (seen with 16 questions x ~600 tokens)
  laya) FILE="$MODELS_DIR/ggml-org/Laya-GGUF/Laya-Q8_0.gguf"; PORT="${PORT:-8081}"; EXTRA=(-b 8192 -ub 8192) ;;
  lev)  FILE="$MODELS_DIR/ggml-org/lev-GGUF/lev-Q4_K_M.gguf";  PORT="${PORT:-8082}"; EXTRA=() ;;
  *)    echo "unknown model: $MODEL (laya|lev)"; exit 1 ;;
esac

# -np 4: 4 slots, so lev (causal) can share the state prefix across questions of one request
exec "$LLAMA_SERVER" -m "$FILE" --port "$PORT" -np 4 -c 16384 -ngl 99 ${EXTRA[@]+"${EXTRA[@]}"}
