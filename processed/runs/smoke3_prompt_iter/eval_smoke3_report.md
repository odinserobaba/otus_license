# Yandex Cloud: прогон eval-набора

- Время (UTC): `2026-04-21T07:42:39.232648+00:00`
- LLM backend: `yandex_openai`
- Модель: `yandexgpt-5-lite/latest`
- Embeddings: `text-search-query/latest`, top-N=80, re-rank=ON
- Retrieval: top_k=12, multi_step=ON, official_only=True
- max_output_tokens: 1200

## Сводка

| id | Тема | Попадание expected | Оценка | Подозр. № | Вердикт |
|---|---|---|---|---|---|
| q05 | основания отказа | 1/2 | 0.50 | 0 | partial |
| q15 | перечень оборудования | 3/3 | 1.00 | 1 | ok |
| q23 | канал подачи | 2/2 | 1.00 | 0 | ok |

Итого: ok=2, partial=1, bad=0 (из 3).

Эвристика: доля вхождений `expected_sources` в тексте ответа (нижний регистр); «подозрительные» номера — вне короткого whitelist проекта.

Полные ответы: `processed/runs/smoke3_prompt_iter/eval_smoke3.jsonl`