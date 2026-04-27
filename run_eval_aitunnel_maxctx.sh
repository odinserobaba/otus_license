#!/usr/bin/env bash
# Прогон 20 вопросов (eval_questions.jsonl): RAG + AITunnel с «широким» контекстом,
# как в удачном single_query (бюджет символов, полные чанки, qwen3.5-9b).
#
# Перед запуском:
#   export OPENAI_API_KEY="..."
#   # опционально:
#   export OPENAI_BASE_URL="https://api.aitunnel.ru/v1/"
#
# Результат: processed/eval_aitunnel_maxctx.jsonl
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
  echo "Нет .venv — создайте окружение и pip install -r requirements.txt" >&2
  exit 1
fi
if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  echo "Задайте OPENAI_API_KEY" >&2
  exit 1
fi

export OPENAI_BASE_URL="${OPENAI_BASE_URL:-https://api.aitunnel.ru/v1/}"

exec .venv/bin/python scripts/llm_eval_openai_compatible.py \
  --model qwen3.5-9b \
  --top-k 0 \
  --max-chunks-cap 500 \
  --prompt-char-budget 400000 \
  --max-chunk-chars 0 \
  --max-tokens 16384 \
  --temperature 0.2 \
  --timeout 600 \
  --questions data/test/eval_questions.jsonl \
  --index processed/lexical_index.json \
  --output processed/eval_aitunnel_maxctx.jsonl \
  "$@"
