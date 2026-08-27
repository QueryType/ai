#!/usr/bin/env bash
# End-to-end smoke test for the `images` stage only: submits prompts to a
# running ComfyUI instance and downloads the results.
#
# Deliberately never contacts the LLM. You only have one GPU service up at a
# time, so this script requires that ./tests/smoke_test.sh (or a full run of
# the CLI without --only-stage images) has already populated
# tests/out/jeeves_ch1/scenes.json with the LLM off -- it copies that cached
# run, trims it to a couple of scenes, and reruns with --force-from images,
# which only touches chunk/bible/scenes/prompts if their config changed
# (it doesn't here), so those stages get skipped and reloaded from disk.
#
# Requires: a running ComfyUI instance (IMAGER_COMFY_URL / --comfy-url) and
# workflows/flux2_klein_4b.json (API-format, exported from ComfyUI with
# "Positive Prompt" / "Negative Prompt" CLIPTextEncode node titles).
#
# Usage:
#   ./tests/smoke_test.sh          # once, with the LLM up
#   # ... shut down the LLM, start ComfyUI ...
#   ./tests/images_smoke_test.sh   # this script, LLM off, ComfyUI up
#
#   NUM_SCENES=3 ./tests/images_smoke_test.sh   # generate more than 2

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGER_SRC="$SCRIPT_DIR/../src"
WORKFLOW="$SCRIPT_DIR/../workflows/flux2_klein_4b.json"
CACHED_DIR="$SCRIPT_DIR/out/jeeves_ch1"
OUT_DIR="$SCRIPT_DIR/out/images_check"
NUM_SCENES="${NUM_SCENES:-2}"

if [ ! -s "$CACHED_DIR/scenes.json" ]; then
    echo "FAIL: $CACHED_DIR/scenes.json not found."
    echo "  Run ./tests/smoke_test.sh first, with the LLM backend up, to populate it."
    exit 1
fi

rm -rf "$OUT_DIR"
cp -r "$CACHED_DIR" "$OUT_DIR"

python3 - "$OUT_DIR/scenes.json" "$NUM_SCENES" <<'PYEOF'
import json, sys
path, n = sys.argv[1], int(sys.argv[2])
scenes = json.load(open(path))[:n]
json.dump(scenes, open(path, "w"), indent=2)
print(f"  trimmed to {len(scenes)} scene(s) for a quick check")
PYEOF

echo "=== images smoke test (jeeves_ch1, $NUM_SCENES scene(s), LLM not contacted) ==="
PYTHONPATH="$IMAGER_SRC" python3 -m imager.cli "$SCRIPT_DIR/fixtures/jeeves_ch1.txt" \
    --workflow-file "$WORKFLOW" \
    --out-dir "$OUT_DIR" \
    --chunk-budget-chars 1200 \
    --seed 12345 \
    --steps 9 \
    --force-from images

status=$?
if [ $status -ne 0 ]; then
    echo "FAIL: pipeline exited $status"
    exit 1
fi

n=$(find "$OUT_DIR" -maxdepth 1 -iname "*.png" | wc -l | tr -d ' ')
if [ "$n" -lt 1 ]; then
    echo "FAIL: no .png files produced in $OUT_DIR"
    exit 1
fi

echo "PASS: $n image(s) -> $OUT_DIR"
