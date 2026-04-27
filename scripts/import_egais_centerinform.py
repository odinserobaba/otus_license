#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from collections import deque
from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib import parse as urlparse
from urllib import request as urlrequest


DOC_NUMBER_RE = re.compile(r"(?:№|N)\s*([0-9]{1,5}(?:-[0-9A-Za-zА-Яа-я]+)?)")
DOC_DATE_RE = re.compile(r"\b(\d{2}\.\d{2}\.\d{4})\b")
DOC_TYPE_RE = re.compile(r"\b(ПРИКАЗ|ПОСТАНОВЛЕНИЕ|РАСПОРЯЖЕНИЕ|ФЕДЕРАЛЬНЫЙ\s+ЗАКОН)\b", re.IGNORECASE)


def clean_text(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self.links: list[str] = []
        self._in_title = False
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        t = tag.lower()
        if t in {"script", "style", "noscript"}:
            self._skip_depth += 1
            return
        if self._skip_depth > 0:
            return
        if t == "title":
            self._in_title = True
            return
        if t == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)
        if t in {"p", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "div"}:
            self.text_parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t in {"script", "style", "noscript"}:
            if self._skip_depth > 0:
                self._skip_depth -= 1
            return
        if t == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return
        s = unescape(data or "")
        if not s.strip():
            return
        if self._in_title:
            self.title_parts.append(s.strip())
        self.text_parts.append(s)

    @property
    def title(self) -> str:
        return clean_text(" ".join(self.title_parts))

    @property
    def text(self) -> str:
        return clean_text(" ".join(self.text_parts))


@dataclass
class CrawlCfg:
    start_urls: list[str]
    allowed_host: str
    allowed_path_prefixes: list[str]
    max_pages: int
    min_text_len: int
    max_external_links: int
    request_timeout_sec: int


def normalize_url(raw: str, current_url: str, cfg: CrawlCfg) -> str:
    if not raw:
        return ""
    url = urlparse.urljoin(current_url, raw.strip())
    parsed = urlparse.urlsplit(url)
    if parsed.scheme not in {"http", "https"}:
        return ""
    host = (parsed.netloc or "").lower()
    if host != cfg.allowed_host:
        return ""
    path = parsed.path or "/"
    tail = path.rsplit("/", 1)[-1]
    # Preserve directory semantics for relative links like "./page.php".
    if path != "/" and not path.endswith("/") and "." not in tail:
        path = path + "/"
    if not any(path.startswith(prefix) for prefix in cfg.allowed_path_prefixes):
        return ""
    if path.endswith((".jpg", ".jpeg", ".png", ".gif", ".svg", ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip")):
        return ""
    cleaned = urlparse.urlunsplit((parsed.scheme, host, path, parsed.query, ""))
    return cleaned


def fetch_html(url: str, timeout: int = 45) -> tuple[str, str]:
    req = urlrequest.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            )
        },
        method="GET",
    )
    with urlrequest.urlopen(req, timeout=timeout) as resp:
        ctype = str(resp.headers.get("Content-Type", "")).lower()
        if "text/html" not in ctype and "application/xhtml+xml" not in ctype:
            return "", f"skip_content_type:{ctype}"
        data = resp.read()
    html = data.decode("utf-8", errors="ignore")
    return html, ""


def normalize_external_url(raw: str, current_url: str) -> str:
    if not raw:
        return ""
    url = urlparse.urljoin(current_url, raw.strip())
    parsed = urlparse.urlsplit(url)
    if parsed.scheme not in {"http", "https"}:
        return ""
    host = (parsed.netloc or "").lower()
    allowed = (
        host.endswith("publication.pravo.gov.ru")
        or host.endswith("pravo.gov.ru")
        or host.endswith("www.pravo.gov.ru")
    )
    if not allowed:
        return ""
    if parsed.path.endswith((".pdf", ".doc", ".docx", ".zip")):
        return ""
    return urlparse.urlunsplit((parsed.scheme, host, parsed.path, parsed.query, ""))


def infer_doc_type(text: str) -> str | None:
    m = DOC_TYPE_RE.search(text or "")
    if not m:
        return None
    return m.group(1).upper().replace("  ", " ")


def infer_procedure_type(text: str) -> str | None:
    low = (text or "").lower()
    if "переоформ" in low:
        return "reissue"
    if "продлен" in low:
        return "extension"
    if "получени" in low or "выдач" in low:
        return "issuance"
    return None


def infer_topic_tags(text: str) -> list[str]:
    low = (text or "").lower()
    tags: list[str] = []
    if "госуслуг" in low or "епгу" in low or "единый портал" in low:
        tags.append("epgu")
    if "госпошлин" in low:
        tags.append("fee")
    if "переоформ" in low:
        tags.append("reissue")
    if "продлен" in low:
        tags.append("extension")
    if "розничн" in low and "продаж" in low:
        tags.append("retail")
    if "выездн" in low and "оцен" in low:
        tags.append("field_assessment")
    return tags


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


