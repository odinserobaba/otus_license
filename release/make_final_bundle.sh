#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUNDLE_DIR="$ROOT_DIR/release/final_bundle"

rm -rf "$BUNDLE_DIR"
mkdir -p "$BUNDLE_DIR"

copy_file() {
  local rel="$1"
  mkdir -p "$BUNDLE_DIR/$(dirname "$rel")"
  cp "$ROOT_DIR/$rel" "$BUNDLE_DIR/$rel"
}

# Core runtime
copy_file "app.py"
copy_file "run.sh"
copy_file "build.sh"
copy_file "requirements.txt"

# Retrieval pipeline
copy_file "scripts/prepare_corpus.py"
copy_file "scripts/prepare_doc_files.py"
copy_file "scripts/chunk_corpus.py"
copy_file "scripts/build_index.py"

# Eval + tests
copy_file "scripts/eval_yandex_suite.py"
copy_file "data/test/eval_questions.jsonl"
copy_file "data/test/eval_questions_extra10.jsonl"
copy_file "tests/test_rag_critical_guard.py"

# Docs
copy_file "README.md"
copy_file "docs/readme_parts/00_INDEX.md"
copy_file "docs/readme_parts/03_APP_AND_RAG_PIPELINE.md"
copy_file "docs/readme_parts/04_HYBRID_RETRIEVAL_EMBEDDINGS.md"
copy_file "docs/readme_parts/06_OPERATION_MONITORING_TROUBLESHOOTING.md"
copy_file "docs/readme_parts/09_ARCHITECTURE_AND_WORKFLOW_SCHEMES.md"
copy_file "release/README.md"
copy_file "release/FINAL_SCHEMA_YANDEXGPT5LITE.md"
copy_file "release/FINAL_VERSION_MANIFEST.md"
copy_file "release/.env.final.example"
copy_file "release/run_final_web.sh"

echo "Final bundle created:"
echo "  $BUNDLE_DIR"
