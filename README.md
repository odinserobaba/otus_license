# EGAIS Licensing RAG Assistant 

Учебный проект юридического ассистента по лицензированию алкогольной продукции и ЕГАИС.

Проект реализует полный контур:
- сбор и очистка корпуса нормативных документов;
- юридически-ориентированный chunking с метаданными;
- гибридный retrieval (TF-IDF + embeddings + multi-step + иерархическое расширение);
- генерация ответов в пользовательском формате с guardrails;
- автоматическая оценка качества (`smoke-3`, `extra10`, `20 + extra10`, `100+ load test`);
- подготовка к деплою на Linux-сервер в РФ.

---

## 1. Цель проекта

Сделать практичный RAG-ассистент, который:
- отвечает на типовые вопросы заявителя по лицензированию;
- опирается на локальную нормативную базу;
- явно показывает источники;
- минимизирует галлюцинации и “шум шаблонов”;
- подходит для демонстрации в рамках дипломной работы.

Целевой baseline модели: `yandexgpt-5-lite/latest`.

---

## 2. Что было сделано 

### Этап A: базовый RAG-контур

- Подготовлен pipeline обработки документов из `doc/` и дополнительных форматов.
- Реализован индекс `processed/lexical_index.json`.
- Поднят веб-интерфейс на Gradio (`app.py`) с retrieval + генерацией.

### Этап B: улучшение retrieval-качества

- Включен гибридный retrieval:
  - TF-IDF (основной поиск),
  - embeddings re-rank (`text-search-query/latest`),
  - multi-step retrieval (follow-up queries).
- Добавлены retries/fallback для внешних API, чтобы не падать при временной недоступности.
- Добавлен `official_only`-режим для фильтрации источников.

### Этап C: улучшение чанкинга (юридическая структура)

- Добавлен list-preserving chunking.
- В метаданные чанков добавлены:
  - `article_key`,
  - `article_part_index/total`,
  - `norm_refs`,
  - `list_density`,
  - neighbor-поля (`neighbor_prev_chunk_id`, `neighbor_next_chunk_id`),
  - иерархические признаки для post-retrieval расширения.
- В retrieval добавлено иерархическое расширение по статье/соседям (light chunk graph).

### Этап D: user-mode и юридические guardrails

- Ответы стандартизированы в блоки:
  - `### Краткий ответ`
  - `### Что сделать заявителю сейчас`
  - `### Какие документы подготовить`
  - `### Что нужно уточнить у заявителя`
  - `### Проверка актуальности норм`
  - `### Источники`
  - (опционально) `### Цитата нормы`
- Добавлены критические фактовые проверки (fact guards), в т.ч. по компетенции розницы и каналу подачи.
- Добавлена санитарка источников:
  - дедуп,
  - удаление будущих/мусорных ссылок,
  - приоритизация официальных НПА.
- Добавлены антишаблонные правила для действий/уточнений/документов.

### Этап E: контроль галлюцинаций и улучшение цитат

- Введен quality scoring для блока `Цитата нормы`.
- Добавлена фильтрация “сервисного шума” (Consultant overlays, технические хвосты).
- Добавлена жесткая проверка цитаты по реквизитам вопроса (если вопрос содержит номер НПА).

### Этап F: кеширование и производительность

- Реализован L2-кеш на SQLite:
  - answer cache,
  - retrieval cache.
- Добавлен fingerprint индекса для корректной инвалидации кеша.
- Добавлен post-expansion rerank для улучшения финального порядка после hierarchy expansion.

### Этап G: инженерный цикл и оценка

- Добавлены:
  - `scripts/run_fast_cycle.sh`,
  - `scripts/compare_eval_runs.py`,
  - `scripts/eval_chunking_grid.py`,
  - `scripts/run_load_test_100.sh`,
  - `scripts/build_loadtest_set.py`.
- Сформирован экономичный цикл разработки:
  - сначала `pytest` + `smoke-3`,
  - только после этого большие прогоны.

### Этап H: подготовка к защите/деплою

- Добавлены deployment-артефакты (`release/deploy`):
  - `systemd` unit,
  - `nginx` конфиг,
  - `provision_ubuntu.sh`,
  - `README_RU_DEPLOY.md`.
- Добавлены:
  - `release/DEPLOY_CHECKLIST.md`,
  - `release/LOAD_TEST_100_PROTOCOL.md`,
  - `release/cleanup_coursework_artifacts.sh`.

---

## 3. Финальная архитектура