def main() -> None:
    parser = argparse.ArgumentParser(description="Crawl EGAIS center-inform legislation pages into extra_docs JSONL")
    parser.add_argument("--start-url", default="https://egais.center-inform.ru/egais/zakonodatelstvo/")
    parser.add_argument(
        "--extra-start-urls",
        default="https://egais.center-inform.ru/tehpod/faq/",
        help="Comma-separated additional start URLs",
    )
    parser.add_argument("--allowed-host", default="egais.center-inform.ru")
    parser.add_argument(
        "--allowed-path-prefixes",
        default="/egais/zakonodatelstvo,/tehpod/faq,/egais/how-to-connect,/egais/",
        help="Comma-separated path prefixes to allow",
    )
    parser.add_argument("--max-pages", type=int, default=1200)
    parser.add_argument("--min-text-len", type=int, default=400)
    parser.add_argument("--max-external-links", type=int, default=800)
    parser.add_argument("--request-timeout-sec", type=int, default=20)
    parser.add_argument("--out-dir", default="doc/egais_centerinform")
    parser.add_argument("--out-jsonl", default="processed/extra_docs_egais_centerinform.jsonl")
    parser.add_argument("--out-manifest", default="processed/egais_centerinform_manifest.jsonl")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    out_dir = (root / args.out_dir).resolve()
    html_dir = out_dir / "source_html"
    txt_dir = out_dir / "source_txt"
    ext_html_dir = out_dir / "source_html_external"
    ext_txt_dir = out_dir / "source_txt_external"
    html_dir.mkdir(parents=True, exist_ok=True)
    txt_dir.mkdir(parents=True, exist_ok=True)
    ext_html_dir.mkdir(parents=True, exist_ok=True)
    ext_txt_dir.mkdir(parents=True, exist_ok=True)
    out_jsonl = (root / args.out_jsonl).resolve()
    out_manifest = (root / args.out_manifest).resolve()
    out_jsonl.parent.mkdir(parents=True, exist_ok=True)
    out_manifest.parent.mkdir(parents=True, exist_ok=True)

    start_urls = [str(args.start_url).strip()]
    start_urls.extend([x.strip() for x in str(args.extra_start_urls or "").split(",") if x.strip()])
    prefixes = [x.strip() for x in str(args.allowed_path_prefixes or "").split(",") if x.strip()]
    if not prefixes:
        raise SystemExit("No allowed path prefixes configured")

    cfg = CrawlCfg(
        start_urls=start_urls,
        allowed_host=str(args.allowed_host).strip().lower(),
        allowed_path_prefixes=prefixes,
        max_pages=int(args.max_pages),
        min_text_len=int(args.min_text_len),
        max_external_links=int(args.max_external_links),
        request_timeout_sec=max(5, int(args.request_timeout_sec)),
    )

    q: deque[str] = deque()
    for s in cfg.start_urls:
        start_norm = normalize_url(s, s, cfg)
        if start_norm:
            q.append(start_norm)
    if not q:
        raise SystemExit("No valid start URLs under allowed host/prefixes")
    seen: set[str] = set()
    records: list[dict] = []
    manifest: list[dict] = []
    external_urls: set[str] = set()
    seq = 0

    while q and len(seen) < cfg.max_pages:
        url = q.popleft()
        if url in seen:
            continue
        seen.add(url)
        seq += 1

        ok = False
        err = ""
        title = ""
        text = ""
        links: list[str] = []
        html_name = f"{seq:04d}.html"
        txt_name = f"{seq:04d}.txt"

        try:
            html, ferr = fetch_html(url, timeout=cfg.request_timeout_sec)
            if ferr:
                err = ferr
            elif not html.strip():
                err = "empty_html"
            else:
                parser_html = PageParser()
                parser_html.feed(html)
                title = parser_html.title or url
                text = parser_html.text
                links = parser_html.links

                (html_dir / html_name).write_text(html, encoding="utf-8")
                if len(text) >= cfg.min_text_len:
                    (txt_dir / txt_name).write_text(text, encoding="utf-8")
                    source_file = f"egais_centerinform_{seq:04d}.txt"
                    number_match = DOC_NUMBER_RE.search(text[:2500])
                    date_match = DOC_DATE_RE.search(text[:2500])
                    meta = {
                        "source_file": source_file,
                        "source_url": url,
                        "source_kind": "guide",
                        "doc_type": infer_doc_type(text),
                        "doc_number_file": None,
                        "doc_date_file": date_match.group(1) if date_match else None,
                        "doc_number_text": number_match.group(1) if number_match else None,
                        "title_guess": title,
                        "doc_title": title,
                        "section_title": title,
                        "procedure_type": infer_procedure_type(text),
                        "topic_tags": infer_topic_tags(text),
                    }
                    meta["doc_citation"] = build_doc_citation(meta)
                    records.append(
                        {
                            "id": f"egais_centerinform_s{seq:04d}",
                            "metadata": meta,
                            "text": text,
                        }
                    )
                    ok = True
                else:
                    err = f"text_too_short:{len(text)}"
        except Exception as e:  # noqa: BLE001
            err = str(e)

        manifest.append(
            {
                "seq": seq,
                "url": url,
                "title": title,
                "downloaded": ok,
                "error": err,
                "text_len": len(text),
                "html_saved_as": str((html_dir / html_name).relative_to(root)) if (html_dir / html_name).exists() else "",
                "txt_saved_as": str((txt_dir / txt_name).relative_to(root)) if (txt_dir / txt_name).exists() else "",
            }
        )

        # Continue BFS even if page had short text; it still can be a section hub.
        for raw in links:
            nurl = normalize_url(raw, url, cfg)
            if nurl and nurl not in seen:
                q.append(nurl)
            exurl = normalize_external_url(raw, url)
            if exurl:
                external_urls.add(exurl)

    ext_count = 0
    for exurl in sorted(external_urls):
        if ext_count >= cfg.max_external_links:
            break
        ext_count += 1
        seq += 1
        ok = False
        err = ""
        title = ""
        text = ""
        html_name = f"ext_{ext_count:04d}.html"
        txt_name = f"ext_{ext_count:04d}.txt"

        try:
            html, ferr = fetch_html(exurl, timeout=cfg.request_timeout_sec)
            if ferr:
                err = ferr
            elif not html.strip():
                err = "empty_html"
            else:
                parser_html = PageParser()
                parser_html.feed(html)
                title = parser_html.title or exurl
                text = parser_html.text
                (ext_html_dir / html_name).write_text(html, encoding="utf-8")
                if len(text) >= cfg.min_text_len:
                    (ext_txt_dir / txt_name).write_text(text, encoding="utf-8")
                    number_match = DOC_NUMBER_RE.search(text[:2500])
                    date_match = DOC_DATE_RE.search(text[:2500])
                    meta = {
                        "source_file": f"egais_centerinform_external_{ext_count:04d}.txt",
                        "source_url": exurl,
                        "source_kind": "official",
                        "doc_type": infer_doc_type(text),
                        "doc_number_file": None,
                        "doc_date_file": date_match.group(1) if date_match else None,
                        "doc_number_text": number_match.group(1) if number_match else None,
                        "title_guess": title,
                        "doc_title": title,
                        "section_title": title,
                        "procedure_type": infer_procedure_type(text),
                        "topic_tags": infer_topic_tags(text),
                    }
                    meta["doc_citation"] = build_doc_citation(meta)
                    records.append(
                        {
                            "id": f"egais_centerinform_external_s{ext_count:04d}",
                            "metadata": meta,
                            "text": text,
                        }
                    )
                    ok = True
                else:
                    err = f"text_too_short:{len(text)}"
        except Exception as e:  # noqa: BLE001
            err = str(e)

        manifest.append(
            {
                "seq": seq,
                "url": exurl,
                "title": title,
                "downloaded": ok,
                "error": err,
                "text_len": len(text),
                "html_saved_as": str((ext_html_dir / html_name).relative_to(root)) if (ext_html_dir / html_name).exists() else "",
                "txt_saved_as": str((ext_txt_dir / txt_name).relative_to(root)) if (ext_txt_dir / txt_name).exists() else "",
            }
        )

    with out_jsonl.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    with out_manifest.open("w", encoding="utf-8") as f:
        for rec in manifest:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    readme_lines = [
        "# EGAIS Center-Inform import",
        "",
        f"- Start URLs: `{', '.join(cfg.start_urls)}`",
        f"- Allowed host: `{cfg.allowed_host}`",
        f"- Allowed path prefixes: `{', '.join(cfg.allowed_path_prefixes)}`",
        f"- Crawled pages: `{len(seen)}`",
        f"- External legal links found: `{len(external_urls)}`",
        f"- External legal links fetched: `{ext_count}`",
        f"- Added corpus records: `{len(records)}`",
        f"- Extra docs JSONL: `{out_jsonl.relative_to(root)}`",
        f"- Manifest: `{out_manifest.relative_to(root)}`",
    ]
    (out_dir / "README.md").write_text("\n".join(readme_lines), encoding="utf-8")

    print(
        json.dumps(
            {
                "crawled_pages": len(seen),
                "external_links_found": len(external_urls),
                "external_links_fetched": ext_count,
                "records": len(records),
                "out_jsonl": str(out_jsonl.relative_to(root)),
                "manifest": str(out_manifest.relative_to(root)),
                "readme": str((out_dir / "README.md").relative_to(root)),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
