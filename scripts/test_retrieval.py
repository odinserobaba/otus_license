#!/usr/bin/env python3
import argparse
import json
import math
import re
from collections import Counter
from pathlib import Path


TOKEN_RE = re.compile(r"[a-zA-Zа-яА-Я0-9]{2,}")
DEFAULT_QUERIES = [
    "Какие документы нужны для продления лицензии?",
    "В каких случаях проводится выездная оценка заявителя?",
    "Как подтверждаются источники происхождения денежных средств в уставный капитал?",
    "Что регулирует федеральный закон о виноградарстве и виноделии?",
]


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in TOKEN_RE.findall(text)]


def score_query(query: str, index: dict) -> list[tuple[float, dict]]:
    q_tf = Counter(tokenize(query))
    if not q_tf:
        return []

    idf = index["idf"]
    docs = index["docs"]
    scored = []
    for d in docs:
        score = 0.0
        for tok, qf in q_tf.items():
            if tok in d["tf"] and tok in idf:
                score += (qf * idf[tok]) * (d["tf"][tok] * idf[tok] / max(1, math.sqrt(d["len"])))
        if score > 0:
            scored.append((score, d))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored


def main() -> None:
    parser = argparse.ArgumentParser(description="Quick retrieval smoke-test against lexical TF-IDF index")
    parser.add_argument("--index", default="processed/lexical_index.json")
    parser.add_argument("--top-k", type=int, default=3)
    args = parser.parse_args()

    with Path(args.index).open("r", encoding="utf-8") as f:
        index = json.load(f)

    for q in DEFAULT_QUERIES:
        matches = score_query(q, index)[: args.top_k]
        print("\n" + "=" * 100)
        print(f"Q: {q}")
        for i, (score, row) in enumerate(matches, 1):
            meta = row.get("metadata", {})
            source = meta.get("source_file", "n/a")
            doc_type = meta.get("doc_type", "n/a")
            doc_no = meta.get("doc_number_file") or meta.get("doc_number_text") or "n/a"
            print(f"\n[{i}] score={score:.4f} | {doc_type} №{doc_no} | {source}")
            print(row["text"][:350].replace("\n", " ") + "...")


if __name__ == "__main__":
    main()
