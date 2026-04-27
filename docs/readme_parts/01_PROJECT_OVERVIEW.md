# 01. Project Overview

## Цель проекта

Собрать локального юридического ассистента по лицензированию ЕГАИС, который:

- отвечает на вопросы на базе локального корпуса НПА и методических материалов;
- показывает, из каких источников взята информация;
- минимизирует галлюцинации за счет retrieval-first подхода;
- поддерживает два режима качества:
  - быстрый локальный (CPU),
  - усиленный (embeddings re-rank + LLM API + LoRA-адаптер).

## Почему выбран такой стек

Проект изначально создавался при ограниченных вычислительных ресурсах.  
Поэтому архитектура построена вокруг принципа "дешевый baseline + усилители по необходимости":

- baseline retrieval: TF-IDF по локальному индексу;
- усилитель качества retrieval: embeddings re-rank только для top-N кандидатов;
- усилитель качества генерации: LLM backend (локальный Ollama или Yandex Cloud);
- усилитель роли/стиля: LoRA-адаптер, обучаемый в Colab (QLoRA).

## Архитектурная схема (логически)

1) `doc/*` -> 2) preprocess -> 3) `processed/cleaned_docs.jsonl` ->  
4) chunking -> 5) `processed/chunks.jsonl` -> 6) TF-IDF index ->  
7) online query:

- lexical retrieval;
- optional embeddings re-rank;
- optional multi-step follow-up retrieval;
- prompt assembly;
- LLM generation;
- validation/post-processing;
- final answer + citations.

## Слои системы

### 1. Ingestion слой (документы)

Поддерживаются форматы:

- RTF (включая MHTML-вставки),
- DOC/DOCX,
- TXT/MD,
- PDF.

Ключевая особенность: спец-обработка `license.txt` отдельным разметчиком, чтобы списки документов не ломались на случайных границах секций.

### 2. Metadata слой (обогащение)

В процессе подготовки выделяются поля:

- `doc_type`, `doc_number_*`, `doc_date_file`, `doc_title`, `doc_citation`;
- `section_title`, `section_index`, `section_page_*`;
- для законов: `article_number`, `article_title`, `subpoint_refs`, `cited_article_refs`;
- retrieval-поля: `source_kind`, `procedure_type`, `topic_tags`.

Это дает адресный поиск и устойчивое цитирование "человеческими" названиями.

### 3. Retrieval слой

- основной поиск: TF-IDF;
- правила-бустеры по intent/entities/tags;
- optional re-rank embeddings для top-N;
- optional multi-step follow-up queries;
- optional deterministic anchors (в т.ч. прямой pull статьи закона по метаданным).

### 4. Generation слой

- prompt с жесткими правилами "только по контексту";
- структурированный формат ответа;
- валидация на наличие ключевых сущностей;
- пост-процессинг: удаление мусорных ссылок и дедупликация источников.

### 5. UI слой (Gradio)

Пользователь управляет:

- `top_k`, `official_only`,
- `LLM backend`, `model`,
- `Embeddings re-rank`, `top-N`,
- `multi-step retrieval`,
- `show_reasoning`,
- логированием.

## Текущие сильные стороны решения

- Полностью рабочий локальный pipeline сборки и запуска.
- Стабильная обработка гетерогенного корпуса.
- Встроенная защита от части галлюцинаций и нерелевантных ссылок.
- Подготовленная дорожка к LoRA без слома существующей системы.

## Текущие ограничения

- TF-IDF baseline хуже обобщает синонимы/перефразировки.
- API embeddings добавляет сетевую зависимость (хоть и кэшируется).
- LoRA-подход требует аккуратной фильтрации train-данных, иначе учится "шум".
- Юридические ответы по-прежнему требуют финальной проверки человеком.

## Рекомендуемый режим для реальной работы

- для повседневных запросов:
  - `official_only=true`,
  - embeddings re-rank включать точечно на сложные вопросы;
- для демонстрации преподавателю:
  - показать A/B: TF-IDF only vs TF-IDF + embeddings,
  - затем показать LoRA-версию ответа на одинаковом retrieval-контексте.

## Связанные разделы

- техническая подготовка корпуса: `02_DATA_PREPARATION_AND_INDEX.md`
- поведение приложения в рантайме: `03_APP_AND_RAG_PIPELINE.md`
- гибридный retrieval: `04_HYBRID_RETRIEVAL_EMBEDDINGS.md`
- LoRA-конвейер: `05_LORA_WORKFLOW_END_TO_END.md`
