#!/usr/bin/env python3
import argparse
import json
import re
from pathlib import Path
from typing import Optional


BOUNDARY_RE = re.compile(
    r"^(Глава\s+\d+|Статья\s+\d+|Раздел\s+[IVXLC]+|\d+\.\s|[а-я]\)\s)",
    re.IGNORECASE,
)
HARD_BOUNDARY_RE = re.compile(
    r"^(Глава\s+\d+|Статья\s+\d+|Раздел\s+[IVXLC]+)",
    re.IGNORECASE,
)
ARTICLE_HEADING_RE = re.compile(r"^Статья\s+(\d+(?:\.\d+)?)\.?\s*(.*)$", re.IGNORECASE)
CHAPTER_HEADING_RE = re.compile(r"^(Глава\s+\S+(?:\s+.+)?)$", re.IGNORECASE)
SUBPOINT_LINE_RE = re.compile(r"^\s*((?:\d+(?:\.\d+)?[.)])|(?:[а-я]\)))\s*", re.IGNORECASE)
ARTICLE_REF_RE = re.compile(r"стать[ьяеи]\s+(\d+(?:\.\d+)?)", re.IGNORECASE)
SENTENCE_SPLIT_RE = re.compile(r"(?<=[\.\!\?;:])\s+")
DOC_NO_CLEAN_RE = re.compile(r"[^0-9a-zа-я\-]", re.IGNORECASE)


def split_to_paragraphs(text: str) -> list[str]:
    lines = text.splitlines()
    parts: list[str] = []
    cur: list[str] = []

    def flush() -> None:
        if not cur:
            return
        block = re.sub(r"\s+", " ", " ".join(cur)).strip()
        if block:
            parts.append(block)
        cur.clear()

    for raw in lines:
        line = raw.strip()
        if not line:
            flush()
            continue

        is_heading = bool(
            BOUNDARY_RE.match(line)
            or ARTICLE_HEADING_RE.match(line)
            or CHAPTER_HEADING_RE.match(line)
        )

        # Keep legal headings and list-item starters as separate semantic units.
        if is_heading and cur:
            flush()
        if is_heading:
            parts.append(line)
            continue

        cur.append(line)
    flush()

    if len(parts) < 2:
        # Fallback for noisy OCR-like texts.
        return [p.strip() for p in text.split("\n") if p.strip()]
    return parts


def is_federal_law_doc(rec: dict) -> bool:
    meta = rec.get("metadata", {}) or {}
    doc_type = (meta.get("doc_type") or "").upper()
    source_file = (meta.get("source_file") or "").lower()
    text = rec.get("text", "")
    return (
        doc_type == "ФЕДЕРАЛЬНЫЙ ЗАКОН"
        or "фз" in source_file
        or bool(re.search(r"\b171-ФЗ\b", text, re.IGNORECASE))
    )


def split_article_blocks(paragraphs: list[str]) -> list[dict]:
    blocks: list[dict] = []
    cur = {"article_number": None, "article_title": None, "chapter_title": None, "paragraphs": []}
    chapter_title = None

    for p in paragraphs:
        ch = CHAPTER_HEADING_RE.match(p)
        if ch:
            chapter_title = ch.group(1).strip()
            if cur["paragraphs"]:
                blocks.append(cur)
                cur = {
                    "article_number": None,
                    "article_title": None,
                    "chapter_title": chapter_title,
                    "paragraphs": [],
                }
            else:
                cur["chapter_title"] = chapter_title
            cur["paragraphs"].append(p)
            continue

        art = ARTICLE_HEADING_RE.match(p)
        if art:
            if cur["paragraphs"]:
                blocks.append(cur)
            cur = {
                "article_number": art.group(1).strip(),
                "article_title": p.strip(),
                "chapter_title": chapter_title,
                "paragraphs": [p],
            }
            continue

        cur["paragraphs"].append(p)

    if cur["paragraphs"]:
        blocks.append(cur)
    return blocks


