# 08. Windows Deployment + Qwen3-8B-GGUF + LoRA

## Цель

Подготовить проект к переносу на Windows-машину, где можно:

- собрать индекс и запустить веб-приложение;
- протестировать ответы на модели `Qwen3-8B-GGUF`;
- дообучить LoRA в Colab и применить адаптер локально.

## 1) Что переносим в GitHub

Минимально необходимый набор:

- исходники: `app.py`, `scripts/*`, `build.sh`, `run.sh`, `build_windows.ps1`, `run_windows.ps1`;
- документация: `README.md`, `docs/readme_parts/*`;
- данные для обучения/оценки: `data/test/*`, `data/lora/*` (если нужны);
- корпус НПА: `doc/*` (без лишних черновиков и локальных служебных файлов).

Не переносим:

- папку `processed/` (генерируется на целевой машине);
- локальные модели и кэши (`models/`, `.venv/`, pytest/jupyter cache);
- временные eval-артефакты.

## 2) Требования на Windows

- Windows 10/11 x64
- Python 3.10+ (`py -3 --version`)
- Git
- Ollama (для GGUF): <https://ollama.com/download>

## 3) Сборка проекта на Windows

В PowerShell из корня репозитория:

```powershell
.\build_windows.ps1
```

Скрипт выполняет полный pipeline:

1. создаёт `.venv`;
2. ставит зависимости;
3. готовит корпус (`prepare_corpus.py`, `prepare_doc_files.py`);
4. собирает `processed/chunks.jsonl`;
5. строит `processed/lexical_index.json`.

## 4) Импорт и тест Qwen3-8B-GGUF через Ollama

### 4.1 Импорт GGUF

```powershell
.\import_qwen3_8b_gguf_ollama.ps1 -GgufPath "D:\models\Qwen3-8B-Instruct.gguf" -ModelName "qwen3-8b-gguf"
```

### 4.2 Использование модели в приложении

```powershell
$env:OLLAMA_MODEL = "qwen3-8b-gguf"
.\run_windows.ps1
```

В UI можно оставить backend `ollama` или переключаться на `yandex_openai` для сравнительных прогонов.

## 5) LoRA: дообучение и перенос адаптера

### 5.1 Подготовка датасета

```powershell
.venv\Scripts\python.exe scripts\build_lora_dataset.py `
  --input processed\qa_history.jsonl `
  --out-train data\lora\train.jsonl `
  --out-eval data\lora\eval.jsonl `
  --eval-ratio 0.1
```

### 5.2 Дообучение в Colab

- Ноутбук: `notebooks/lora_qlora_colab.ipynb`
- Загружаем `data/lora/train.jsonl`, `data/lora/eval.jsonl`
- На выходе: папка адаптера LoRA

### 5.3 Применение адаптера локально

```powershell
.venv\Scripts\python.exe scripts\lora_infer_local.py `
  --base-model Qwen/Qwen2.5-1.5B-Instruct `
  --adapter-path "D:\adapters\my-lora" `
  --question "Какие документы нужны для получения лицензии?"
```

> Примечание: GGUF-пайплайн (Ollama) и HF+PEFT LoRA-пайплайн — это разные технологические ветки. Для LoRA-инференса нужен base model в формате transformers.

## 6) Рекомендуемый smoke-test на Windows

1. `.\build_windows.ps1`
2. импорт GGUF и запуск Ollama-модели
3. `.\run_windows.ps1`
4. в UI проверить:
   - retrieval по 2-3 контрольным вопросам;
   - корректность блока `### Источники`;
   - отсутствие критичных фактических ошибок.

## 7) Рекомендации по релизу

- перед push не включать локальные генерируемые файлы;
- фиксировать в release notes:
  - версия индекса/корпуса;
  - модель (`OLLAMA_MODEL`);
  - дата последней валидации набора вопросов.
