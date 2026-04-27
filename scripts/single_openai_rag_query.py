#!/usr/bin/env python3
"""Один вопрос: lexical RAG + OpenAI-совместимый чат. Результат — JSON в --output."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from llm_eval_local import build_prompt, score_query, select_matches  # noqa: E402

from openai import OpenAI  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--id",
        default="",
        help="id вопроса из eval_questions.jsonl (например q02); иначе первая строка",
    )
    p.add_argument("--index", default="processed/lexical_index.json")
    p.add_argument("--questions", default="data/test/eval_questions.jsonl")
    p.add_argument(
        "--top-k",
        type=int,
        default=0,
        help="Сколько чанков. 0 = максимум до --max-chunks-cap (полный список после TF-IDF).",
    )
    p.add_argument(
        "--max-chunks-cap",
        type=int,
        default=500,
        help="Максимум чанков (и при бюджете символов).",
    )
    p.add_argument(
        "--prompt-char-budget",
        type=int,
        default=400_000,
        help="Суммарный ориентир размера контекста в символах (0 = без бюджета, только --max-chunks-cap).",
    )
    p.add_argument(
        "--max-chunk-chars",
        type=int,
        default=0,
        help="Символов на чанк; 0 = без обрезки (весь текст фрагмента).",
    )
    p.add_argument("--model", default="qwen3.5-9b")
    p.add_argument("--max-tokens", type=int, default=8192)
    p.add_argument("--temperature", type=float, default=0.2)
    p.add_argument("--timeout", type=float, default=600.0)
    p.add_argument("--output", default="processed/single_query_response.json")
    args = p.parse_args()

    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("export OPENAI_API_KEY=...")
    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.aitunnel.ru/v1/").strip()
    if not base_url.endswith("/"):
        base_url += "/"

    root = Path(__file__).resolve().parents[1]
    idx = json.loads((root / args.index).read_text(encoding="utf-8"))
    rows = []
    for line in (root / args.questions).read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    if args.id:
        rec = next((r for r in rows if r.get("id") == args.id), None)
        if not rec:
            raise SystemExit(f"id не найден: {args.id}")
    else:
        rec = rows[0]

    q = rec["question"]
    ranked = score_query(q, idx)
    budget = args.prompt_char_budget
    matches = select_matches(
        ranked,
        top_k=args.top_k,
        max_chunks_cap=args.max_chunks_cap,
        prompt_char_budget=budget,
    )
    chunk_limit = None if args.max_chunk_chars <= 0 else args.max_chunk_chars
    user_prompt = build_prompt(q, matches, max_chunk_chars=chunk_limit)

    client = OpenAI(api_key=api_key, base_url=base_url, timeout=args.timeout)
    resp = client.chat.completions.create(
        model=args.model,
        messages=[
            {
                "role": "system",
                "content": (
                    "Ты юридический ассистент по лицензированию ЕГАИС. "
                    "Следуй инструкциям и контексту в сообщении пользователя."
                ),
            },
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=args.max_tokens,
        temperature=args.temperature,
    )
    msg = resp.choices[0].message
    answer = (msg.content or "").strip()
    if not answer and getattr(msg, "reasoning", None):
        answer = (msg.reasoning or "").strip()

    out = {
        "id": rec.get("id"),
        "question": q,
        "model": args.model,
        "top_k_requested": args.top_k,
        "max_chunks_cap": args.max_chunks_cap,
        "prompt_char_budget": budget,
        "chunks_used": len(matches),
        "ranked_available": len(ranked),
        "max_chunk_chars": args.max_chunk_chars,
        "prompt_chars": len(user_prompt),
        "retrieved_sources": [
            m[1].get("metadata", {}).get("source_file", "n/a") for m in matches
        ],
        "answer": answer,
        "usage": resp.usage.model_dump() if resp.usage else None,
        "finish_reason": resp.choices[0].finish_reason,
    }
    outp = root / args.output
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {outp}")
    print("--- answer preview ---")
    print(answer[:1200] + ("..." if len(answer) > 1200 else ""))


if __name__ == "__main__":
    main()
