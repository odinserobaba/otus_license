#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


def read_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Build synthetic 100+ load test set from base eval questions")
    parser.add_argument(
        "--inputs",
        nargs="+",
        default=["data/test/eval_questions.jsonl", "data/test/eval_questions_extra10.jsonl"],
        help="Input JSONL files with base questions",
    )
    parser.add_argument("--target-size", type=int, default=120, help="Output question count")
    parser.add_argument("--output", default="data/test/eval_questions_load100.jsonl")
    args = parser.parse_args()

    base: list[dict] = []
    for p in [Path(x) for x in args.inputs]:
        base.extend(read_jsonl(p))
    if not base:
        raise SystemExit("No input questions found")

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    target = max(1, int(args.target_size))
    rows: list[dict] = []
    for i in range(target):
        src = dict(base[i % len(base)])
        src_id = str(src.get("id") or f"q{i+1}")
        src["id"] = f"{src_id}_lt{i+1:03d}"
        rows.append(src)

    with out_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"Built load set: {len(rows)}")
    print(f"Saved: {out_path}")


if __name__ == "__main__":
    main()
