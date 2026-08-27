#!/usr/bin/env bash
# Runs the full imager pipeline end-to-end while only ever holding one model
# in VRAM at a time: loads the LLM, runs chunk->bible->scenes->prompts,
# unloads the LLM, then runs the images stage against ComfyUI (which loads
# its own model on first submitted workflow) and frees ComfyUI's VRAM when
# done. Both servers stay running the whole time -- only the VRAM residency
# is toggled -- so no manual app restarts are needed between phases.
#
# Mechanisms used (both confirmed to not require restarting the server):
#   - LM Studio: `lms load <key>` / `lms unload --all` (local CLI control)
#   - ComfyUI:   POST /free {"unload_models": true, "free_memory": true}
#
# Usage:
#   ./scripts/run_full_pipeline.sh STORY.txt --out-dir ./output [imager.cli flags...]
#
# Requires .env with IMAGER_LMS_MODEL_KEY set (the `lms load` key, which is
# NOT always the same string as IMAGER_LLM_MODEL used in API requests --
# check with `lms ls`).

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

if [ -f .env ]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
fi

: "${IMAGER_LMS_MODEL_KEY:?Set IMAGER_LMS_MODEL_KEY in .env -- the \`lms load\` key for your model (run \`lms ls\` to find it; it may differ from IMAGER_LLM_MODEL).}"
: "${IMAGER_COMFY_URL:?Set IMAGER_COMFY_URL in .env}"

if [ $# -lt 1 ]; then
    echo "Usage: $0 STORY.txt [imager.cli flags...]" >&2
    exit 1
fi

free_comfyui() {
    echo "=== Freeing ComfyUI VRAM ($IMAGER_COMFY_URL/free) ==="
    if curl -s -m 10 -X POST "$IMAGER_COMFY_URL/free" \
        -H "Content-Type: application/json" \
        -d '{"unload_models": true, "free_memory": true}' >/dev/null 2>&1; then
        echo "  ok"
    else
        echo "  ComfyUI not reachable, skipping"
    fi
}

free_comfyui

echo "=== Loading LLM: $IMAGER_LMS_MODEL_KEY ==="
lms load "$IMAGER_LMS_MODEL_KEY" -y

echo "=== LLM stages: chunk -> bible -> scenes -> prompts ==="
PYTHONPATH="$REPO_DIR/src" python3 -m imager.cli "$@" --only-stage prompts

echo "=== Unloading LLM ==="
lms unload --all

echo "=== images stage (ComfyUI) ==="
PYTHONPATH="$REPO_DIR/src" python3 -m imager.cli "$@"

free_comfyui

echo "=== Done ==="
