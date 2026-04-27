#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_rows(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec.get("type") == "run_meta":
                continue
            rows.append(rec)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare two eval JSONL runs and write one markdown report")
    parser.add_argument("--before", required=True, help="Path to baseline eval JSONL")
    parser.add_argument("--after", required=True, help="Path to new eval JSONL")
    parser.add_argument("--out-md", required=True, help="Output markdown comparison report")
    parser.add_argument("--title", default="Smoke-3 Before/After")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    before_path = (root / args.before).resolve() if not Path(args.before).is_absolute() else Path(args.before)
    after_path = (root / args.after).resolve() if not Path(args.after).is_absolute() else Path(args.after)
    out_md = (root / args.out_md).resolve() if not Path(args.out_md).is_absolute() else Path(args.out_md)
    out_md.parent.mkdir(parents=True, exist_ok=True)

    before_rows = load_rows(before_path)
    after_rows = load_rows(after_path)
    before_map = {str(r.get("id") or ""): r for r in before_rows}

    def verdict_counts(rows: list[dict]) -> dict[str, int]:
        out = {"ok": 0, "partial": 0, "bad": 0}
        for r in rows:
            v = str(r.get("verdict") or "").lower()
            if v in out:
                out[v] += 1
        return out

    bcnt = verdict_counts(before_rows)
    acnt = verdict_counts(after_rows)
    delta: list[tuple[str, str, str, float, float]] = []
    for r in after_rows:
        qid = str(r.get("id") or "")
        old = before_map.get(qid)
        if not old:
            continue
        v_old = str(old.get("verdict") or "")
        v_new = str(r.get("verdict") or "")
        if v_old != v_new:
            delta.append(
                (
                    qid,
                    v_old,
                    v_new,
                    float(old.get("score_ratio") or 0.0),
                    float(r.get("score_ratio") or 0.0),
                )
            )

    lines = [
        f"# {args.title}",
        "",
        f"- Before: `{before_path.relative_to(root)}`",
        f"- After: `{after_path.relative_to(root)}`",
        "",
        "## Verdict counts",
        "",
        "| run | ok | partial | bad |",
        "|---|---:|---:|---:|",
        f"| before | {bcnt['ok']} | {bcnt['partial']} | {bcnt['bad']} |",
        f"| after | {acnt['ok']} | {acnt['partial']} | {acnt['bad']} |",
        "",
        "## Changed questions",
        "",
        "| id | before | after | score_before | score_after |",
        "|---|---|---|---:|---:|",
    ]
    if delta:
        for qid, vo, vn, so, sn in delta:
            lines.append(f"| {qid} | {vo} | {vn} | {so:.3f} | {sn:.3f} |")
    else:
        lines.append("| - | - | - | - | - |")

    out_md.write_text("\n".join(lines), encoding="utf-8")
    print(str(out_md.relative_to(root)))


if __name__ == "__main__":
    main()
