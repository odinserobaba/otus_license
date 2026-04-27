#!/usr/bin/env python3
import argparse
import json
import math
import re
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path


TOKEN_RE = re.compile(r"[a-zA-Zа-яА-Я0-9]{2,}")


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in TOKEN_RE.findall(text)]


def doc_weight(row: dict) -> float:
    meta = row.get("metadata", {})
    source = (meta.get("source_file") or "").lower()
    doc_type = (meta.get("doc_type") or "").upper()
    is_official = doc_type in {"ПРИКАЗ", "ПОСТАНОВЛЕНИЕ", "РАСПОРЯЖЕНИЕ", "ФЕДЕРАЛЬНЫЙ ЗАКОН"}
    if not is_official:
        return 0.0
    weight = 1.25
    if source.startswith("guide_"):
        weight *= 0.75
    if "unknown" in source:
        weight *= 0.65
    return weight


def score_query(query: str, index: dict) -> list[tuple[float, dict]]:
    q_tf = Counter(tokenize(query))
    if not q_tf:
        return []
    idf = index["idf"]
    docs = index["docs"]
    scored = []
    for d in docs:
        w = doc_weight(d)
        if w <= 0:
            continue
        score = 0.0
        d_tf = d["tf"]
        d_len = max(1, d["len"])
        for tok, qf in q_tf.items():
            if tok in d_tf and tok in idf:
                score += (qf * idf[tok]) * (d_tf[tok] * idf[tok] / math.sqrt(d_len))
        if score > 0:
            scored.append((score * w, d))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored


def build_prompt(
    question: str,
    matches: list[tuple[float, dict]],
    max_chunk_chars: int | None = 800,
) -> str:
    context_blocks = []
    for i, (score, row) in enumerate(matches, 1):
        meta = row.get("metadata", {})
        doc_type = meta.get("doc_type", "Документ")
        doc_no = meta.get("doc_number_file") or meta.get("doc_number_text") or "n/a"
        source = meta.get("source_file", "n/a")
        body = row.get("text") or ""
        if max_chunk_chars is not None and max_chunk_chars > 0:
            body = body[:max_chunk_chars]
        context_blocks.append(
            f"[{i}] {doc_type} №{doc_no} ({source})\n{body}"
        )
    context = "\n\n".join(context_blocks)
    return (
        "Ты юридический ассистент по лицензированию ЕГАИС.\n"
        "Отвечай только по предоставленному контексту.\n"
        "Если в контексте нет точного ответа, так и скажи.\n"
        "Не выдумывай нормативные реквизиты.\n"
        "Формат ответа:\n"
        "1) Краткий ответ\n2) Нормативное основание\n3) Практические шаги\n4) Источники\n\n"
        f"Вопрос:\n{question}\n\n"
        f"Контекст:\n{context}\n"
    )


def select_matches(
    ranked: list[tuple[float, dict]],
    *,
    top_k: int,
    max_chunks_cap: int,
    prompt_char_budget: int,
) -> list[tuple[float, dict]]:
    """Отбор чанков по рангу TF-IDF: бюджет символов и/или top_k / max_chunks_cap."""
    if prompt_char_budget > 0:
        out: list[tuple[float, dict]] = []
        used = 0
        overhead = 200
        for pair in ranked:
            if len(out) >= max_chunks_cap:
                break
            row = pair[1]
            t = len(row.get("text") or "")
            need = t + overhead
            if used + need > prompt_char_budget and out:
                break
            out.append(pair)
            used += need
        return out
    if top_k <= 0:
        return ranked[:max_chunks_cap]
    return ranked[:top_k]


def ollama_generate(model: str, prompt: str, url: str) -> str:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 768},
    }
    req = urllib.request.Request(
        url=url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=3600) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("response", "").strip()
    except urllib.error.URLError as e:
        return f"[OLLAMA ERROR] {e}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Local LLM evaluation using lexical RAG + Ollama")
    parser.add_argument("--index", default="processed/lexical_index.json")
    parser.add_argument("--questions", default="data/test/eval_questions.jsonl")
    parser.add_argument("--top-k", type=int, default=6)
    parser.add_argument("--model", default="qwen2.5:7b-instruct")
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434/api/generate")
    parser.add_argument("--output", default="processed/eval_local_llm.jsonl")
    args = parser.parse_args()

    with Path(args.index).open("r", encoding="utf-8") as f:
        index = json.load(f)

    questions = []
    with Path(args.questions).open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                questions.append(json.loads(line))

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with out_path.open("w", encoding="utf-8") as out:
        for q in questions:
            question = q["question"]
            matches = score_query(question, index)[: args.top_k]
            prompt = build_prompt(question, matches)
            answer = ollama_generate(args.model, prompt, args.ollama_url)
            record = {
                "id": q["id"],
                "question": question,
                "top_k": args.top_k,
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
