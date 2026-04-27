#!/usr/bin/env python3
import argparse
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from zipfile import ZipFile
try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

TOP_LEVEL_SECTION_RE = re.compile(r"^\s*(\d{1,2})\.\s+(.+?)\s*$")
DOC_NUMBER_RE = re.compile(r"(?:№|N)\s*([0-9]{1,5}(?:-[0-9A-Za-zА-Яа-я]+)?)")
DOC_DATE_RE = re.compile(r"\b(\d{2}\.\d{2}\.\d{4})\b")
HEADING_RE = re.compile(
    r"^\s*(?:"
    r"Глава\s+\d+|"
    r"Статья\s+\d+(?:\.\d+)?|"
    r"Раздел\s+[IVXLC]+"
    r")(?:[.\s:-].*)?$",
    re.IGNORECASE,
)
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


def build_doc_citation(meta: dict) -> str:
    doc_type = (meta.get("doc_type") or "Документ").strip()
    number = meta.get("doc_number_text") or meta.get("doc_number_file")
    date = meta.get("doc_date_file")
    title = meta.get("doc_title") or meta.get("title_guess") or meta.get("section_title")

    parts = [doc_type]
    if number:
        parts.append(f"№{number}")
    if date:
        parts.append(f"от {date}")
    if title:
        parts.append(f"— {title}")
    return " ".join(parts)


