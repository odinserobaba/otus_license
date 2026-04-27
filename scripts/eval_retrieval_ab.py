#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import (  # noqa: E402
    INDEX,
    doc_label,
    rerank_with_embeddings,
    score_query,
    select_diverse_matches,
)


def normalize(text: str) -> str:
    return (text or "").strip().lower()


def load_questions(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def expected_hit(match_rows: list[tuple[float, dict]], expected_tokens: list[str]) -> bool:
    if not expected_tokens:
        return False
    expected = [normalize(x) for x in expected_tokens if normalize(x)]
    if not expected:
        return False
    for _, row in match_rows:
        meta = row.get("metadata", {}) or {}
        text = normalize(row.get("text", ""))
        label = normalize(doc_label(meta))
        hay = f"{label}\n{text}"
        if all(tok in hay for tok in expected):
            return True
    return False


def summarize(records: list[dict]) -> dict:
    total = len(records)
    if total == 0:
        return {
            "total": 0,
            "baseline_hit_rate": 0.0,
            "hybrid_hit_rate": 0.0,
            "improved_count": 0,
            "regressed_count": 0,
        }
    b_hits = sum(1 for r in records if r["baseline_hit"])
    h_hits = sum(1 for r in records if r["hybrid_hit"])
    improved = sum(1 for r in records if (not r["baseline_hit"]) and r["hybrid_hit"])
    regressed = sum(1 for r in records if r["baseline_hit"] and (not r["hybrid_hit"]))
    return {
        "total": total,
        "baseline_hit_rate": round(b_hits / total, 4),
        "hybrid_hit_rate": round(h_hits / total, 4),
        "improved_count": improved,
        "regressed_count": regressed,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="A/B eval for retrieval: TF-IDF baseline vs embeddings rerank")
    parser.add_argument("--questions", default="data/test/eval_questions.jsonl")
    parser.add_argument("--top-k", type=int, default=6)
    parser.add_argument("--official-only", action="store_true", default=True)
    parser.add_argument("--no-official-only", dest="official_only", action="store_false")
    parser.add_argument("--embeddings-top-n", type=int, default=40)
    parser.add_argument("--yandex-api-key", default="")
    parser.add_argument("--yandex-folder", default="")
    parser.add_argument("--embedding-model", default="text-search-query/latest")
    parser.add_argument("--output-jsonl", default="processed/eval_retrieval_ab.jsonl")
    parser.add_argument("--output-summary", default="processed/eval_retrieval_ab_summary.json")
    args = parser.parse_args()

    questions_path = Path(args.questions)
    rows = load_questions(questions_path)
    output_rows: list[dict] = []

    for q in rows:
        qid = q.get("id") or ""
        question = (q.get("question") or "").strip()
        expected_sources = q.get("expected_sources") or []
        if not question:
            continue

        baseline_scored = score_query(question, INDEX, official_only=bool(args.official_only), retrieval_text=question)
        baseline_matches = select_diverse_matches(baseline_scored, max(1, int(args.top_k)))

        hybrid_scored, emb_diag = rerank_with_embeddings(
            question,
            baseline_scored,
            api_key=(args.yandex_api_key or "").strip(),
            folder=(args.yandex_folder or "").strip(),
            model=(args.embedding_model or "").strip(),
            top_n=int(args.embeddings_top_n),
        )
        hybrid_matches = select_diverse_matches(hybrid_scored, max(1, int(args.top_k)))

        rec = {
            "id": qid,
            "question": question,
            "topic": q.get("topic"),
            "expected_sources": expected_sources,
            "baseline_hit": expected_hit(baseline_matches, expected_sources),
            "hybrid_hit": expected_hit(hybrid_matches, expected_sources),
            "embedding_diag": emb_diag,
            "baseline_sources": [doc_label((r.get("metadata") or {})) for _, r in baseline_matches],
            "hybrid_sources": [doc_label((r.get("metadata") or {})) for _, r in hybrid_matches],
        }
        output_rows.append(rec)

    summary = summarize(output_rows)
    summary["questions_file"] = str(questions_path)
    summary["top_k"] = int(args.top_k)
    summary["official_only"] = bool(args.official_only)
    summary["embeddings_top_n"] = int(args.embeddings_top_n)
    summary["embedding_model"] = args.embedding_model

    out_jsonl = Path(args.output_jsonl)
    out_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with out_jsonl.open("w", encoding="utf-8") as f:
        for rec in output_rows:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    out_summary = Path(args.output_summary)
    out_summary.parent.mkdir(parents=True, exist_ok=True)
    out_summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Saved details: {out_jsonl}")
    print(f"Saved summary: {out_summary}")


if __name__ == "__main__":
    main()
