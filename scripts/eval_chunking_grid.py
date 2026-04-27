#!/usr/bin/env python3
"""
Grid-eval for chunking params: rebuild chunks/index and compare retrieval completeness.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import doc_label, score_query, select_diverse_matches  # noqa: E402


@dataclass
class ChunkCfg:
    chunk_size: int
    overlap: int

    @property
    def name(self) -> str:
        return f"cs{self.chunk_size}_ov{self.overlap}"


LEGAL_ANCHOR_RE = re.compile(
    r"(171|99|199|398|397|405|402|423|2466|648|735|268|статья|пункт|лиценз|егаис)",
    re.IGNORECASE,
)
LIST_Q_RE = re.compile(r"(переч|спис|виды|видов|основан|требован)", re.IGNORECASE)
DOCS_SUBMIT_RE = re.compile(r"(документ|заявлен|подач|госуслуг|епгу|портал)", re.IGNORECASE)
REFUSAL_RE = re.compile(r"(отказ|отклон)", re.IGNORECASE)
EQUIP_RE = re.compile(r"(оборудован|перечень|коммуникац|фиксац)", re.IGNORECASE)


def normalize(text: str) -> str:
    return (text or "").strip().lower()


def parse_grid(grid: str) -> list[ChunkCfg]:
    out: list[ChunkCfg] = []
    for part in (grid or "").split(","):
        p = part.strip()
        if not p:
            continue
        if ":" not in p:
            raise ValueError(f"Bad grid item '{p}', expected chunk:overlap")
        cs, ov = p.split(":", 1)
        out.append(ChunkCfg(chunk_size=int(cs), overlap=int(ov)))
    if not out:
        raise ValueError("Grid is empty")
    return out


def load_questions(paths: list[Path]) -> list[dict]:
    rows: list[dict] = []
    for p in paths:
        with p.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rows.append(json.loads(line))
    return rows


def row_hay(matches: list[tuple[float, dict]]) -> str:
    parts: list[str] = []
    for _, row in matches:
        meta = row.get("metadata", {}) or {}
        parts.append(normalize(doc_label(meta)))
        parts.append(normalize(row.get("text", "")))
    return "\n".join(parts)


def strict_hit(matches: list[tuple[float, dict]], expected_tokens: list[str]) -> bool:
    expected = [normalize(x) for x in expected_tokens if normalize(x)]
    if not expected:
        return False
    for _, row in matches:
        meta = row.get("metadata", {}) or {}
        hay = f"{normalize(doc_label(meta))}\n{normalize(row.get('text', ''))}"
        if all(tok in hay for tok in expected):
            return True
    return False


def token_coverage(matches: list[tuple[float, dict]], expected_tokens: list[str]) -> float:
    expected = [normalize(x) for x in expected_tokens if normalize(x)]
    if not expected:
        return 0.0
    hay = row_hay(matches)
    hits = sum(1 for tok in expected if tok in hay)
    return hits / len(expected)


def avg_chunk_chars(matches: list[tuple[float, dict]]) -> float:
    vals = []
    for _, row in matches:
        meta = row.get("metadata", {}) or {}
        c = meta.get("chunk_chars")
        if isinstance(c, int):
            vals.append(c)
    return (sum(vals) / len(vals)) if vals else 0.0


def source_diversity(matches: list[tuple[float, dict]]) -> int:
    seen = set()
    for _, row in matches:
        meta = row.get("metadata", {}) or {}
        seen.add(str(meta.get("source_file") or doc_label(meta)))
    return len(seen)


def is_critical_question(question: str, expected: list[str]) -> bool:
    text = f"{question} {' '.join(expected or [])}"
    return LEGAL_ANCHOR_RE.search(text or "") is not None


def is_list_question(question: str, topic: str) -> bool:
    return bool(LIST_Q_RE.search(f"{question} {topic}"))


def slice_kind(question: str, topic: str) -> str | None:
    text = f"{question} {topic}".lower()
    if DOCS_SUBMIT_RE.search(text):
        return "docs_submission"
    if REFUSAL_RE.search(text):
        return "refusal"
    if EQUIP_RE.search(text):
        return "equipment_requirements"
    return None


def run_chunk_and_index(cfg: ChunkCfg, cleaned_docs: Path, work_dir: Path) -> Path:
    chunks_path = work_dir / f"chunks_{cfg.name}.jsonl"
    index_path = work_dir / f"lexical_index_{cfg.name}.json"

    subprocess.run(
        [
            str(ROOT / ".venv/bin/python"),
            str(ROOT / "scripts/chunk_corpus.py"),
            "--input-jsonl",
            str(cleaned_docs),
            "--output-jsonl",
            str(chunks_path),
            "--chunk-size",
            str(cfg.chunk_size),
            "--overlap",
            str(cfg.overlap),
        ],
        check=True,
        cwd=str(ROOT),
    )
    subprocess.run(
        [
            str(ROOT / ".venv/bin/python"),
            str(ROOT / "scripts/build_index.py"),
            "--chunks-jsonl",
            str(chunks_path),
            "--output",
            str(index_path),
        ],
        check=True,
        cwd=str(ROOT),
    )
    return index_path


def evaluate_cfg(cfg: ChunkCfg, index: dict, questions: list[dict], top_k: int, official_only: bool) -> dict:
    recs: list[dict] = []
    slices: dict[str, list[dict]] = {"docs_submission": [], "refusal": [], "equipment_requirements": []}
    for q in questions:
        question = str(q.get("question") or "").strip()
        expected = q.get("expected_sources") or []
        topic = str(q.get("topic") or "")
        if not question:
            continue
        scored = score_query(question, index, official_only=official_only, retrieval_text=question)
        matches = select_diverse_matches(scored, top_k=top_k)
        sh = strict_hit(matches, expected)
        cov = token_coverage(matches, expected)
        crit = is_critical_question(question, expected)
        rec = {
            "id": q.get("id"),
            "topic": topic,
            "strict_hit": sh,
            "coverage": round(cov, 3),
            "critical_miss": bool(crit and not sh),
            "source_diversity": source_diversity(matches),
            "avg_chunk_chars": round(avg_chunk_chars(matches), 1),
            "is_list_question": is_list_question(question, topic),
        }
        recs.append(rec)
        sk = slice_kind(question, topic)
        if sk:
            slices[sk].append(rec)
    total = len(recs) or 1
    list_rows = [r for r in recs if r.get("is_list_question")]
    slice_summary: dict[str, dict] = {}
    for key, rows in slices.items():
        n = len(rows)
        if n == 0:
            slice_summary[key] = {"questions": 0, "strict_hit_rate": 0.0, "avg_coverage": 0.0}
            continue
        slice_summary[key] = {
            "questions": n,
            "strict_hit_rate": round(sum(1 for r in rows if r["strict_hit"]) / n, 4),
            "avg_coverage": round(sum(r["coverage"] for r in rows) / n, 4),
        }
    return {
        "config": cfg.name,
        "chunk_size": cfg.chunk_size,
        "overlap": cfg.overlap,
        "questions_total": len(recs),
        "strict_hit_rate": round(sum(1 for r in recs if r["strict_hit"]) / total, 4),
        "avg_coverage": round(sum(r["coverage"] for r in recs) / total, 4),
        "critical_miss_count": sum(1 for r in recs if r["critical_miss"]),
        "avg_source_diversity": round(sum(r["source_diversity"] for r in recs) / total, 3),
        "avg_chunk_chars_in_topk": round(sum(r["avg_chunk_chars"] for r in recs) / total, 1),
        "list_question_hit_rate": round(sum(1 for r in list_rows if r["strict_hit"]) / (len(list_rows) or 1), 4),
        "slices": slice_summary,
        "details": recs,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate chunking parameter grid on retrieval completeness")
    parser.add_argument("--cleaned-docs", default="processed/cleaned_docs.jsonl")
    parser.add_argument(
        "--questions",
        default="data/test/eval_questions.jsonl,data/test/eval_questions_extra10.jsonl",
        help="Comma-separated JSONL files with eval questions",
    )
    parser.add_argument("--grid", default="2200:320,2800:560,3200:700,3800:800")
    parser.add_argument("--top-k", type=int, default=12)
    parser.add_argument("--official-only", action="store_true", default=True)
    parser.add_argument("--no-official-only", dest="official_only", action="store_false")
    parser.add_argument("--out-json", default="processed/chunk_grid_summary.json")
    parser.add_argument("--out-md", default="processed/chunk_grid_summary.md")
    parser.add_argument("--work-dir", default="processed/chunk_grid")
    args = parser.parse_args()

    cleaned_docs = (ROOT / args.cleaned_docs).resolve()
    q_paths = [(ROOT / x.strip()).resolve() for x in args.questions.split(",") if x.strip()]
    work_dir = (ROOT / args.work_dir).resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    out_json = (ROOT / args.out_json).resolve()
    out_md = (ROOT / args.out_md).resolve()
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)

    grid = parse_grid(args.grid)
    questions = load_questions(q_paths)
    summaries: list[dict] = []

    for cfg in grid:
        idx_path = run_chunk_and_index(cfg, cleaned_docs, work_dir)
        index = json.loads(idx_path.read_text(encoding="utf-8"))
        summary = evaluate_cfg(cfg, index, questions, top_k=int(args.top_k), official_only=bool(args.official_only))
        summaries.append(summary)

    summaries.sort(key=lambda x: (x["strict_hit_rate"], x["avg_coverage"], -x["critical_miss_count"]), reverse=True)
    best = summaries[0] if summaries else {}
    result = {
        "questions_files": [str(p.relative_to(ROOT)) for p in q_paths],
        "questions_total": len(questions),
        "top_k": int(args.top_k),
        "official_only": bool(args.official_only),
        "grid": [f"{c.chunk_size}:{c.overlap}" for c in grid],
        "best": {
            "config": best.get("config"),
            "chunk_size": best.get("chunk_size"),
            "overlap": best.get("overlap"),
            "strict_hit_rate": best.get("strict_hit_rate"),
            "avg_coverage": best.get("avg_coverage"),
            "critical_miss_count": best.get("critical_miss_count"),
        },
        "configs": summaries,
    }
    out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Chunking grid eval",
        "",
        f"- Questions total: `{len(questions)}`",
        f"- Top-K: `{args.top_k}`",
        f"- Official-only: `{bool(args.official_only)}`",
        f"- Grid: `{', '.join(result['grid'])}`",
        "",
        "## Summary",
        "",
        "| config | strict_hit_rate | avg_coverage | critical_miss_count | avg_source_diversity | avg_chunk_chars_in_topk |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for s in summaries:
        lines.append(
            f"| {s['config']} | {s['strict_hit_rate']:.4f} | {s['avg_coverage']:.4f} | "
            f"{s['critical_miss_count']} | {s['avg_source_diversity']:.3f} | {s['avg_chunk_chars_in_topk']:.1f} |"
        )
    lines.extend(
        [
            "",
            "## List-focused metric",
            "",
            "| config | list_question_hit_rate |",
            "|---|---:|",
        ]
    )
    for s in summaries:
        lines.append(f"| {s['config']} | {s['list_question_hit_rate']:.4f} |")

    lines.extend(["", "## Topic slices (best config)", ""])
    if best and best.get("slices"):
        lines.append("| slice | questions | strict_hit_rate | avg_coverage |")
        lines.append("|---|---:|---:|---:|")
        for sk, sv in (best.get("slices") or {}).items():
            lines.append(
                f"| {sk} | {sv.get('questions', 0)} | {float(sv.get('strict_hit_rate', 0.0)):.4f} | {float(sv.get('avg_coverage', 0.0)):.4f} |"
            )
    if best:
        lines.extend(
            [
                "",
                "## Best config",
                "",
                f"- `{best['config']}` (chunk_size={best['chunk_size']}, overlap={best['overlap']})",
                f"- strict_hit_rate={best['strict_hit_rate']:.4f}, avg_coverage={best['avg_coverage']:.4f}, critical_miss_count={best['critical_miss_count']}",
                f"- list_question_hit_rate={best['list_question_hit_rate']:.4f}",
                "",
                f"Detailed JSON: `{out_json.relative_to(ROOT)}`",
            ]
        )
    out_md.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(result["best"], ensure_ascii=False))
    print(f"Saved summary: {out_json.relative_to(ROOT)}")
    print(f"Saved report: {out_md.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
