#!/usr/bin/env python3
"""
Прогон набора вопросов через app.answer с выбранным LLM-бэкендом и эвристической оценкой.

Пример (Yandex Cloud):
  YANDEX_CLOUD_MODEL=yandexgpt-5-lite/latest \\
  YANDEX_CLOUD_MAX_TOKENS=4000 \\
  ./.venv/bin/python scripts/eval_yandex_suite.py \\
    --questions data/test/eval_questions.jsonl \\
    --out-jsonl processed/yandex_eval_20.jsonl \\
    --out-md processed/yandex_eval_20_report.md

Пример (AITUNNEL, Qwen 3.5 9B, ключ только из окружения):
  AITUNNEL_API_KEY=sk-aitunnel-... \\
  ./.venv/bin/python scripts/eval_yandex_suite.py \\
    --llm-backend aitunnel_openai \\
    --questions data/test/eval_questions.jsonl \\
    --out-jsonl processed/aitunnel_qwen35_9b_eval.jsonl \\
    --out-md processed/aitunnel_qwen35_9b_eval_report.md
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app as app_module  # noqa: E402


def expected_sources_gap(answer: str, expected: list[str]) -> list[str]:
    """Токены из expected_sources, не встретившиеся в тексте ответа (для ручной верификации)."""
    low = (answer or "").lower()
    missing: list[str] = []
    for token in expected:
        t = (token or "").strip()
        if not t:
            continue
        if t.lower() not in low:
            missing.append(t)
    return missing


def heuristic_score(answer: str, expected: list[str]) -> tuple[float, int, int]:
    low = (answer or "").lower()
    hits = 0
    for token in expected:
        t = (token or "").strip().lower()
        if not t:
            continue
        if t in low:
            hits += 1
    n = len([x for x in expected if (x or "").strip()])
    if n == 0:
        return 1.0, 0, 0
    return hits / n, hits, n


def suspicious_doc_hits(text: str) -> list[str]:
    """Грубая эвристика: номера НПА в ответе, которых нет в типовом наборе проекта."""
    known = {
        "171",
        "199",
        "2466",
        "1720",
        "648",
        "735",
        "268",
        "398",
        "402",
        "405",
        "397",
        "423",
        "453",
        "99",
    }
    found = set(re.findall(r"№\s*(\d{3,4})\b", text, flags=re.IGNORECASE))
    found |= set(re.findall(r"\b(\d{3,4})-ФЗ\b", text, flags=re.IGNORECASE))
    return sorted(x for x in found if x not in known)


def verdict_from_score(ratio: float, susp: list[str]) -> str:
    if susp and len(susp) >= 3:
        # Strong content hit but noisy references -> partial, not hard fail.
        return "partial" if ratio >= 0.85 else "bad"
    if ratio >= 0.85:
        return "ok"
    if ratio >= 0.5:
        return "partial"
    return "bad"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--questions", default="data/test/eval_questions.jsonl")
    parser.add_argument("--out-jsonl", default="processed/yandex_eval_20.jsonl")
    parser.add_argument("--out-md", default="processed/yandex_eval_20_report.md")
    parser.add_argument(
        "--out-qa",
        default="processed/yandex_eval_20_qa.md",
        help="Файл только с парами вопрос-ответ (Markdown).",
    )
    parser.add_argument(
        "--llm-backend",
        default="yandex_openai",
        choices=["yandex_openai", "aitunnel_openai"],
        help="Бэкенд генерации (embeddings re-rank по-прежнему через Yandex, если задан ключ)",
    )
    parser.add_argument(
        "--answer-mode",
        default="full",
        choices=["full", "concise", "user"],
        help="Режим ответа app.answer",
    )
    parser.add_argument("--top-k", type=int, default=12)
    parser.add_argument("--embeddings-top-n", type=int, default=80)
    parser.add_argument(
        "--full-corpus",
        action="store_true",
        help="Не ограничивать выборку только НПА (official_only=False), подтянуть guide/прочее",
    )
    parser.add_argument(
        "--exclude-topics",
        default="",
        help="Список тем через запятую для исключения из прогона (пример: розница,помещения)",
    )
    parser.add_argument(
        "--exclude-ids",
        default="",
        help="Список id вопросов через запятую для исключения из прогона (пример: q06,q08)",
    )
    args = parser.parse_args()

    qpath = ROOT / args.questions
    out_jsonl = ROOT / args.out_jsonl
    out_md = ROOT / args.out_md
    out_qa = ROOT / args.out_qa
    out_jsonl.parent.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    with qpath.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))

    exclude_topics = {
        x.strip().lower()
        for x in (args.exclude_topics or "").split(",")
        if x.strip()
    }
    exclude_ids = {
        x.strip().lower()
        for x in (args.exclude_ids or "").split(",")
        if x.strip()
    }
    if exclude_topics or exclude_ids:
        filtered_rows: list[dict] = []
        for rec in rows:
            topic = str(rec.get("topic") or "").strip().lower()
            qid = str(rec.get("id") or "").strip().lower()
            if topic in exclude_topics or qid in exclude_ids:
                continue
            filtered_rows.append(rec)
        rows = filtered_rows

    llm_backend = args.llm_backend
    gen_model = (
        app_module.DEFAULT_AITUNNEL_MODEL
        if llm_backend == "aitunnel_openai"
        else app_module.DEFAULT_YANDEX_MODEL
    )
    max_out = (
        app_module.AITUNNEL_MAX_OUTPUT_TOKENS
        if llm_backend == "aitunnel_openai"
        else app_module.YANDEX_MAX_OUTPUT_TOKENS
    )
    meta = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "llm_backend": llm_backend,
        "model": gen_model,
        "embedding_model": app_module.DEFAULT_YANDEX_EMBEDDING_MODEL,
        "max_output_tokens": max_out,
        "top_k": args.top_k,
        "embeddings_top_n": args.embeddings_top_n,
        "official_only": not args.full_corpus,
        "multi_step_retrieval": True,
        "use_embeddings_rerank": True,
        "answer_mode": args.answer_mode,
        "exclude_topics": sorted(exclude_topics),
        "exclude_ids": sorted(exclude_ids),
        "questions_total": len(rows),
    }

    summary_rows: list[dict] = []

    qa_lines = [
        f"# QA dump ({llm_backend})",
        "",
        f"- Время (UTC): `{meta['ts']}`",
        f"- Модель: `{meta['model']}`",
        "",
    ]

    with out_jsonl.open("w", encoding="utf-8") as jout:
        jout.write(json.dumps({"type": "run_meta", **meta}, ensure_ascii=False) + "\n")
        for rec in rows:
            qid = rec.get("id", "")
            question = rec.get("question", "")
            expected = rec.get("expected_sources") or []
            topic = rec.get("topic", "")

            reply = app_module.answer(
                question=question,
                history=[],
                top_k=args.top_k,
                official_only=not args.full_corpus,
                use_embeddings_rerank=True,
                embeddings_top_n=args.embeddings_top_n,
                use_llm=True,
                llm_backend=llm_backend,
                llm_model=app_module.DEFAULT_OLLAMA_MODEL,
                lora_base_model=app_module.DEFAULT_LORA_BASE_MODEL,
                lora_adapter_path=app_module.DEFAULT_LORA_ADAPTER_PATH,
                yandex_api_key=app_module.DEFAULT_YANDEX_API_KEY,
                yandex_folder=app_module.DEFAULT_YANDEX_FOLDER,
                yandex_model=app_module.DEFAULT_YANDEX_MODEL,
                yandex_embedding_model=app_module.DEFAULT_YANDEX_EMBEDDING_MODEL,
                enable_logging=False,
                show_reasoning=True,
                multi_step_retrieval=True,
                answer_mode=args.answer_mode,
                aitunnel_api_key=app_module.DEFAULT_AITUNNEL_API_KEY,
                aitunnel_base_url=app_module.DEFAULT_AITUNNEL_BASE_URL,
                aitunnel_model=app_module.DEFAULT_AITUNNEL_MODEL,
            )

            ratio, hits, nexp = heuristic_score(reply, expected)
            susp = suspicious_doc_hits(reply)
            v = verdict_from_score(ratio, susp)
            gap = expected_sources_gap(reply, expected)
            out_rec = {
                "id": qid,
                "topic": topic,
                "question": question,
                "expected_sources": expected,
                "expected_sources_missing_in_answer": gap,
                "answer": reply,
                "score_ratio": round(ratio, 3),
                "expected_hits": hits,
                "expected_total": nexp,
                "suspicious_doc_numbers": susp,
                "verdict": v,
            }
            jout.write(json.dumps(out_rec, ensure_ascii=False) + "\n")
            qa_lines.extend(
                [
                    f"## {qid} — {topic}",
                    "",
                    f"**Вопрос:** {question}",
                    "",
                    "**Ответ:**",
                    "",
                    reply.strip(),
                    "",
                    "---",
                    "",
                ]
            )
            summary_rows.append(
                {
                    "id": qid,
                    "topic": topic,
                    "hit_ratio": f"{hits}/{nexp}",
                    "score": f"{ratio:.2f}",
                    "susp": len(susp),
                    "verdict": v,
                }
            )

    title = (
        "AITUNNEL (OpenAI-совместимый): прогон eval-набора"
        if llm_backend == "aitunnel_openai"
        else "Yandex Cloud: прогон eval-набора"
    )
    # Markdown report
    lines = [
        f"# {title}",
        "",
        f"- Время (UTC): `{meta['ts']}`",
        f"- LLM backend: `{meta['llm_backend']}`",
        f"- Модель: `{meta['model']}`",
        f"- Embeddings: `{meta['embedding_model']}`, top-N={meta['embeddings_top_n']}, re-rank=ON",
        f"- Retrieval: top_k={meta['top_k']}, multi_step=ON, official_only={meta['official_only']}",
        f"- max_output_tokens: {meta['max_output_tokens']}",
        "",
        "## Сводка",
        "",
        "| id | Тема | Попадание expected | Оценка | Подозр. № | Вердикт |",
        "|---|---|---|---|---|---|",
    ]
    for s in summary_rows:
        lines.append(
            f"| {s['id']} | {s['topic']} | {s['hit_ratio']} | {s['score']} | {s['susp']} | {s['verdict']} |"
        )
    ok = sum(1 for s in summary_rows if s["verdict"] == "ok")
    partial = sum(1 for s in summary_rows if s["verdict"] == "partial")
    bad = sum(1 for s in summary_rows if s["verdict"] == "bad")
    lines.extend(
        [
            "",
            f"Итого: ok={ok}, partial={partial}, bad={bad} (из {len(summary_rows)}).",
            "",
            "Эвристика: доля вхождений `expected_sources` в тексте ответа (нижний регистр); "
            "«подозрительные» номера — вне короткого whitelist проекта.",
            "",
            f"Полные ответы: `{out_jsonl.relative_to(ROOT)}`",
        ]
    )
    out_md.write_text("\n".join(lines), encoding="utf-8")
    out_qa.write_text("\n".join(qa_lines), encoding="utf-8")
    print(f"Wrote {out_jsonl}, {out_md} and {out_qa}")


if __name__ == "__main__":
    main()
