#!/usr/bin/env python3
import argparse
import hashlib
import json
import re
from pathlib import Path


def normalize_doc_no(raw: str | None) -> str:
    s = (raw or "").strip().lower().replace(" ", "")
    s = s.replace("–", "-")
    s = re.sub(r"[^0-9a-zа-я\-]", "", s)
    return s


def normalize_date(raw: str | None) -> str:
    s = (raw or "").strip().replace("_", ".")
    m = re.match(r"^(\d{2})\.(\d{2})\.(\d{4})$", s)
    if m:
        return s
    return ""


def source_bucket(meta: dict) -> str:
    bucket = str(meta.get("source_bucket") or "").strip().lower()
    if bucket:
        return bucket
    rel = str(meta.get("source_rel_path") or "").replace("\\", "/").lower()
    if "/new_doc/" in f"/{rel}":
        return "new_doc"
    return "doc"


def canonical_key(rec: dict) -> str:
    meta = rec.get("metadata", {}) or {}
    dt = str(meta.get("doc_type") or "").strip().lower()
    no = normalize_doc_no(meta.get("doc_number_text") or meta.get("doc_number_file"))
    date = normalize_date(meta.get("doc_date_effective") or meta.get("doc_date_file") or meta.get("doc_date_text"))
    if dt and no:
        return f"doc:{dt}|{no}|{date}"
    text = re.sub(r"\s+", " ", str(rec.get("text") or "")).strip().lower()
    th = hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()
    return f"text:{th}"


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            out.append(json.loads(line))
    return out


def record_priority(rec: dict) -> int:
    # Prefer canonical records from existing doc/ over duplicates from new_doc/.
    meta = rec.get("metadata", {}) or {}
    return 1 if source_bucket(meta) == "new_doc" else 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge corpora, detect duplicates, and mark new_doc status")
    parser.add_argument("--rtf-jsonl", default="processed/cleaned_docs_rtf.jsonl")
    parser.add_argument("--extra-jsonl", default="processed/extra_docs.jsonl")
    parser.add_argument("--extra-egais-jsonl", default="processed/extra_docs_egais_centerinform.jsonl")
    parser.add_argument("--output-jsonl", default="processed/cleaned_docs.jsonl")
    parser.add_argument("--new-doc-report", default="processed/new_doc_presence_report.jsonl")
    args = parser.parse_args()

    records: list[dict] = []
    for p in [Path(args.rtf_jsonl), Path(args.extra_jsonl), Path(args.extra_egais_jsonl)]:
        records.extend(read_jsonl(p))

    best_by_key: dict[str, dict] = {}
    for rec in records:
        key = canonical_key(rec)
        current = best_by_key.get(key)
        if current is None or record_priority(rec) < record_priority(current):
            best_by_key[key] = rec

    kept_ids = {str(v.get("id") or "") for v in best_by_key.values()}
    report_rows: list[dict] = []
    merged: list[dict] = []

    for rec in records:
        meta = rec.get("metadata", {}) or {}
        bucket = source_bucket(meta)
        key = canonical_key(rec)
        canonical = best_by_key.get(key, rec)
        duplicate = str(rec.get("id") or "") != str(canonical.get("id") or "")
        if bucket == "new_doc":
            report_rows.append(
                {
                    "id": rec.get("id"),
                    "source_file": meta.get("source_file"),
                    "source_rel_path": meta.get("source_rel_path"),
                    "status": "already_in_corpus" if duplicate else "new_unique",
                    "canonical_id": canonical.get("id"),
                    "dedupe_key": key,
                    "doc_date_effective": meta.get("doc_date_effective") or meta.get("doc_date_file") or meta.get("doc_date_text"),
                }
            )
        if str(rec.get("id") or "") not in kept_ids:
            continue
        meta["source_bucket"] = bucket
        meta["new_doc_status"] = "already_in_corpus" if bucket == "new_doc" and duplicate else ("new_unique" if bucket == "new_doc" else "existing")
        meta["doc_date_effective"] = meta.get("doc_date_effective") or meta.get("doc_date_file") or meta.get("doc_date_text")
        rec["metadata"] = meta
        merged.append(rec)
        kept_ids.remove(str(rec.get("id") or ""))

    out_path = Path(args.output_jsonl)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for rec in merged:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    report_path = Path(args.new_doc_report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", encoding="utf-8") as f:
        for row in report_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"Merged records: {len(merged)}")
    print(f"new_doc report rows: {len(report_rows)}")
    print(f"Saved merged corpus: {out_path}")
    print(f"Saved report: {report_path}")


if __name__ == "__main__":
    main()