1) **Corpus build**  
`prepare_corpus.py` + `prepare_doc_files.py` -> JSONL документов с метаданными (включая даты).

2) **Chunking**  
`chunk_corpus.py` -> юридические чанки + `norm_refs` + иерархические связи.

3) **Index**  
`build_index.py` -> TF-IDF индекс.

4) **Retrieval в `app.py`**  
TF-IDF -> embeddings rerank -> multi-step -> parent/child + neighbor expansion -> post-expansion rerank.

5) **Generation + post-processing**  
LLM -> guardrails -> sanitization -> структурирование user-mode -> источники/цитаты.

6) **Evaluation**  
`eval_yandex_suite.py` + сравнение прогонов + load-test 100+.

---

## 4. Ключевые файлы проекта

- `app.py` — ядро веб-приложения, retrieval/generation/guardrails/cache.
- `build.sh`, `run.sh` — сборка и запуск.
- `scripts/prepare_corpus.py` — очистка RTF-корпуса.
- `scripts/prepare_doc_files.py` — импорт doc/docx/txt/md/pdf.
- `scripts/merge_corpora.py` — дедуп и приоритизация источников.
- `scripts/chunk_corpus.py` — юридический chunking.
- `scripts/build_index.py` — сборка TF-IDF индекса.
- `scripts/eval_yandex_suite.py` — основной eval.
- `scripts/eval_chunking_grid.py` — оценка конфигураций чанкинга.
- `scripts/run_fast_cycle.sh` — быстрый цикл проверки.
- `scripts/build_loadtest_set.py`, `scripts/run_load_test_100.sh` — нагрузочный тест 100+.
- `tests/test_rag_critical_guard.py` — критические тесты guardrails.
- `release/` — финальные инструкции, deploy-артефакты и чек-листы.

---

## 5. Быстрый старт 

```bash
chmod +x build.sh run.sh
./build.sh
./run.sh
```

