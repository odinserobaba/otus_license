# Final Schema: YandexGPT-5-lite

```mermaid
sequenceDiagram
    participant U as User
    participant UI as Gradio UI
    participant R as Retrieval
    participant E as Embeddings re-rank
    participant P as Planner
    participant Y as YandexGPT-5-lite
    participant V as Validators

    U->>UI: Вопрос
    UI->>R: TF-IDF поиск (top_k=12)
    R->>E: Re-rank кандидатов (top_n=80)
    E-->>R: Пересортированные чанки (или fallback к TF-IDF)
    R->>P: Multi-step follow-up retrieval
    P-->>UI: Финальный context
    UI->>Y: Prompt(INSTRUCT + context)
    Y-->>UI: Draft answer
    UI->>V: Guardrails + source validation
    V-->>UI: Sanitized final answer
    UI-->>U: Ответ + источники + дисклеймер
```

## Runtime safeguards

- если `embeddings` недоступны: fallback на lexical retrieval без остановки ответа;
- если OpenAI SDK падает по кодировке (`ascii codec`): UTF-8 HTTP fallback;
- при connection/timeout: повторные попытки до fallback;
- `strict sources`: список источников пересобирается только из retrieval `matches`.

## Final baseline settings

- `llm_backend = yandex_openai`
- `yandex_model = yandexgpt-5-lite/latest`
- `top_k = 12`
- `official_only = true`
- `use_embeddings_rerank = true`
- `embeddings_top_n = 80`
- `multi_step_retrieval = true`
- `answer_mode = full`
