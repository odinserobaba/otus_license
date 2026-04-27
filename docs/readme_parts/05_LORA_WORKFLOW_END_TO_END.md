# 05. LoRA Workflow End-to-End

## Цель

Сделать адаптер стиля/роли юридического ассистента без тяжелого полного fine-tuning.

Подход:

- train в Colab T4 (QLoRA),
- inference локально через base model + adapter.

## Шаг 0: Что уже реализовано в проекте

Добавлены:

- `scripts/build_lora_dataset.py`
- `notebooks/lora_qlora_colab.ipynb`
- `scripts/lora_infer_local.py`
- `requirements-lora.txt`

## Шаг 1: Подготовить датасет из истории QA

Источник:

- `processed/qa_history.jsonl`

Команда:

```bash
python3 scripts/build_lora_dataset.py \
  --input processed/qa_history.jsonl \
  --out-train data/lora/train.jsonl \
  --out-eval data/lora/eval.jsonl \
  --eval-ratio 0.1
```

Что делает скрипт:

- берет пары `question -> answer`;
- чистит служебные хвосты;
- фильтрует слишком короткие ответы;
- дедуплицирует;
- делит на train/eval;
- пишет в формат `messages` для SFT.

## Шаг 2: Проверить качество датасета

Перед обучением обязательно:

- просмотреть 30-50 random записей train;
- удалить ответы с явными ошибками или "пустыми" шаблонами;
- убрать дубли одной и той же формулировки;
- убедиться, что сохраняется юридический стиль и структура.

Практический критерий:

- лучше меньше, но чище датасет, чем много "шумных" примеров.

## Шаг 3: Обучение QLoRA в Colab

Ноутбук:

- `notebooks/lora_qlora_colab.ipynb`

Сценарий:

1. установить зависимости (`transformers`, `peft`, `trl`, `bitsandbytes`);
2. подмонтировать Google Drive;
3. загрузить train/eval JSONL;
4. запустить SFTTrainer;
5. сохранить адаптер в Drive.

Базовая модель в ноутбуке:

- `Qwen/Qwen2.5-1.5B-Instruct`

## Рекомендуемые гиперпараметры для старта

- `r=16`
- `lora_alpha=32`
- `lora_dropout=0.05`
- `max_seq_length=1536`
- `learning_rate=2e-4`
- `epochs=2`

Если переобучение:

- уменьшить epochs до 1;
- добавить больше разнообразных QA;
- увеличить eval долю.

## Шаг 4: Локальный инференс адаптера

Команда:

```bash
python3 scripts/lora_infer_local.py \
  --base-model Qwen/Qwen2.5-1.5B-Instruct \
  --adapter-path /path/to/adapter \
  --question "какие документы нужны для лицензии на перевозку этилового спирта"
```

Скрипт:

- загружает base model;
- подключает PEFT adapter;
- генерирует ответ.

## Шаг 5: Интеграция LoRA в основной `app.py` (следующий шаг)

Рекомендуемая схема:

- оставить retrieval текущим (не трогать);
- добавить новый backend `local_lora`;
- в backend вызывать base+adapter генерацию;
- включить переключатель в UI.

Так вы сравните:

- `ollama baseline`
- `yandex_openai`
- `local_lora`

на одном retrieval-контексте.

## Критические риски LoRA

1. Учится на ошибках, если QA-история шумная.  
2. Может "забыть" осторожный стиль и начать уверенно ошибаться.  
3. При очень маленьком датасете эффект нестабилен.

## Минимальные правила безопасности

- хранить test-набор отдельно (не обучать на нем);
- проверять не только "красивость", но и фактическую точность ссылок;
- оставить retrieval-валидацию и пост-фильтры включенными.

## Что считать успехом

- меньше общих фраз;
- лучше структура ответа;
- выше соответствие стилю "юридический ассистент";
- без роста галлюцинаций относительно baseline.

## Связанные разделы

- эксплуатация и оценка: `06_OPERATION_MONITORING_TROUBLESHOOTING.md`
- итоговый план внедрения: `07_IMPLEMENTATION_PLAN_TURNKEY.md`