def clean_text(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


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
    m = DOC_DATE_RE.search(header)
    if m:
        return normalize_date(m.group(1))
    m = re.search(r"\b(\d{1,2}\s+[А-Яа-я]+\s+\d{4}\s*г?\.?)\b", header)
    if m:
        return normalize_date(m.group(1))
    return None


def extract_docx_text(path: Path) -> str:
    with ZipFile(path, "r") as zf:
        xml = zf.read("word/document.xml").decode("utf-8", errors="replace")
    xml = re.sub(r"</w:p>", "\n", xml)
    xml = re.sub(r"<[^>]+>", " ", xml)
    return clean_text(xml)


def run_cmd(cmd: list[str]) -> str | None:
    try:
        cp = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except Exception:
        return None
    return cp.stdout


def extract_doc_text(path: Path) -> str | None:
    antiword = shutil.which("antiword")
    if antiword:
        out = run_cmd([antiword, str(path)])
        if out and out.strip():
            return clean_text(out)

    catdoc = shutil.which("catdoc")
    if catdoc:
        out = run_cmd([catdoc, str(path)])
        if out and out.strip():
            return clean_text(out)

    # Fallback via LibreOffice headless conversion, if installed
    lowriter = shutil.which("lowriter") or shutil.which("libreoffice")
    if lowriter:
        with tempfile.TemporaryDirectory(prefix="doc_convert_") as tmp:
            cmd = [lowriter, "--headless", "--convert-to", "txt:Text", "--outdir", tmp, str(path)]
            try:
                subprocess.run(cmd, capture_output=True, text=True, check=True)
            except Exception:
                return None
            txt_path = Path(tmp) / f"{path.stem}.txt"
            if txt_path.exists():
                return clean_text(txt_path.read_text(encoding="utf-8", errors="replace"))

    return None


def infer_doc_type(text: str) -> str | None:
    m = re.search(r"\b(ПРИКАЗ|ПОСТАНОВЛЕНИЕ|РАСПОРЯЖЕНИЕ|ФЕДЕРАЛЬНЫЙ\s+ЗАКОН)\b", text)
    return m.group(1) if m else None


def infer_procedure_type(text: str) -> str | None:
    low = text.lower()
    if "переоформ" in low:
        return "reissue"
    if "продлен" in low:
        return "extension"
    if "получени" in low or "выдач" in low:
        return "issuance"
    return None


def infer_topic_tags(text: str) -> list[str]:
    low = text.lower()
    tags = []
    if "госуслуг" in low or "епгу" in low:
        tags.append("epgu")
    if "госпошлин" in low:
        tags.append("fee")
    if "лаборатор" in low or "аккредитац" in low:
        tags.append("lab")
    if "уставн" in low and "капитал" in low:
        tags.append("charter_capital")
    if "переоформ" in low:
        tags.append("reissue")
    if "продлен" in low:
        tags.append("extension")
    if "розничн" in low and "продаж" in low:
        tags.append("retail")
    return tags


def detect_source_kind(path: Path, text: str) -> str:
    low_name = path.name.lower()
    if (
        low_name.startswith("guide_")
        or low_name.startswith("faq_")
        or low_name in {"license.txt", "licensing.txt"}
    ):
        return "guide"
    if infer_doc_type(text):
        return "official"
    return "other"


def split_into_sections(text: str) -> list[tuple[str, str]]:
    """
    Split long guidance text by top-level headings:
    '1. ...', '2. ...' etc.
    """
    lines = text.splitlines()
    sections: list[tuple[str, list[str]]] = []
    cur_title = "Общие положения"
    cur_lines: list[str] = []

    for raw_line in lines:
        line = raw_line.strip()
        m = TOP_LEVEL_SECTION_RE.match(line)
        if m and len(line) > 8:
            if cur_lines:
                sections.append((cur_title, cur_lines))
            cur_title = line
            cur_lines = []
            continue
        cur_lines.append(raw_line)

    if cur_lines:
        sections.append((cur_title, cur_lines))

    # Keep original text if split is too noisy.
    if len(sections) < 2:
        return [("Общие положения", text)]

    normalized: list[tuple[str, str]] = []
    for title, sec_lines in sections:
        sec_text = clean_text("\n".join(sec_lines))
        if len(sec_text) >= 300:
            normalized.append((title, sec_text))

    return normalized if len(normalized) >= 2 else [("Общие положения", text)]


def split_license_txt(text: str) -> list[tuple[str, str]]:
    """
    Specialized splitter for license.txt:
    keep list items inside their parent licensing section and split
    only on high-signal headings.
    """
    lines = text.splitlines()
    heading_re = re.compile(r"^\s*\d{1,2}\.\s+Для получения лицензии\b", re.IGNORECASE)
    boundary_re = re.compile(
        r"^\s*(Лицензирование .*|Прием заявлений и документов по лицензированию.*)\s*$",
        re.IGNORECASE,
    )

    sections: list[tuple[str, list[str]]] = []
    cur_title = "Общие положения по лицензированию"
    cur_lines: list[str] = []

    for raw_line in lines:
        line = raw_line.strip()
        is_boundary = bool(line and (heading_re.match(line) or boundary_re.match(line)))
        if is_boundary:
            if cur_lines:
                sections.append((cur_title, cur_lines))
            cur_title = line
            cur_lines = []
            continue
        cur_lines.append(raw_line)

    if cur_lines:
        sections.append((cur_title, cur_lines))

    normalized: list[tuple[str, str]] = []
    for title, sec_lines in sections:
        sec_text = clean_text("\n".join(sec_lines))
        if len(sec_text) >= 240:
            normalized.append((title, sec_text))

    return normalized if len(normalized) >= 2 else [("Общие положения", clean_text(text))]


def split_pdf_into_sections(path: Path) -> list[dict]:
    if PdfReader is None:
        return []

    reader = PdfReader(str(path))
    sections: list[dict] = []
    cur_title = "Общие положения"
    cur_lines: list[str] = []
    start_page = 1
    cur_page = 1

    def flush(end_page: int) -> None:
        nonlocal cur_lines, cur_title, start_page
        text = clean_text("\n".join(cur_lines))
        if len(text) >= 300:
            sections.append(
                {
                    "title": cur_title,
                    "text": text,
                    "start_page": start_page,
                    "end_page": end_page,
                }
            )
        cur_lines = []

    for page_idx, page in enumerate(reader.pages, 1):
        raw = page.extract_text() or ""
        page_text = clean_text(raw)
        if not page_text:
            cur_page = page_idx
            continue
        for line in page_text.splitlines():
            normalized = line.strip()
            if HEADING_RE.match(normalized):
                if cur_lines:
                    flush(page_idx)
                cur_title = normalized
                start_page = page_idx
            else:
                cur_lines.append(line)
        cur_page = page_idx

    if cur_lines:
        flush(cur_page)

    if len(sections) >= 2:
        return sections

    full_text = clean_text("\n".join([(p.extract_text() or "") for p in reader.pages]))
    return [
        {
            "title": "Общие положения",
            "text": full_text,
            "start_page": 1,
            "end_page": len(reader.pages),
        }
    ]


def read_text_file(path: Path) -> str:
    for enc in ("utf-8", "cp1251", "windows-1251"):
        try:
            return clean_text(path.read_text(encoding=enc))
        except Exception:
            continue
    return clean_text(path.read_text(encoding="utf-8", errors="replace"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare extra corpus records from .doc/.docx/.txt/.md/.pdf files")
    parser.add_argument("--input-dir", default="doc")
    parser.add_argument("--txt-dir", default="processed/clean_txt")
    parser.add_argument("--jsonl", default="processed/extra_docs.jsonl")
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    txt_dir = Path(args.txt_dir)
    out_jsonl = Path(args.jsonl)
    txt_dir.mkdir(parents=True, exist_ok=True)
    out_jsonl.parent.mkdir(parents=True, exist_ok=True)

    files = sorted(
        list(input_dir.rglob("*.doc"))
        + list(input_dir.rglob("*.DOC"))
        + list(input_dir.rglob("*.docx"))
        + list(input_dir.rglob("*.DOCX"))
        + list(input_dir.rglob("*.txt"))
        + list(input_dir.rglob("*.TXT"))
        + list(input_dir.rglob("*.md"))
        + list(input_dir.rglob("*.MD"))
        + list(input_dir.rglob("*.pdf"))
        + list(input_dir.rglob("*.PDF"))
    )
    if not files:
        out_jsonl.write_text("", encoding="utf-8")
        print("No .doc/.docx/.txt/.md/.pdf files found")
        print(f"JSONL file: {out_jsonl}")
        return

    records = []
    skipped: list[str] = []
    for path in files:
        source_rel_path = str(path.relative_to(input_dir))
        source_bucket = detect_source_bucket(source_rel_path)
        suffix = path.suffix.lower()
        if suffix == ".docx":
            text = extract_docx_text(path)
        elif suffix == ".doc":
            text = extract_doc_text(path)
        elif suffix == ".pdf":
            sections = split_pdf_into_sections(path)
            if not sections:
                skipped.append(path.name)
                continue
            for sec_idx, sec in enumerate(sections, 1):
                sec_title = sec["title"]
                sec_text = sec["text"]
                rec_id = f"{path.stem}_extra_s{sec_idx:03d}"
                txt_path = txt_dir / f"{rec_id}.txt"
                txt_path.write_text(sec_text, encoding="utf-8")

                number_match = DOC_NUMBER_RE.search(sec_text[:2500])
                date_match = DOC_DATE_RE.search(sec_text[:2500])
                doc_date_text = extract_date_from_text(sec_text)
                meta = {
                    "source_file": path.name,
                    "source_rel_path": source_rel_path,
                    "source_bucket": source_bucket,
                    "doc_type": infer_doc_type(sec_text),
                    "doc_number_file": None,
                    "doc_date_file": normalize_date(date_match.group(1) if date_match else None),
                    "doc_date_text": doc_date_text,
                    "doc_date_effective": normalize_date(date_match.group(1) if date_match else None) or doc_date_text,
                    "doc_number_text": number_match.group(1) if number_match else None,
                    "title_guess": sec_title,
                    "doc_title": sec_title,
                    "section_title": sec_title,
                    "section_index": sec_idx,
                    "section_page_start": sec.get("start_page"),
                    "section_page_end": sec.get("end_page"),
                    "source_kind": detect_source_kind(path, sec_text),
                    "procedure_type": infer_procedure_type(sec_text),
                    "topic_tags": infer_topic_tags(sec_text),
                }
                meta["doc_citation"] = build_doc_citation(meta)
                records.append({"id": rec_id, "metadata": meta, "text": sec_text})
            continue
        else:
            text = read_text_file(path)

        if not text:
            skipped.append(path.name)
            continue

        if suffix in {".txt", ".md"}:
            if path.name.lower() == "license.txt":
                sections = split_license_txt(text)
            else:
                sections = split_into_sections(text)
        else:
            sections = [("Основной текст", text)]
        for sec_idx, (sec_title, sec_text) in enumerate(sections, 1):
            rec_id = f"{path.stem}_extra_s{sec_idx:03d}"
            txt_path = txt_dir / f"{rec_id}.txt"
            txt_path.write_text(sec_text, encoding="utf-8")

            number_match = DOC_NUMBER_RE.search(sec_text[:2000])
            date_match = DOC_DATE_RE.search(sec_text[:2000])
            doc_date_text = extract_date_from_text(sec_text)
            meta = {
                "source_file": path.name,
                "source_rel_path": source_rel_path,
                "source_bucket": source_bucket,
                "doc_type": infer_doc_type(sec_text),
                "doc_number_file": None,
                "doc_date_file": normalize_date(date_match.group(1) if date_match else None),
                "doc_date_text": doc_date_text,
                "doc_date_effective": normalize_date(date_match.group(1) if date_match else None) or doc_date_text,
                "doc_number_text": number_match.group(1) if number_match else None,
                "title_guess": sec_title if sec_title != "Основной текст" else None,
                "doc_title": sec_title if sec_title != "Основной текст" else None,
                "section_title": sec_title,
                "section_index": sec_idx,
                "source_kind": detect_source_kind(path, sec_text),
                "procedure_type": infer_procedure_type(sec_text),
                "topic_tags": infer_topic_tags(sec_text),
            }
            meta["doc_citation"] = build_doc_citation(meta)
            records.append({"id": rec_id, "metadata": meta, "text": sec_text})

    with out_jsonl.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"Processed extra files (.doc/.docx/.txt/.md/.pdf): {len(records)}")
    print(f"Skipped extra files: {len(skipped)}")
    if skipped:
        print("Skipped list:", ", ".join(skipped))
        print("Hint: install antiword/catdoc/libreoffice for .doc support")
    print(f"JSONL file: {out_jsonl}")


if __name__ == "__main__":
    main()
