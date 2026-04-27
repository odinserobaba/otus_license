# Final Release Package (YandexGPT-5-lite)

Эта папка содержит финальную конфигурацию и чек-лист запуска production-baseline:
- LLM backend: `yandex_openai`
- модель: `yandexgpt-5-lite/latest`
- retrieval: `top_k=12`, `official_only=ON`, `embeddings re-rank=ON`, `top_n=80`, `multi-step=ON`

## Содержимое

- `FINAL_SCHEMA_YANDEXGPT5LITE.md` — схема работы финального контура.
- `CORPUS_RETRIEVAL_PIPELINE.md` — отдельно про сбор корпуса и retrieval pipeline.
- `FINAL_VERSION_MANIFEST.md` — список файлов репозитория, относящихся к финальной версии.
- `.env.final.example` — шаблон переменных окружения.
- `run_final_web.sh` — запуск веба с baseline-параметрами.
- `deploy/README_RU_DEPLOY.md` — развертывание в РФ (systemd + nginx + API access).
- `DEPLOY_CHECKLIST.md` — краткий чек-лист для защиты/демо.
- `LOAD_TEST_100_PROTOCOL.md` — протокол нагрузочного прогона 100+ запросов.

## Быстрый запуск

1) Подготовьте `.env` на основе `.env.final.example`:

```bash
cp release/.env.final.example .env.final
```

2) Заполните секреты в `.env.final` (минимум `YANDEX_CLOUD_API_KEY`).

3) Запустите:

```bash
chmod +x release/run_final_web.sh
./release/run_final_web.sh
```

Веб-интерфейс: <http://127.0.0.1:7860>

## Финальная папка для GitHub

Собрать отдельную папку со всем проектом:

```bash
chmod +x release/build_final_github_package.sh
./release/build_final_github_package.sh
```

Результат:
- `release/final_project_full/`

## Оценка качества

Основной regression-run (20 вопросов):

```bash
./.venv/bin/python scripts/eval_yandex_suite.py \
  --llm-backend yandex_openai \
  --questions data/test/eval_questions.jsonl \
  --out-jsonl processed/yandexgpt5lite_eval_20_final.jsonl \
  --out-md processed/yandexgpt5lite_eval_20_final_report.md \
  --out-qa processed/yandexgpt5lite_eval_20_final_qa.md
```
