#!/usr/bin/env python3
import re
from pathlib import Path

from prepare_corpus import process_file

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


def extract_date_from_text(text: str) -> str | None:
    m = re.search(r"\b(\d{1,2})\s+([А-Яа-я]+)\s+(\d{4})\s+г\.", text[:2000])
    if not m:
        return None
    day, month_ru, year = m.group(1), m.group(2).lower(), m.group(3)
    month = MONTHS.get(month_ru)
    if not month:
        return None
    return f"{int(day):02d}_{month}_{year}"


def normalize_num(num: str) -> str:
    # Keep names filesystem-friendly and stable
    return num.lower().replace("-", "m")


def main() -> None:
    doc_dir = Path("doc")
    unknown_files = sorted(doc_dir.glob("norm_unknown_*.rtf"))
    if not unknown_files:
        print("No unknown files found")
        return

    changes: list[tuple[str, str]] = []
    for path in unknown_files:
        meta, clean_text = process_file(path)
        number = meta.get("doc_number_text")
        date = extract_date_from_text(clean_text) or "unknown_date"
        if not number:
            continue

        new_name = f"norm_{normalize_num(number)}_{date}.rtf"
        target = doc_dir / new_name
        if target.exists() and target != path:
            i = 2
            while True:
                candidate = doc_dir / f"{target.stem}_v{i}.rtf"
                if not candidate.exists():
                    target = candidate
                    break
                i += 1

        if target != path:
            path.rename(target)
            changes.append((path.name, target.name))

    map_path = doc_dir / "rename_map_unknowns.tsv"
    with map_path.open("w", encoding="utf-8") as f:
        f.write("old_name\tnew_name\n")
        for old, new in changes:
            f.write(f"{old}\t{new}\n")

    print(f"Renamed unknown files: {len(changes)}")
    print(f"Saved map: {map_path}")


if __name__ == "__main__":
    main()
