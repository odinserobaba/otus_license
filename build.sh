#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

CHUNK_SIZE=3200
CHUNK_OVERLAP=700

echo "[1/7] Ensure virtual environment"
if [[ ! -d ".venv" ]]; then
  python3 -m venv .venv
fi

echo "[2/7] Install Python dependencies"
".venv/bin/pip" install --upgrade pip >/dev/null
".venv/bin/pip" install -r requirements.txt >/dev/null

echo "[3/7] Rename all source files in doc/"
".venv/bin/python" scripts/rename_all_docs.py

echo "[4/7] Prepare RTF corpus"
".venv/bin/python" scripts/prepare_corpus.py \
  --input-dir doc \
  --txt-dir processed/clean_txt \
  --jsonl processed/cleaned_docs_rtf.jsonl

echo "[5/7] Prepare DOC/DOCX corpus (if any)"
".venv/bin/python" scripts/prepare_doc_files.py \
  --input-dir doc \
  --txt-dir processed/clean_txt \
  --jsonl processed/extra_docs.jsonl

echo "[6/7] Merge corpora and chunk"
".venv/bin/python" scripts/merge_corpora.py \
  --rtf-jsonl processed/cleaned_docs_rtf.jsonl \
  --extra-jsonl processed/extra_docs.jsonl \
  --extra-egais-jsonl processed/extra_docs_egais_centerinform.jsonl \
  --output-jsonl processed/cleaned_docs.jsonl \
  --new-doc-report processed/new_doc_presence_report.jsonl

".venv/bin/python" scripts/chunk_corpus.py \
  --input-jsonl processed/cleaned_docs.jsonl \
  --output-jsonl processed/chunks.jsonl \
  --chunk-size "$CHUNK_SIZE" \
  --overlap "$CHUNK_OVERLAP"

echo "[7/7] Build lexical index"
".venv/bin/python" scripts/build_index.py \
  --chunks-jsonl processed/chunks.jsonl \
  --output processed/lexical_index.json

echo
echo "Build complete."
echo "Run app with: ./run.sh"
