#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

TOP_K="${TOP_K:-6}"
EMBEDDINGS_TOP_N="${EMBEDDINGS_TOP_N:-40}"
QUESTIONS_FILE="${QUESTIONS_FILE:-data/test/eval_questions.jsonl}"
AB_JSONL_OUT="${AB_JSONL_OUT:-processed/eval_retrieval_ab.jsonl}"
AB_SUMMARY_OUT="${AB_SUMMARY_OUT:-processed/eval_retrieval_ab_summary.json}"
YANDEX_CLOUD_API_KEY="${YANDEX_CLOUD_API_KEY:-}"
YANDEX_CLOUD_FOLDER="${YANDEX_CLOUD_FOLDER:-b1g80c8c8v3gh72ahsi7}"
YANDEX_EMBEDDING_MODEL="${YANDEX_EMBEDDING_MODEL:-text-search-query/latest}"

echo "[1/5] Check environment and required artifacts"
if [[ ! -d ".venv" ]]; then
  echo "Virtual environment not found: .venv"
  echo "Run: ./build.sh"
  exit 1
fi
if [[ ! -f "processed/lexical_index.json" ]]; then
  echo "Index not found: processed/lexical_index.json"
  echo "Run: ./build.sh"
  exit 1
fi

echo "[2/5] Python compile check"
".venv/bin/python" -m py_compile \
  app.py \
  scripts/build_lora_dataset.py \
  scripts/lora_infer_local.py \
  scripts/eval_retrieval_ab.py \
  scripts/test_retrieval.py

echo "[3/5] Retrieval smoke test"
".venv/bin/python" scripts/test_retrieval.py \
  --index processed/lexical_index.json \
  --top-k "$TOP_K"

echo "[4/5] Build/refresh LoRA dataset split"
".venv/bin/python" scripts/build_lora_dataset.py \
  --input processed/qa_history.jsonl \
  --out-train data/lora/train.jsonl \
  --out-eval data/lora/eval.jsonl \
  --eval-ratio 0.1

echo "[5/5] A/B retrieval evaluation (baseline vs embeddings)"
if [[ -n "${YANDEX_CLOUD_API_KEY:-}" && -n "${YANDEX_CLOUD_FOLDER:-}" ]]; then
  ".venv/bin/python" scripts/eval_retrieval_ab.py \
    --questions "$QUESTIONS_FILE" \
    --top-k "$TOP_K" \
    --official-only \
    --embeddings-top-n "$EMBEDDINGS_TOP_N" \
    --yandex-api-key "$YANDEX_CLOUD_API_KEY" \
    --yandex-folder "$YANDEX_CLOUD_FOLDER" \
    --embedding-model "$YANDEX_EMBEDDING_MODEL" \
    --output-jsonl "$AB_JSONL_OUT" \
    --output-summary "$AB_SUMMARY_OUT"
else
  echo "YANDEX_CLOUD_API_KEY or YANDEX_CLOUD_FOLDER is not set."
  echo "Skipping embeddings A/B test."
  echo "To run full A/B, export credentials and re-run ./test.sh."
fi

echo
echo "Tests completed."
echo "A/B details: $AB_JSONL_OUT"
echo "A/B summary: $AB_SUMMARY_OUT"
