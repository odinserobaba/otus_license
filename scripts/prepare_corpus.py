#!/usr/bin/env python3
import argparse
import json
import re
from email import policy
from email.parser import BytesParser
from html import unescape
from pathlib import Path


MONTHS = {
    "января": "01",
    "февраля": "02",
    "марта": "03",
    "апреля": "04",
    "мая": "05",
    "июня": "06",
    "июля": "07",
    "августа": "08",
    "сентября": "09",
    "октября": "10",
    "ноября": "11",
    "декабря": "12",
}


def detect_source_bucket(source_rel_path: str) -> str:
    p = (source_rel_path or "").replace("\\", "/").lower()
    if "/new_doc/" in f"/{p}":
        return "new_doc"
    return "doc"


def normalize_date(raw: str | None) -> str | None:
    s = (raw or "").strip()
    if not s:
        return None
    m = re.match(r"^(\d{2})[._-](\d{2})[._-](\d{4})$", s)
    if m:
        return f"{m.group(1)}.{m.group(2)}.{m.group(3)}"
    m = re.match(r"^(\d{1,2})\s+([А-Яа-я]+)\s+(\d{4})\s*г?\.?$", s)
    if m:
        day, month_ru, year = m.group(1), m.group(2).lower(), m.group(3)
        month = MONTHS.get(month_ru)
        if month:
            return f"{int(day):02d}.{month}.{year}"
    return None


def extract_date_from_text(text: str) -> str | None:
    header = (text or "")[:2500]
    m = re.search(r"\b(\d{2}\.\d{2}\.\d{4})\b", header)
    if m:
        return normalize_date(m.group(1))
    m = re.search(r"\b(\d{1,2}\s+[А-Яа-я]+\s+\d{4}\s*г?\.?)\b", header)
    if m:
        return normalize_date(m.group(1))
    return None


def build_doc_citation(meta: dict) -> str:
    doc_type = (meta.get("doc_type") or "Документ").strip()
    number = meta.get("doc_number_text") or meta.get("doc_number_file")
    date = meta.get("doc_date_file")
    title = meta.get("title_guess")

    parts = [doc_type]
    if number:
        parts.append(f"№{number}")
    if date:
        parts.append(f"от {date}")
    if title:
        parts.append(f"— {title}")
    return " ".join(parts)


def extract_html_from_mhtml(raw_bytes: bytes) -> str:
    msg = BytesParser(policy=policy.default).parsebytes(raw_bytes)
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype == "text/html":
                payload = part.get_payload(decode=True) or b""
                charset = part.get_content_charset() or "windows-1251"
                return payload.decode(charset, errors="replace")
    # Fallback for non-multipart or malformed files
    text = raw_bytes.decode("windows-1251", errors="replace")
    if "<html" in text.lower():
        return text
    raise ValueError("No HTML content found")


