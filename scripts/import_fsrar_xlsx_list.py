#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import zipfile
from html import unescape
from pathlib import Path
from urllib import request as urlrequest
from xml.etree import ElementTree as ET


NS_MAIN = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
NS_REL = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}
HTTP_RE = re.compile(r"https?://", re.IGNORECASE)
URL_IN_TEXT_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)


def col_letters(cell_ref: str) -> str:
    out = []
    for ch in cell_ref:
        if ch.isalpha():
            out.append(ch)
        else:
            break
    return "".join(out)


def load_shared_strings(zf: zipfile.ZipFile) -> list[str]:
    name = "xl/sharedStrings.xml"
    if name not in zf.namelist():
        return []
    root = ET.fromstring(zf.read(name))
    out: list[str] = []
    for si in root.findall("x:si", NS_MAIN):
        parts = []
        for t in si.findall(".//x:t", NS_MAIN):
            parts.append(t.text or "")
        out.append("".join(parts).strip())
    return out


def load_sheet_rels(zf: zipfile.ZipFile) -> dict[str, str]:
    name = "xl/worksheets/_rels/sheet1.xml.rels"
    if name not in zf.namelist():
        return {}
    root = ET.fromstring(zf.read(name))
    rels: dict[str, str] = {}
    for rel in root.findall("r:Relationship", NS_REL):
        rid = rel.attrib.get("Id", "").strip()
        target = rel.attrib.get("Target", "").strip()
        if rid and target:
            rels[rid] = target
    return rels


def parse_sheet_rows(xlsx_path: Path) -> tuple[list[dict], dict[str, str]]:
    with zipfile.ZipFile(xlsx_path) as zf:
        shared = load_shared_strings(zf)
        rels = load_sheet_rels(zf)
        root = ET.fromstring(zf.read("xl/worksheets/sheet1.xml"))

        hyperlink_by_ref: dict[str, str] = {}
        for h in root.findall("x:hyperlinks/x:hyperlink", NS_MAIN):
            ref = h.attrib.get("ref", "").strip()
            rid = h.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id", "").strip()
            target = rels.get(rid, "")
            if ref and target:
                hyperlink_by_ref[ref] = unescape(target)

        rows: list[dict] = []
        for row in root.findall("x:sheetData/x:row", NS_MAIN):
            row_num = int(row.attrib.get("r", "0") or 0)
            cells: dict[str, str] = {}
            links: list[str] = []
            for c in row.findall("x:c", NS_MAIN):
                ref = c.attrib.get("r", "").strip()
                col = col_letters(ref)
                c_type = (c.attrib.get("t") or "").strip()
                v = c.find("x:v", NS_MAIN)
                if v is None:
                    txt = ""
                elif c_type == "s":
                    idx = int(v.text or "0")
                    txt = shared[idx] if 0 <= idx < len(shared) else ""
                else:
                    txt = (v.text or "").strip()
                if col:
                    cells[col] = txt
                href = hyperlink_by_ref.get(ref)
                if href:
                    links.append(href)
            rows.append({"row": row_num, "cells": cells, "links": links})
    return rows, hyperlink_by_ref


def normalize_url(url: str) -> str:
    u = unescape((url or "").strip())
    if not HTTP_RE.search(u):
        return ""
    # Keep only practical legal sources from this list.
    if "publication.pravo.gov.ru" in u.lower() or "pravo.gov.ru/proxy/ips/" in u.lower():
        return u
    return ""


def safe_name(s: str, max_len: int = 80) -> str:
    x = re.sub(r"\s+", "_", (s or "").strip())
    x = re.sub(r"[^A-Za-z0-9_.-]+", "_", x)
    return x[:max_len].strip("_") or "doc"


def download_url(url: str, out_path: Path) -> tuple[bool, str]:
    req = urlrequest.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        },
        method="GET",
    )
    try:
        with urlrequest.urlopen(req, timeout=120) as resp:
            data = resp.read()
            out_path.write_bytes(data)
        return True, ""
    except Exception as e:  # noqa: BLE001
        return False, str(e)


