#!/usr/bin/env python3
import argparse
import re
from pathlib import Path

from prepare_corpus import process_file
from prepare_doc_files import extract_doc_text, extract_docx_text


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


def extract_date(text: str) -> str | None:
    m = re.search(r"\b(\d{1,2})\s+([А-Яа-я]+)\s+(\d{4})\s+г\.", text[:2500])
    if not m:
        return None
    day, month_ru, year = m.group(1), m.group(2).lower(), m.group(3)
    month = MONTHS.get(month_ru)
    if not month:
        return None
    return f"{int(day):02d}_{month}_{year}"


def extract_number(text: str) -> str | None:
    header = text[:2500]
    patterns = [
        r"\b\d{1,2}\s+[А-Яа-я]+\s+\d{4}\s+г\.\s*№\s*([0-9]{1,6}(?:\s*[-–]\s*[А-Яа-яA-Za-z]{1,3}|[А-Яа-яA-Za-z]{1,3})?)",
        r"от\s+\d{1,2}\s+[А-Яа-я]+\s+\d{4}\s+г\.\s*№\s*([0-9]{1,6}(?:\s*[-–]\s*[А-Яа-яA-Za-z]{1,3}|[А-Яа-яA-Za-z]{1,3})?)",
        r"\b№\s*([0-9]{1,6}\s*[-–]?\s*[А-Яа-яA-Za-z]{0,3})",
    ]
    for p in patterns:
        m = re.search(p, header)
        if m:
            return m.group(1).strip()
    return None


def normalize_token(token: str | None) -> str | None:
    if not token:
        return None
    s = token.lower().replace(" ", "")
    s = s.replace("–", "-")
    # Common legal suffixes
    s = s.replace("-фз", "fz").replace("фз", "fz")
    s = s.replace("-р", "mr").replace("р", "r")
    s = s.replace("н", "n")
    # Keep only ascii alnum
    s = re.sub(r"[^a-z0-9]+", "", s)
    return s or None


def content_text(path: Path, input_dir: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".rtf":
        _, text = process_file(path, input_dir)
        return text
    if ext == ".docx":
        return extract_docx_text(path)
    if ext == ".doc":
        text = extract_doc_text(path)
        return text or ""
    return ""


def main() -> None:
    parser = argparse.ArgumentParser(description="Rename all doc/*.rtf|.doc|.docx files to stable norm_* names")
    parser.add_argument("--input-dir", default="doc")
    parser.add_argument("--map-file", default="doc/rename_map_latest.tsv")
    args = parser.parse_args()

    doc_dir = Path(args.input_dir)
    files = sorted(
        [p for p in doc_dir.iterdir() if p.is_file() and p.suffix.lower() in {".rtf", ".doc", ".docx"}]
    )
    if not files:
        print("No source files found")
        return

    changes: list[tuple[str, str]] = []
    unknown_counter = 1

    for path in files:
        ext = path.suffix.lower()
        text = content_text(path, doc_dir)
        number = normalize_token(extract_number(text)) if text else None
        date = extract_date(text) if text else None

        if number and date:
            new_name = f"norm_{number}_{date}{ext}"
        elif number:
            new_name = f"norm_{number}_unknown_date{ext}"
        elif date:
            new_name = f"norm_unknown_{unknown_counter:03d}_{date}{ext}"
            unknown_counter += 1
        else:
            new_name = f"norm_unknown_{unknown_counter:03d}{ext}"
            unknown_counter += 1

        target = doc_dir / new_name
        if target.exists() and target != path:
            i = 2
            while True:
                candidate = doc_dir / f"{target.stem}_v{i}{ext}"
                if not candidate.exists():
                    target = candidate
                    break
                i += 1

        if target != path:
            path.rename(target)
            changes.append((path.name, target.name))

    map_path = Path(args.map_file)
    map_path.parent.mkdir(parents=True, exist_ok=True)
    with map_path.open("w", encoding="utf-8") as f:
        f.write("old_name\tnew_name\n")
        for old, new in changes:
            f.write(f"{old}\t{new}\n")

    print(f"Scanned files: {len(files)}")
    print(f"Renamed files: {len(changes)}")
    print(f"Mapping file: {map_path}")


if __name__ == "__main__":
    main()
