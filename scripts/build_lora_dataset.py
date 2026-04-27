#!/usr/bin/env python3
import argparse
import hashlib
import json
import random
import re
from pathlib import Path


DEFAULT_SYSTEM_PROMPT = (
    "Ты юридический ассистент по лицензированию ЕГАИС. "
    "Отвечай строго по контексту, не выдумывай нормы и реквизиты."
)


def clean_answer(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return ""
    # Keep only user-facing part.
    t = re.sub(r"\n?### Embeddings re-rank[\s\S]*$", "", t).strip()
    t = re.sub(r"\n?---\nОтвет сформирован автоматически[\s\S]*$", "", t).strip()
    return t


def dedupe_pairs(rows: list[tuple[str, str]]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    seen = set()
    for q, a in rows:
        h = hashlib.sha1(f"{q}\n{a}".encode("utf-8", errors="ignore")).hexdigest()
        if h in seen:
            continue
        seen.add(h)
        out.append((q, a))
    return out


def load_pairs(path: Path, min_answer_chars: int) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            q = (rec.get("question") or "").strip()
            a = clean_answer(rec.get("answer") or "")
            if not q or len(a) < min_answer_chars:
                continue
            rows.append((q, a))
    return dedupe_pairs(rows)


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def format_record(q: str, a: str, system_prompt: str) -> dict:
    return {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": q},
            {"role": "assistant", "content": a},
        ]
    }


def split_records(
    pairs: list[tuple[str, str]],
    eval_ratio: float,
    seed: int,
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    data = list(pairs)
    rnd = random.Random(seed)
    rnd.shuffle(data)
    eval_size = int(len(data) * eval_ratio)
    eval_size = max(1, eval_size) if len(data) >= 10 and eval_ratio > 0 else 0
    eval_pairs = data[:eval_size]
    train_pairs = data[eval_size:]
    return train_pairs, eval_pairs


def main() -> None:
    parser = argparse.ArgumentParser(description="Build LoRA SFT dataset from processed/qa_history.jsonl")
    parser.add_argument("--input", default="processed/qa_history.jsonl")
    parser.add_argument("--out-train", default="data/lora/train.jsonl")
    parser.add_argument("--out-eval", default="data/lora/eval.jsonl")
    parser.add_argument("--eval-ratio", type=float, default=0.1)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--min-answer-chars", type=int, default=120)
    parser.add_argument("--system-prompt", default=DEFAULT_SYSTEM_PROMPT)
    args = parser.parse_args()

    pairs = load_pairs(Path(args.input), min_answer_chars=args.min_answer_chars)
    if not pairs:
        print("No suitable question/answer pairs found.")
        return

    train_pairs, eval_pairs = split_records(
        pairs,
        eval_ratio=max(0.0, min(float(args.eval_ratio), 0.5)),
        seed=args.seed,
    )
    train_records = [format_record(q, a, args.system_prompt) for q, a in train_pairs]
    eval_records = [format_record(q, a, args.system_prompt) for q, a in eval_pairs]

    write_jsonl(Path(args.out_train), train_records)
    write_jsonl(Path(args.out_eval), eval_records)

    print(f"Loaded pairs: {len(pairs)}")
    print(f"Train records: {len(train_records)} -> {args.out_train}")
    print(f"Eval records: {len(eval_records)} -> {args.out_eval}")


if __name__ == "__main__":
    main()
