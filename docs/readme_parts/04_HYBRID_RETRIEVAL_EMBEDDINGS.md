# 04. Hybrid Retrieval: TF-IDF + Embeddings Re-rank

## Зачем нужен гибрид

TF-IDF хорошо работает по точным лексическим совпадениям, но хуже справляется с:

- перефразировками;
- синонимами;
- "похожим смыслом" без совпадающих ключевых слов.

Embeddings re-rank решает это, но дороже и требует API.

Итоговая стратегия:

1) дешево отобрать кандидатов TF-IDF;  
2) точечно переразложить top-N через embeddings similarity.

## Текущая реализация

В `app.py` добавлен этап:

- вход: `scored` из lexical retrieval;
- берутся первые `top_n` кандидатов (UI slider);
- считается embedding вопроса и каждого candidate chunk;
- финальный score = blend(lexical_norm, embedding_norm);
- список сортируется заново;
- "хвост" кандидатов ниже `top_n` сохраняется как есть.

## Кэш эмбеддингов

Кэш хранится в `processed/embedding_cache.json`.

Ключ кэша:

- `folder::model` + hash нормализованного текста.

Кэшируются:

- embedding вопроса;
- embeddings candidate chunks.

Это позволяет:

- не платить API повторно за один и тот же контент;
- ускорить повторные запросы и тесты.

## Настройки в UI

- `Embeddings re-rank (гибридный retrieval)` — включить/выключить.
- `Embeddings re-rank top-N кандидатов` — диапазон 10..80.
- `Yandex embedding model` — например `text-search-query/latest`.

## Рекомендуемые параметры

Стартовый профиль:

- `top_k=6`
- `embeddings_top_n=40`
- `emb_weight=0.35` (в коде)

Если API медленный/дорогой:

- снизить `embeddings_top_n` до 20..30.

Если много "мимо контекста":

- повысить lexical dominance (уменьшить `emb_weight` до 0.25).

## Поведение при ошибках API

Если embeddings недоступны:

- retrieval не падает;
- система автоматически работает как TF-IDF-only;
- пользователю добавляется диагностический блок, что re-rank отключен для запроса.

## Практика оценки качества

Для сравнения рекомендуется A/B на фиксированном списке вопросов:

- A: TF-IDF only;
- B: TF-IDF + embeddings re-rank.

Метрики:

- hit@k по эталонным документам;
- доля ответов без "Недостаточно данных";
- экспертная оценка юридической релевантности.

## Ограничения текущей версии

- embeddings берутся из внешнего API;
- нет автоматического budget cap в день/час;
- re-rank работает только для первого retrieval-пула (что обычно достаточно).

## Что улучшить дальше

- добавить лимитер на число embedding вызовов за сессию;
- добавить offline local embedding fallback;
- добавить persisted stats по hit-rate до и после re-rank.

## Быстрый operational чек-лист

- ключ/папка/модель заданы;
- `processed/embedding_cache.json` создается и растет;
- latency приемлема для выбранного `top_n`;
- в логах есть `embedding_diag` с `used=true`.

## Связанные разделы

- общий pipeline: `03_APP_AND_RAG_PIPELINE.md`
- эксплуатация и диагностика: `06_OPERATION_MONITORING_TROUBLESHOOTING.md`
