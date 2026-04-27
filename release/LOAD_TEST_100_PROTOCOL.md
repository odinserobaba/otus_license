# Load Test 100+ Protocol

Цель: проверить стабильность generation/retrieval на длинной серии запросов (100+).

## 1) Сборка нагрузочного набора

```bash
./.venv/bin/python scripts/build_loadtest_set.py \
  --target-size 120 \
  --output data/test/eval_questions_load100.jsonl
```

## 2) Прогон

```bash
YANDEX_CLOUD_API_KEY=<KEY> \
TARGET_SIZE=120 \
OUT_PREFIX=processed/loadtest_100 \
./scripts/run_load_test_100.sh
```

Артефакты:
- `processed/loadtest_100.jsonl`
- `processed/loadtest_100_report.md`
- `processed/loadtest_100_qa.md`

## 3) Что контролировать

- Доля вердиктов `ok/partial/bad`.
- Наличие fallback-блоков недоступности генерации.
- Наличие suspicious-документов.
- Средний размер ответа и структура блоков user-mode.

## 4) Рекомендации

- Сначала запускать `TARGET_SIZE=60`, потом `120+`.
- Для честного сравнения фиксировать одинаковые параметры retrieval и answer mode.
- Перед серией прогонов очищать transient-кэш при необходимости:
  - `rm -f processed/answer_cache.sqlite`
