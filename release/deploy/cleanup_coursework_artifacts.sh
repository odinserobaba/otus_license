#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

mkdir -p processed

# Keep only final keyretry QA artifacts + runtime index data.
shopt -s nullglob
for f in processed/*eval* processed/*answers* processed/*analysis* processed/chat_logs.jsonl processed/qa_history.jsonl; do
  case "$f" in
    processed/iter4_full_20_eval_keyretry.jsonl|\
    processed/iter4_full_20_eval_keyretry_qa.md|\
    processed/iter4_full_20_eval_keyretry_report.md|\
    processed/iter4_full_extra10_eval_keyretry.jsonl|\
    processed/iter4_full_extra10_eval_keyretry_qa.md|\
    processed/iter4_full_extra10_eval_keyretry_report.md)
      ;;
    *)
      rm -f "$f"
      ;;
  esac
done
shopt -u nullglob

echo "Cleanup done."