def html_to_text(raw_html: bytes) -> str:
    s = raw_html.decode("utf-8", errors="ignore")
    s = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", s)
    s = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", s)
    s = re.sub(r"(?is)<[^>]+>", " ", s)
    s = unescape(s)
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n\s*\n\s*\n+", "\n\n", s.replace("\r", "\n"))
    return s.strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--xlsx", required=True, help="Path to source XLSX list")
    parser.add_argument(
        "--out-dir",
        default="doc/fsrar_dr31_2025_09_25",
        help="Destination folder for downloaded source docs",
    )
    parser.add_argument(
        "--out-manifest",
        default="processed/fsrar_dr31_2025_09_25_manifest.jsonl",
        help="Manifest JSONL path",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    xlsx_path = (root / args.xlsx).resolve()
    out_dir = (root / args.out_dir).resolve()
    docs_dir = out_dir / "source_docs"
    txt_dir = out_dir / "source_txt"
    manifest_path = (root / args.out_manifest).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    docs_dir.mkdir(parents=True, exist_ok=True)
    txt_dir.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    rows, _ = parse_sheet_rows(xlsx_path)
    records: list[dict] = []
    seen = set()
    seq = 0

    for r in rows:
        row_num = r.get("row", 0)
        cells: dict = r.get("cells", {})
        title = " ".join(x for _, x in sorted(cells.items()) if x).strip()
        raw_urls = list(r.get("links", []))
        for txt in cells.values():
            if not txt:
                continue
            raw_urls.extend(URL_IN_TEXT_RE.findall(unescape(str(txt))))
        for raw in raw_urls:
            url = normalize_url(raw)
            if not url:
                continue
            key = (row_num, url)
            if key in seen:
                continue
            seen.add(key)
            seq += 1
            base = safe_name(title or f"row_{row_num}")
            html_name = f"{seq:03d}_r{row_num}_{base}.html"
            out_file = docs_dir / html_name
            ok, err = download_url(url, out_file)
            txt_rel = ""
            if ok:
                try:
                    txt_name = f"{seq:03d}_r{row_num}_{base}.txt"
                    txt_file = txt_dir / txt_name
                    txt_file.write_text(html_to_text(out_file.read_bytes()), encoding="utf-8")
                    txt_rel = str(txt_file.relative_to(root))
                except Exception as te:  # noqa: BLE001
                    ok = False
                    err = f"text_extract_error: {te}"
            records.append(
                {
                    "seq": seq,
                    "row": row_num,
                    "title": title,
                    "url": url,
                    "saved_as": str(out_file.relative_to(root)),
                    "text_saved_as": txt_rel,
                    "downloaded": ok,
                    "error": err,
                }
            )

    with manifest_path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    ok_count = sum(1 for r in records if r.get("downloaded"))
    fail_count = len(records) - ok_count
    md_lines = [
        "# FSRAR DR-31 list import",
        "",
        f"- Source XLSX: `{xlsx_path.relative_to(root)}`",
        f"- Total links: `{len(records)}`",
        f"- Downloaded: `{ok_count}`",
        f"- Failed: `{fail_count}`",
        f"- Manifest: `{manifest_path.relative_to(root)}`",
        "",
        "## Imported documents",
        "",
        "| # | Row | Saved file | URL | Status |",
        "|---|---:|---|---|---|",
    ]
    for r in records:
        status = "ok" if r.get("downloaded") else f"fail: {r.get('error', '')[:80]}"
        md_lines.append(
            f"| {r['seq']} | {r['row']} | `{r['saved_as']}` | {r['url']} | {status} |"
        )
    (out_dir / "README.md").write_text("\n".join(md_lines), encoding="utf-8")

    print(
        json.dumps(
            {
                "links_total": len(records),
                "downloaded": ok_count,
                "failed": fail_count,
                "manifest": str(manifest_path.relative_to(root)),
                "readme": str((out_dir / "README.md").relative_to(root)),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
