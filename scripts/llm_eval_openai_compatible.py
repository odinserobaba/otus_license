#!/usr/bin/env python3
"""
Локальный lexical RAG + генерация через OpenAI-совместимый API (например api.aitunnel.ru).

Переменные окружения:
  OPENAI_API_KEY    — обязательно
  OPENAI_BASE_URL   — например https://api.aitunnel.ru/v1/ (со слэшем в конце как в SDK)

Пример:
  export OPENAI_API_KEY="..."
  export OPENAI_BASE_URL="https://api.aitunnel.ru/v1/"
  cd /path/to/license_rag && .venv/bin/python scripts/llm_eval_openai_compatible.py \\
    --model qwen3.5-9b --output processed/eval_aitunnel.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from llm_eval_local import build_prompt, score_query, select_matches  # noqa: E402

try:
    from openai import OpenAI
except ImportError as e:
    raise SystemExit("pip install openai") from e


def chat_generate(
    client: OpenAI,
    model: str,
    user_content: str,
    *,
    max_tokens: int,
    temperature: float,
) -> str:
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Ты юридический ассистент по лицензированию ЕГАИС. "
                        "Следуй инструкциям и контексту в сообщении пользователя."
                    ),
                },
                {"role": "user", "content": user_content},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        choice = response.choices[0].message
        text = (choice.content or "").strip()
        # У qwen3.5 и др. часть токенов уходит в reasoning; при малом max_tokens content бывает пустым.
        if not text and getattr(choice, "reasoning", None):
            text = (choice.reasoning or "").strip()
        return text
    except Exception as e:
        return f"[OPENAI API ERROR] {e}"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="RAG eval via OpenAI-compatible Chat Completions (e.g. aitunnel.ru)"
    )
    parser.add_argument("--index", default="processed/lexical_index.json")
    parser.add_argument("--questions", default="data/test/eval_questions.jsonl")
    parser.add_argument(
        "--top-k",
        type=int,
        default=0,
        help="Число чанков; 0 вместе с бюджетом = режим как в single_query (см. --prompt-char-budget).",
    )
    parser.add_argument(
        "--max-chunks-cap",
        type=int,
        default=500,
        help="Верхняя граница числа чанков.",
    )
    parser.add_argument(
        "--prompt-char-budget",
        type=int,
        default=400_000,
        help="Бюджет символов контекста; 0 = только --top-k и --max-chunks-cap (классический режим).",
    )
    parser.add_argument(
        "--max-chunk-chars",
        type=int,
        default=0,
        help="Обрезка текста чанка; 0 = полный текст фрагмента.",
    )
    parser.add_argument("--model", default="qwen3.5-9b")
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=16384,
        help="max_tokens (reasoning-модели нуждаются в большом лимите)",
    )
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument(
        "--timeout",
        type=float,
        default=600.0,
        help="Таймаут HTTP на один запрос (сек)",
    )
    parser.add_argument("--output", default="processed/eval_openai_compatible.jsonl")
    args = parser.parse_args()

    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise SystemExit(
            "Задайте OPENAI_API_KEY (например: export OPENAI_API_KEY='...')"
        )
    base_url = (
        os.environ.get("OPENAI_BASE_URL", "https://api.aitunnel.ru/v1/").strip()
    )
    if not base_url.endswith("/"):
        base_url += "/"

    project_root = Path(__file__).resolve().parents[1]
    index_path = project_root / args.index
    questions_path = project_root / args.questions
    out_path = project_root / args.output

    with index_path.open("r", encoding="utf-8") as f:
        index = json.load(f)

    questions: list[dict] = []
    with questions_path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                questions.append(json.loads(line))

    client = OpenAI(api_key=api_key, base_url=base_url, timeout=args.timeout)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    chunk_limit = None if args.max_chunk_chars <= 0 else args.max_chunk_chars
    meta = {
        "base_url": base_url,
        "model": args.model,
        "max_tokens": args.max_tokens,
        "temperature": args.temperature,
        "top_k": args.top_k,
        "max_chunks_cap": args.max_chunks_cap,
        "prompt_char_budget": args.prompt_char_budget,
        "max_chunk_chars": args.max_chunk_chars,
    }

    with out_path.open("w", encoding="utf-8") as out:
        out.write(json.dumps({"type": "run_meta", **meta}, ensure_ascii=False) + "\n")
        for q in questions:
            question = q["question"]
            ranked = score_query(question, index)
            if args.prompt_char_budget > 0:
                matches = select_matches(
                    ranked,
                    top_k=args.top_k,
                    max_chunks_cap=args.max_chunks_cap,
                    prompt_char_budget=args.prompt_char_budget,
                )
            elif args.top_k <= 0:
                matches = ranked[: args.max_chunks_cap]
            else:
                matches = ranked[: args.top_k]
            user_prompt = build_prompt(question, matches, max_chunk_chars=chunk_limit)
            answer = chat_generate(
                client,
                args.model,
                user_prompt,
                max_tokens=args.max_tokens,
                temperature=args.temperature,
            )
            record = {
                "id": q["id"],
                "question": question,
                "top_k": args.top_k,
                "max_chunks_cap": args.max_chunks_cap,
                "prompt_char_budget": args.prompt_char_budget,
                "chunks_used": len(matches),
                "ranked_available": len(ranked),
                "prompt_chars": len(user_prompt),
                "model": args.model,
                "retrieved_sources": [
                    m[1].get("metadata", {}).get("source_file", "n/a") for m in matches
                ],
                "answer": answer,
            }
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
            print(f"Done: {q['id']}")

    print(f"Saved: {out_path}")


if __name__ == "__main__":
    main()