Откройте: [http://127.0.0.1:7860](http://127.0.0.1:7860)

---

## 6. Режим финального baseline

Рекомендуемые параметры:
- backend: `yandex_openai`
- модель: `yandexgpt-5-lite/latest`
- `top_k=12`
- `official_only=ON`
- embeddings rerank: `ON`, `top_n=80`
- `multi_step=ON`

Готовый запуск:

```bash
cp release/.env.final.example .env.final
chmod +x release/run_final_web.sh
./release/run_final_web.sh
```

---

## 6.1 Описание используемых моделей

### Генеративная модель (LLM)

- Основная модель ответа: `yandexgpt-5-lite/latest`.
- Роль в системе: формирует итоговый структурированный ответ **только на основе отобранного retrieval-контекста**.
- Почему выбрана:
  - хорошее соотношение качества и стоимости для прикладного RAG-сценария;
  - стабильная работа на типовых юридических запросах;
  - пригодна для быстрых eval-циклов (`smoke`, `extra10`).
- Важно: модель **не дообучалась на внутреннем датасете проекта**; надежность достигается не fine-tune, а связкой retrieval + guardrails + source sanitization.

### Модель эмбеддингов

- Модель семантического ранжирования: `text-search-query/latest`.
- Роль в системе: пересортировка lexical-кандидатов (embeddings re-rank), чтобы повысить смысловую релевантность.
- Режим отказоустойчивости: при недоступности embeddings API система автоматически уходит в lexical-only fallback.

### Ограничения и границы применимости

- Модель может ошибаться без достаточного контекста, поэтому обязательны проверка источников и guardrails.
- Ответ не заменяет юридическую экспертизу; финальная правовая интерпретация остается за профильным специалистом.
- Качество чувствительно к полноте/актуальности корпуса НПА: retrieval не найдет то, чего нет в локальной базе.

---

## 7. Как оценивать качество

### Smoke (дешевый регресс)

```bash
./scripts/run_fast_cycle.sh
```

### Extra10

```bash
./.venv/bin/python scripts/eval_yandex_suite.py \
  --llm-backend yandex_openai \
  --answer-mode user \
  --questions data/test/eval_questions_extra10.jsonl \
  --out-jsonl processed/eval_extra10.jsonl \
  --out-md processed/eval_extra10_report.md \
  --out-qa processed/eval_extra10_qa.md
```

### Load-test 100+

```bash
TARGET_SIZE=120 OUT_PREFIX=processed/loadtest_100 ./scripts/run_load_test_100.sh
```

Протокол: `release/LOAD_TEST_100_PROTOCOL.md`.

---

## 8. Дополнительная документация

- `docs/readme_parts/00_INDEX.md`
- `docs/PIPELINE_DETAILED_RU.md` — максимально подробный разбор подготовки документов, чанкинга и retrieval-контура
- `docs/DIPLOMA_DEFENSE_OVERVIEW_RU.md` — версия для защиты диплома (архитектура, решения, ограничения)
- `README_GITHUB.md` — быстрый onboarding за 5 минут для нового репозитория
- `release/README.md`
- `release/FINAL_SCHEMA_YANDEXGPT5LITE.md`
- `release/CORPUS_RETRIEVAL_PIPELINE.md`
- `release/FINAL_VERSION_MANIFEST.md`

---

## 9. Техническая реализация по шагам (подробно)

Ниже описан полный путь: от документов до финального ответа пользователю.

### 10  Offline build: как собирается корпус и индекс

1. **Импорт и очистка источников**
   - Скрипты: `scripts/prepare_corpus.py`, `scripts/prepare_doc_files.py`.
   - Что делаем: читаем RTF/MHTML/DOC/DOCX/TXT/MD/PDF, нормализуем текст, очищаем шум.
   - Результат: `processed/cleaned_docs.jsonl`.

2. **Юридический чанкинг**
   - Скрипт: `scripts/chunk_corpus.py`.
   - Библиотеки: `re`, `json`, `typing`, `pathlib`.
   - Что делаем:
     - выделяем главы/статьи/подпункты регулярными выражениями;
     - режем текст на семантические блоки без разрушения списков;
     - добавляем метаданные: `article_number`, `subpoint_refs`, `cited_article_refs`, `norm_refs`, соседние чанки.
   - Результат: `processed/chunks.jsonl`.

3. **Построение lexical индекса (TF-IDF)**
   - Скрипт: `scripts/build_index.py`.
   - Библиотеки: `collections.Counter`, `defaultdict`, `math`, `hashlib`, `json`, `re`.
   - Что делаем:
     - токенизируем каждый чанк;
     - считаем TF по чанку и DF по корпусу;
     - считаем IDF по формуле `log((N+1)/(df+1))+1`;
     - сохраняем индекс в JSON.
   - Результат: `processed/lexical_index.json`.

### 11 Online runtime: как обрабатывается вопрос пользователя

1. **Вход в `app.answer()`**
   - Нормализация вопроса и базовая защита от вредоносных инструкций.
   - Инициализация параметров retrieval (`top_k`, `official_only`, `multi_step`).

2. **Lexical retrieval (`score_query`)**
   - Источник: `processed/lexical_index.json`.
   - Что делаем:
     - считаем lexical score по пересечению токенов вопроса и чанка;
     - применяем юридические бусты по norm refs и intent.
   - Результат: первичный список кандидатов.

3. **Embeddings re-rank (`rerank_with_embeddings`)**
   - Что делаем:
     - берем top-N lexical кандидатов;
     - считаем embedding вопроса и кандидатов;
     - пересортировываем по семантической близости.
   - Кэш: `processed/embedding_cache.json`.
   - Fallback: при недоступности embeddings API используем lexical-only режим.

4. **Multi-step retrieval**
   - Что делаем:
     - генерируем follow-up подзапросы по первичному контексту;
     - повторно ищем по индексу;
     - объединяем и дедуплицируем результаты (`merge_scored_matches`).

5. **Иерархическое расширение контекста**
   - Что делаем:
     - добавляем parent/child и соседние части норм;
     - при включении выполняем post-expansion rerank.
   - Цель: сохранить юридическую целостность ответа (не вырывать отдельные фразы из контекста).

6. **Generation + guardrails + sources**
   - На основе финального контекста формируем prompt.
   - Применяем постобработку:
     - fact guards;
     - sanitization реквизитов и источников;
     - strict source reconstruction.
   - Результат: структурированный пользовательский ответ + источники.

### 12 Регрессия и контроль качества

1. **Unit regression (pytest)**
   - Основной набор: `tests/test_rag_critical_guard.py`.
   - Проверяются:
     - критичные факты;
     - структура user-mode;
     - обработка источников/реквизитов;
     - сценарии “список документов”.

2. **Functional eval**
   - Скрипт: `scripts/eval_yandex_suite.py`.
   - Сравнение прогонов: `scripts/compare_eval_runs.py`.
   - Контрольный набор: `extra10`.

---
