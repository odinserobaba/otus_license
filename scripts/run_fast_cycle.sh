#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

SMOKE_Q_FILE="${SMOKE_Q_FILE:-data/test/eval_questions_smoke3.jsonl}"
RUN_DIR="${RUN_DIR:-processed/runs/fast_cycle_$(date +%Y%m%d_%H%M%S)}"
BASELINE_JSONL="${BASELINE_JSONL:-processed/runs/smoke3_baseline/eval_smoke3.jsonl}"
RUN_FULL="${RUN_FULL:-0}"

mkdir -p "$RUN_DIR"

echo "[1/4] pytest"
.venv/bin/python -m pytest -q

echo "[2/4] smoke-3 eval"
if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

.venv/bin/python scripts/eval_yandex_suite.py \
  --questions "$SMOKE_Q_FILE" \
  --answer-mode user \
  --llm-backend yandex_openai \
  --out-jsonl "$RUN_DIR/eval_smoke3.jsonl" \
  --out-md "$RUN_DIR/eval_smoke3_report.md" \
  --out-qa "$RUN_DIR/eval_smoke3_qa.md"

if [[ -f "$BASELINE_JSONL" ]]; then
  echo "[3/4] compare smoke before/after"
  .venv/bin/python scripts/compare_eval_runs.py \
    --before "$BASELINE_JSONL" \
    --after "$RUN_DIR/eval_smoke3.jsonl" \
    --out-md "$RUN_DIR/eval_smoke3_compare.md" \
    --title "Fast cycle smoke-3"
else
  echo "[3/4] baseline not found, skip compare: $BASELINE_JSONL"
fi

if [[ "$RUN_FULL" == "1" ]]; then
  echo "[4/4] full eval 20 + extra10"
  .venv/bin/python scripts/eval_yandex_suite.py \
    --questions data/test/eval_questions.jsonl \
    --answer-mode user \
    --llm-backend yandex_openai \
    --out-jsonl "$RUN_DIR/eval20.jsonl" \
    --out-md "$RUN_DIR/eval20_report.md" \
    --out-qa "$RUN_DIR/eval20_qa.md"
  .venv/bin/python scripts/eval_yandex_suite.py \
    --questions data/test/eval_questions_extra10.jsonl \
    --answer-mode user \
    --llm-backend yandex_openai \
    --out-jsonl "$RUN_DIR/eval_extra10.jsonl" \
    --out-md "$RUN_DIR/eval_extra10_report.md" \
    --out-qa "$RUN_DIR/eval_extra10_qa.md"
else
  echo "[4/4] full eval skipped (set RUN_FULL=1 to enable)"
fi

echo "Done. Run directory: $RUN_DIR"
