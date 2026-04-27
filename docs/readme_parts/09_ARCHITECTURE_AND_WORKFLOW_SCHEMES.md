# 09. Architecture and Workflow Schemes

Ниже — сводные схемы того, как устроен проект и какие этапы были реализованы.

## 1) End-to-end pipeline

```mermaid
flowchart TD
    A[doc/* NPA files] --> B[prepare_corpus.py / prepare_doc_files.py]
    B --> C[processed/cleaned_docs*.jsonl]
    C --> D[chunk_corpus.py]
    D --> E[processed/chunks.jsonl]
    E --> F[build_index.py]
    F --> G[processed/lexical_index.json]
    G --> H[app.py / Gradio]
    H --> I[TF-IDF retrieval]
    I --> J[optional embeddings rerank]
    J --> K[prompt assembly]
    K --> L[LLM backend: ollama/yandex/local_lora]
    L --> M[post-processing + source validation]
    M --> N[final answer + sources]
```

## 2) Online query path (runtime)

```mermaid
sequenceDiagram
    participant U as User
    participant UI as Gradio UI
    participant R as Retrieval
    participant L as LLM
    participant V as Validators

    U->>UI: question
    UI->>R: score_query + top_k
    R->>R: optional embeddings re-rank
    R->>R: optional multi-step follow-up retrieval
    R-->>UI: matched chunks
    UI->>L: prompt(context + INSTRUCT)
    L-->>UI: draft answer
    UI->>V: critical fact guard + strict sources
    V-->>UI: sanitized answer
    UI-->>U: final answer with verified sources
```

## 3) Source validation / anti-hallucination

```mermaid
flowchart LR
    A[LLM draft answer] --> B[extract referenced doc numbers]
    B --> C[compare with allowed numbers from matches]
    C -->|unverified refs found| D[sanitize unverified refs]
    D --> E[rebuild sources block from matches only]
    C -->|clean| E
    E --> F[append diagnostics in logs]
    F --> G[return final answer]
```

## 4) LoRA workflow

```mermaid
flowchart TD
    A[processed/qa_history.jsonl] --> B[build_lora_dataset.py]
    B --> C[data/lora/train.jsonl + eval.jsonl]
    C --> D[Colab QLoRA training]
    D --> E[adapter output]
    E --> F[lora_infer_local.py / app local_lora backend]
```

## 5) Deployment matrix

```mermaid
flowchart TD
    A[GitHub repo] --> B[Linux setup]
    A --> C[Windows setup]

    B --> B1[build.sh]
    B --> B2[run.sh]

    C --> C1[build_windows.ps1]
    C --> C2[import_qwen3_8b_gguf_ollama.ps1]
    C --> C3[run_windows.ps1]
```

## 6) Testing and regression loop

```mermaid
flowchart LR
    A[Code change] --> B[pytest regression tests]
    B --> C[20-question eval suite]
    C --> D[compare KPI: ok/partial/bad + suspicious]
    D --> E{Quality acceptable?}
    E -->|No| F[adjust prompt/retrieval/validators]
    F --> B
    E -->|Yes| G[release/push]
```

## 7) Что важно сохранять при дальнейшей доработке

- разделять качество retrieval и качество генерации;
- удерживать критические guardrail-правила;
- контролировать `suspicious_doc_numbers` как отдельную метрику риска;
- фиксировать все изменения через единый regression-run.

## 8) Final runtime schema (YandexGPT-5-lite baseline)

```mermaid
flowchart TD
    U[User in Web UI] --> A[app.py answer()]
    A --> B[score_query TF-IDF top_k=12]
    B --> C[embeddings re-rank top_n=80]
    C --> D[multi-step retrieval planner]
    D --> E[build prompt with INSTRUCT + context]
    E --> F[Yandex OpenAI endpoint]
    F --> G[Model: gpt://folder/yandexgpt-5-lite/latest]
    G --> H[LLM draft answer]
    H --> I[critical fact guard]
    I --> J[sanitize unverified refs]
    J --> K[strict sources reconstruction from matches]
    K --> L[official links + disclaimer]
    L --> M[final answer to UI]

    C --> C1{embedding failure?}
    C1 -->|yes| C2[fallback to lexical TF-IDF]
    C2 --> D
    F --> F1{SDK encoding/connection issue?}
    F1 -->|yes| F2[UTF-8 HTTP fallback + retry]
    F2 --> G
```

Recommended baseline parameters:
- backend: `yandex_openai`
- model: `yandexgpt-5-lite/latest`
- `top_k=12`
- `official_only=true`
- `embeddings_rerank=true`
- `embeddings_top_n=80`
- `multi_step_retrieval=true`
- `answer_mode=full`