def extract_subpoint_refs(text: str, limit: int = 25) -> list[str]:
    refs: list[str] = []
    for line in text.split("\n"):
        m = SUBPOINT_LINE_RE.match(line)
        if not m:
            continue
        token = m.group(1).strip()
        if token not in refs:
            refs.append(token)
        if len(refs) >= limit:
            break
    return refs


def extract_cited_article_refs(text: str, limit: int = 25) -> list[str]:
    refs: list[str] = []
    for m in ARTICLE_REF_RE.finditer(text):
        token = m.group(1).strip()
        if token not in refs:
            refs.append(token)
        if len(refs) >= limit:
            break
    return refs


def _normalize_article_ref(token: str) -> str:
    return re.sub(r"[^0-9.]", "", str(token or "").strip())


def _normalize_subpoint_ref(token: str) -> str:
    return re.sub(r"[.)\s]+$", "", str(token or "").strip().lower())


def _infer_doc_norm_key(meta: dict) -> str:
    doc_type = str(meta.get("doc_type") or "").strip().lower()
    raw_no = str(meta.get("doc_number_text") or meta.get("doc_number_file") or "").strip().lower()
    source_file = str(meta.get("source_file") or "").strip().lower()

    cleaned = DOC_NO_CLEAN_RE.sub("", raw_no).replace("n", "")
    if "171" in cleaned and ("фз" in cleaned or "fz" in source_file or "фз" in source_file):
        return "171-фз"
    if doc_type == "федеральный закон" and cleaned:
        digits = re.findall(r"\d+", cleaned)
        if digits:
            return f"{digits[0]}-фз"
    if cleaned:
        return cleaned
    return ""


def build_norm_refs(meta: dict, article_number: Optional[str], cited_article_refs: list[str], subpoint_refs: list[str]) -> list[str]:
    refs: list[str] = []

    def add(x: str) -> None:
        x = (x or "").strip().lower()
        if x and x not in refs:
            refs.append(x)

    doc_key = _infer_doc_norm_key(meta)
    if doc_key:
        add(doc_key)

    article_tokens: list[str] = []
    for raw in [article_number, *cited_article_refs]:
        norm = _normalize_article_ref(raw or "")
        if norm and norm not in article_tokens:
            article_tokens.append(norm)

    for art in article_tokens[:8]:
        add(f"ст{art}")
        if doc_key:
            add(f"{doc_key}:ст{art}")

    first_article = article_tokens[0] if article_tokens else ""
    for raw in subpoint_refs[:12]:
        sp = _normalize_subpoint_ref(raw)
        if not sp:
            continue
        add(f"пп{sp}")
        if doc_key and first_article:
            add(f"{doc_key}:ст{first_article}:пп{sp}")

    return refs


def list_density_score(text: str) -> float:
    t = (text or "").strip()
    if not t:
        return 0.0
    lines = [ln.strip() for ln in t.splitlines() if ln.strip()]
    if not lines:
        lines = [x.strip() for x in re.split(r"(?<=[.;])\s+", t) if x.strip()]
    if not lines:
        return 0.0
    hits = 0
    for ln in lines:
        if SUBPOINT_LINE_RE.match(ln):
            hits += 1
            continue
        if re.match(r"^(?:[-*•]\s+)", ln):
            hits += 1
            continue
        if re.match(r"^\d+(?:\.\d+)?\s*[-:)]\s*", ln):
            hits += 1
    return round(min(1.0, hits / max(1, len(lines))), 3)


def _link_chunk_sequence(records: list[dict], *, doc_id: str, block: Optional[dict]) -> None:
    """
    Add lightweight chunk-graph metadata: prev/next within the same sequence
    (same статья for ФЗ, same документ для прочих НПА).
    """
    n = len(records)
    if not n:
        return
    article_number = (block or {}).get("article_number")
    chapter_title = (block or {}).get("chapter_title")
    for i, rec in enumerate(records):
        meta = rec["metadata"]
        if i > 0:
            meta["neighbor_prev_chunk_id"] = records[i - 1]["chunk_id"]
        if i < n - 1:
            meta["neighbor_next_chunk_id"] = records[i + 1]["chunk_id"]
        meta["hierarchy_seq_total"] = n
        meta["hierarchy_seq_index"] = i + 1
        if block is not None:
            meta["article_part_index"] = i + 1
            meta["article_part_total"] = n
            if article_number:
                meta["article_key"] = f"{doc_id}::ст{article_number}"
            else:
                meta["article_key"] = None
            if chapter_title:
                meta["chapter_title"] = chapter_title
        else:
            meta["doc_part_index"] = i + 1
            meta["doc_part_total"] = n
            meta["article_key"] = None


