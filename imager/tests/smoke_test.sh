#!/usr/bin/env bash
# Repeatable smoke test for the imager pipeline (chunk -> bible -> scenes -> prompts).
# No ComfyUI needed -- stops before the `images` stage.
#
# Fixtures are public-domain excerpts (Project Gutenberg) borrowed from the
# story_chunker/story_summarizer test corpora on the Desktop:
#   - jeeves_ch1.txt        dialogue-heavy, single scene, few characters
#   - twelve_years_ch1.txt  narrative prose, different tone, tests bible merge
#
# Usage:
#   ./tests/smoke_test.sh                # run against both fixtures
#   PARALLEL=1 ./tests/smoke_test.sh      # sequential LLM calls (matches a
#                                         # 1-slot llama-server)
#   FORCE=1 ./tests/smoke_test.sh         # ignore cached stage output, rerun fully
#   LLM_URL=http://localhost:8080/v1 LLM_MODEL=my-model ./tests/smoke_test.sh

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGER_SRC="$SCRIPT_DIR/../src"
FIXTURES_DIR="$SCRIPT_DIR/fixtures"
OUT_DIR="$SCRIPT_DIR/out"

LLM_URL="${LLM_URL:-http://localhost:8080/v1}"
LLM_MODEL="${LLM_MODEL:-local-model}"
PARALLEL="${PARALLEL:-4}"
FORCE_FLAG=""
[ "${FORCE:-0}" = "1" ] && FORCE_FLAG="--force"

FIXTURES=("jeeves_ch1.txt" "twelve_years_ch1.txt")

pass=0
fail=0

for fixture in "${FIXTURES[@]}"; do
    name="${fixture%.txt}"
    story="$FIXTURES_DIR/$fixture"
    out="$OUT_DIR/$name"
    mkdir -p "$out"

    echo "=== $name (parallel=$PARALLEL) ==="
    PYTHONPATH="$IMAGER_SRC" python3 -m imager.cli "$story" \
        --out-dir "$out" \
        --only-stage prompts \
        --chunk-budget-chars 1200 \
        --parallel "$PARALLEL" \
        --llm-url "$LLM_URL" \
        --llm-model "$LLM_MODEL" \
        $FORCE_FLAG

    status=$?
    prompts_file="$out/prompts.json"

    if [ $status -ne 0 ]; then
        echo "  FAIL: pipeline exited $status"
        fail=$((fail + 1))
        continue
    fi

    if [ ! -s "$prompts_file" ]; then
        echo "  FAIL: $prompts_file missing or empty"
        fail=$((fail + 1))
        continue
    fi

    n=$(python3 -c "import json; print(len(json.load(open('$prompts_file'))))")
    if [ "$n" -lt 1 ]; then
        echo "  FAIL: $prompts_file has zero scenes"
        fail=$((fail + 1))
        continue
    fi

    echo "  PASS: $n scene prompt(s) -> $prompts_file"
    pass=$((pass + 1))
done

echo
echo "=== $pass passed, $fail failed ==="
[ $fail -eq 0 ]
