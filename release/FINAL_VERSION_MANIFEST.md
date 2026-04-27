# Final Version Manifest

Ниже перечислены файлы проекта, относящиеся к финальной версии baseline на `yandexgpt-5-lite`.

## Core runtime

- `app.py`
- `run.sh`
- `build.sh`
- `requirements.txt`

## Corpus + retrieval pipeline

- `scripts/prepare_corpus.py`
- `scripts/prepare_doc_files.py`
- `scripts/chunk_corpus.py`
- `scripts/build_index.py`

## Evaluation / regression

- `scripts/eval_yandex_suite.py`
- `data/test/eval_questions.jsonl`
- `data/test/eval_questions_extra10.jsonl`

## Tests (guardrails and sanitization)

- `tests/test_rag_critical_guard.py`

## Documentation for final architecture

- `README.md`
- `docs/readme_parts/00_INDEX.md`
- `docs/readme_parts/03_APP_AND_RAG_PIPELINE.md`
- `docs/readme_parts/04_HYBRID_RETRIEVAL_EMBEDDINGS.md`
- `docs/readme_parts/06_OPERATION_MONITORING_TROUBLESHOOTING.md`
- `docs/readme_parts/09_ARCHITECTURE_AND_WORKFLOW_SCHEMES.md`
- `release/FINAL_SCHEMA_YANDEXGPT5LITE.md`
- `release/CORPUS_RETRIEVAL_PIPELINE.md`
- `release/README.md`

## Excluded from final baseline

- `local_lora` training/inference workflow (optional);
- AITUNNEL-specific artifacts (optional alternative backend);
- Windows-specific helper scripts (если релиз только под Linux baseline).