def chunk_paragraphs(paragraphs: list[str], chunk_size: int, overlap: int) -> list[str]:
    def split_list_dense_paragraph(p: str) -> list[str]:
        # Preserve list-item integrity: split only on item starts, never by sentences.
        marker_re = re.compile(r"((?:\d+(?:\.\d+)?[.)])|(?:[а-я]\)))\s*", re.IGNORECASE)
        starts = [m.start() for m in marker_re.finditer(p)]
        if len(starts) < 2:
            return [p]

        items: list[str] = []
        for i, pos in enumerate(starts):
            nxt = starts[i + 1] if i + 1 < len(starts) else len(p)
            seg = p[pos:nxt].strip()
            if seg:
                items.append(seg)
        if len(items) < 2:
            return [p]

        out: list[str] = []
        cur: list[str] = []
        cur_len = 0
        for item in items:
            ilen = len(item)
            if cur and cur_len + ilen + 1 > chunk_size:
                out.append(" ".join(cur).strip())
                cur = [item]
                cur_len = ilen
            else:
                cur.append(item)
                cur_len += ilen + 1
        if cur:
            out.append(" ".join(cur).strip())
        return [x for x in out if x]

    def split_long_paragraph(p: str) -> list[str]:
        if len(p) <= chunk_size:
            return [p]
        if SUBPOINT_LINE_RE.match(p):
            return [p]
        marker_hits = len(re.findall(r"(?:\d+(?:\.\d+)?[.)]|[а-я]\))\s", p, re.IGNORECASE))
        if marker_hits >= 2:
            list_parts = split_list_dense_paragraph(p)
            if len(list_parts) > 1:
                return list_parts
        sentences = SENTENCE_SPLIT_RE.split(p)
        if len(sentences) <= 1:
            return [p[i : i + chunk_size] for i in range(0, len(p), chunk_size)]

        out: list[str] = []
        cur_sent: list[str] = []
        cur_len = 0
        for s in sentences:
            s = s.strip()
            if not s:
                continue
            if cur_sent and cur_len + len(s) + 1 > chunk_size:
                out.append(" ".join(cur_sent).strip())
                cur_sent = [s]
                cur_len = len(s)
            else:
                cur_sent.append(s)
                cur_len += len(s) + 1
        if cur_sent:
            out.append(" ".join(cur_sent).strip())
        return out or [p]

    def overlap_tail(prev: list[str], overlap_chars: int) -> list[str]:
        if overlap_chars <= 0 or not prev:
            return []
        acc: list[str] = []
        total = 0
        for para in reversed(prev):
            acc.insert(0, para)
            total += len(para) + 1
            if total >= overlap_chars:
                break
        return acc

    normalized: list[str] = []
    for p in paragraphs:
        normalized.extend(split_long_paragraph(p))

    chunks: list[str] = []
    cur: list[str] = []
    cur_len = 0
    min_chunk = max(300, chunk_size // 3)

    for p in normalized:
        p_len = len(p)
        # Start new chunk on explicit legal boundary when current chunk is non-trivial
        if cur and HARD_BOUNDARY_RE.match(p) and cur_len >= min_chunk:
            chunks.append("\n".join(cur).strip())
            tail = overlap_tail(cur, overlap)
            cur = tail + [p]
            cur_len = len("\n".join(cur))
            continue

        if cur_len + p_len + 1 > chunk_size and cur:
            chunks.append("\n".join(cur).strip())
            tail = overlap_tail(cur, overlap)
            cur = tail + [p]
            cur_len = len("\n".join(cur))
        else:
            cur.append(p)
            cur_len += p_len + 1

    if cur:
        chunks.append("\n".join(cur).strip())
    return [c for c in chunks if c]


def main() -> None:
    parser = argparse.ArgumentParser(description="Chunk cleaned legal corpus into RAG-ready fragments")
    parser.add_argument("--input-jsonl", default="processed/cleaned_docs.jsonl")
    parser.add_argument("--output-jsonl", default="processed/chunks.jsonl")
    parser.add_argument("--chunk-size", type=int, default=2200)
    parser.add_argument("--overlap", type=int, default=320)
    args = parser.parse_args()

    input_path = Path(args.input_jsonl)
    output_path = Path(args.output_jsonl)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    total_docs = 0
    total_chunks = 0

    with input_path.open("r", encoding="utf-8") as src, output_path.open("w", encoding="utf-8") as out:
        for line in src:
            if not line.strip():
                continue
            rec = json.loads(line)
            doc_id = rec["id"]
            text = rec["text"]
            metadata = rec.get("metadata", {})
            paragraphs = split_to_paragraphs(text)
            article_blocks = split_article_blocks(paragraphs) if is_federal_law_doc(rec) else None
            total_docs += 1

            if article_blocks:
                chunk_idx = 0
                for block in article_blocks:
                    block_chunks = chunk_paragraphs(block["paragraphs"], args.chunk_size, args.overlap)
                    block_records: list[dict] = []
                    for chunk_text in block_chunks:
                        chunk_idx += 1
                        article_number = block.get("article_number")
                        subpoint_refs = extract_subpoint_refs(chunk_text)
                        cited_refs = extract_cited_article_refs(chunk_text)
                        list_density = list_density_score(chunk_text)
                        if article_number and article_number not in cited_refs:
                            cited_refs.insert(0, article_number)
                        block_records.append(
                            {
                                "chunk_id": f"{doc_id}::chunk_{chunk_idx:04d}",
                                "doc_id": doc_id,
                                "text": chunk_text,
                                "metadata": {
                                    **metadata,
                                    "chunk_index": chunk_idx,
                                    "chunk_chars": len(chunk_text),
                                    "chapter_title": block.get("chapter_title"),
                                    "article_number": article_number,
                                    "article_title": block.get("article_title"),
                                    "subpoint_refs": subpoint_refs,
                                    "cited_article_refs": cited_refs,
                                    "norm_refs": build_norm_refs(metadata, article_number, cited_refs, subpoint_refs),
                                    "list_density": list_density,
                                },
                            }
                        )
                    _link_chunk_sequence(block_records, doc_id=doc_id, block=block)
                    for chunk in block_records:
                        out.write(json.dumps(chunk, ensure_ascii=False) + "\n")
                        total_chunks += 1
            else:
                chunks = chunk_paragraphs(paragraphs, args.chunk_size, args.overlap)
                seq_records: list[dict] = []
                for idx, chunk_text in enumerate(chunks, 1):
                    subpoint_refs = extract_subpoint_refs(chunk_text)
                    cited_refs = extract_cited_article_refs(chunk_text)
                    list_density = list_density_score(chunk_text)
                    seq_records.append(
                        {
                            "chunk_id": f"{doc_id}::chunk_{idx:04d}",
                            "doc_id": doc_id,
                            "text": chunk_text,
                            "metadata": {
                                **metadata,
                                "chunk_index": idx,
                                "chunk_chars": len(chunk_text),
                                "subpoint_refs": subpoint_refs,
                                "cited_article_refs": cited_refs,
                                "norm_refs": build_norm_refs(metadata, None, cited_refs, subpoint_refs),
                                "list_density": list_density,
                            },
                        }
                    )
                _link_chunk_sequence(seq_records, doc_id=doc_id, block=None)
                for chunk in seq_records:
                    out.write(json.dumps(chunk, ensure_ascii=False) + "\n")
                    total_chunks += 1

    print(f"Chunked docs: {total_docs}")
    print(f"Total chunks: {total_chunks}")
    print(f"Saved: {output_path}")


if __name__ == "__main__":
    main()