def html_to_clean_text(html: str) -> str:
    html = re.sub(r"(?is)<script.*?>.*?</script>", " ", html)
    html = re.sub(r"(?is)<style.*?>.*?</style>", " ", html)
    html = re.sub(r"(?is)<!--.*?-->", " ", html)
    html = re.sub(r"(?i)<br\\s*/?>", "\n", html)
    html = re.sub(r"(?i)</p>", "\n", html)
    html = re.sub(r"(?i)</tr>", "\n", html)
    html = re.sub(r"(?i)</td>", " | ", html)
    text = re.sub(r"(?is)<[^>]+>", " ", html)
    text = unescape(text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()
    text = re.sub(r"^Complex\s*\n+", "", text)
    return text


def extract_metadata(file_name: str, source_rel_path: str, text: str) -> dict:
    file_match = re.match(r"norm_([0-9a-zA-Zа-яА-Я\-]+)_(\d{2}_\d{2}_\d{4})(?:_v\d+)?\.rtf$", file_name)
    doc_number_file = file_match.group(1) if file_match else None
    doc_date_file = normalize_date(file_match.group(2)) if file_match else None

    # Header metadata from text for better grounding in answers
    doc_type_match = re.search(r"\b(ПРИКАЗ|ПОСТАНОВЛЕНИЕ|РАСПОРЯЖЕНИЕ|ФЕДЕРАЛЬНЫЙ\s+ЗАКОН)\b", text)
    doc_type = doc_type_match.group(1) if doc_type_match else None

    doc_number_text = None
    header_text = text[:1800]
    number_match = re.search(
        r"\b\d{1,2}\s+[А-Яа-я]+\s+\d{4}\s+г\.\s*№\s*([0-9]{1,5}(?:н|-[а-яА-Яa-zA-Z])?)\b",
        header_text,
    )
    if not number_match:
        number_match = re.search(
            r"от\s+\d{1,2}\s+[А-Яа-я]+\s+\d{4}\s+г\.\s*№\s*([0-9]{1,5}(?:н|-[а-яА-Яa-zA-Z])?)\b",
        header_text,
    )
    if not number_match:
        number_match = re.search(
            r"\b(?:ПРИКАЗ|ПОСТАНОВЛЕНИЕ|РАСПОРЯЖЕНИЕ)\b[^\n]{0,120}№\s*([0-9]{1,5}(?:н|-[а-яА-Яa-zA-Z])?)\b",
            header_text,
        )
    if number_match:
        doc_number_text = number_match.group(1)
    doc_date_text = extract_date_from_text(text)
    doc_date_effective = doc_date_file or doc_date_text

    title = None
    title_match = re.search(r"(Об\s+утверждении[^\n]{20,500}|О\s+государственном[^\n]{20,500})", text)
    if title_match:
        title = title_match.group(1).strip()

    return {
        "source_file": file_name,
        "source_rel_path": source_rel_path,
        "source_bucket": detect_source_bucket(source_rel_path),
        "doc_type": doc_type,
        "doc_number_file": doc_number_file,
        "doc_date_file": doc_date_file,
        "doc_date_text": doc_date_text,
        "doc_date_effective": doc_date_effective,
        "doc_number_text": doc_number_text,
        "title_guess": title,
        "doc_title": title,
        "doc_citation": build_doc_citation(
            {
                "doc_type": doc_type,
                "doc_number_file": doc_number_file,
                "doc_date_file": doc_date_effective,
                "doc_number_text": doc_number_text,
                "title_guess": title,
            }
        ),
    }


def process_file(path: Path, input_dir: Path) -> tuple[dict, str]:
    raw = path.read_bytes()
    html = extract_html_from_mhtml(raw)
    clean_text = html_to_clean_text(html)
    source_rel_path = str(path.relative_to(input_dir))
    meta = extract_metadata(path.name, source_rel_path, clean_text)
    return meta, clean_text


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare cleaned corpus from MHTML-in-RTF files.")
    parser.add_argument("--input-dir", default="doc", help="Directory with source .rtf files")
    parser.add_argument("--txt-dir", default="processed/clean_txt", help="Directory for cleaned txt files")
    parser.add_argument("--jsonl", default="processed/cleaned_docs.jsonl", help="Output JSONL file")
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    txt_dir = Path(args.txt_dir)
    jsonl_path = Path(args.jsonl)
    txt_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)

    files = sorted(input_dir.rglob("*.rtf"))
    if not files:
        raise SystemExit(f"No .rtf files found in {input_dir}")

    records = []
    for path in files:
        meta, clean_text = process_file(path, input_dir)
        txt_path = txt_dir / f"{path.stem}.txt"
        txt_path.write_text(clean_text, encoding="utf-8")
        record = {"id": path.stem, "metadata": meta, "text": clean_text}
        records.append(record)

    with jsonl_path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"Processed {len(records)} files")
    print(f"Cleaned TXT directory: {txt_dir}")
    print(f"JSONL file: {jsonl_path}")


if __name__ == "__main__":
    main()
