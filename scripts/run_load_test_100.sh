#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

TARGET_SIZE="${TARGET_SIZE:-120}"
OUT_PREFIX="${OUT_PREFIX:-processed/loadtest_100}"

echo "[1/2] Build load test set (${TARGET_SIZE} questions)"
".venv/bin/python" scripts/build_loadtest_set.py \
  --target-size "$TARGET_SIZE" \
  --output data/test/eval_questions_load100.jsonl

echo "[2/2] Run eval on load test set"
".venv/bin/python" scripts/eval_yandex_suite.py \
  --llm-backend yandex_openai \
  --answer-mode user \
  --questions data/test/eval_questions_load100.jsonl \
  --out-jsonl "${OUT_PREFIX}.jsonl" \
  --out-md "${OUT_PREFIX}_report.md" \
  --out-qa "${OUT_PREFIX}_qa.md"

echo "Done:"
echo " - ${OUT_PREFIX}.jsonl"
echo " - ${OUT_PREFIX}_report.md"
echo " - ${OUT_PREFIX}_qa.md"
