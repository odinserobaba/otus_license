from __future__ import annotations

from datetime import datetime
import re
from typing import Callable


def enforce_fact_consistency(
    text: str,
    question: str,
    is_comparative_law_question: Callable[[str], bool],
) -> tuple[str, list[str]]:
    out = text or ""
    notes: list[str] = []
    ql = (question or "").lower()
    low = out.lower()
    if ("госуслуг" in ql or "бумаж" in ql or "портал" in ql) and ("продл" in ql and "лиценз" in ql):
        bad = re.search(r"(можно|допускается|разрешается).{0,60}(бумажн|на бумажном)", low)
        if bad:
            fix = (
                "Для продления лицензии бумажный канал не применяется: подача осуществляется "
                "через ЕПГУ в электронной форме."
            )
            out = f"{out}\n\n{fix}".strip()
            notes.append("consistency_fixed_submission_channel")
    if ("99" in ql and "171" in ql) or is_comparative_law_question(question):
        has_special = "специальн" in low and ("171-фз" in low or "171 фз" in low)
        has_general = "99-фз" in low or "99 фз" in low
        if not (has_special and has_general):
            fix = (
                "При коллизии норм по алкогольному рынку применяется специальное регулирование 171-ФЗ, "
                "а 99-ФЗ действует как общий закон в непротиворечащей части."
            )
            out = f"{out}\n\n{fix}".strip()
            notes.append("consistency_fixed_99_vs_171")
    return out, notes


def count_quality_sources(matches: list[tuple[float, dict]]) -> int:
    def _parse_date(raw: str) -> datetime | None:
        val = (raw or "").strip()
        if not val:
            return None
        try:
            return datetime.strptime(val, "%d.%m.%Y")
        except Exception:
            return None

    score = 0
    for _, row in matches[:8]:
        meta = row.get("metadata", {}) or {}
        doc_type = str(meta.get("doc_type") or "").strip().upper()
        doc_no = str(meta.get("doc_number_text") or meta.get("doc_number_file") or "").strip()
        doc_date = str(meta.get("doc_date_file") or "").strip()
        is_official_type = doc_type in {"ФЕДЕРАЛЬНЫЙ ЗАКОН", "ПРИКАЗ", "ПОСТАНОВЛЕНИЕ", "РАСПОРЯЖЕНИЕ"}
        if not is_official_type:
            continue
        if not doc_no:
            continue
        dt = _parse_date(doc_date)
        if dt and dt.date() > datetime.now().date():
            continue
        score += 1
    return score


def derive_confidence_label(
    validation_text: str,
    unverified_refs_replaced: int,
    suspicious_doc_numbers: list[str],
    quality_sources: int,
) -> tuple[str, list[str]]:
    validation_low = (validation_text or "").lower()
    suspicious_count = len(suspicious_doc_numbers or [])
    reasons: list[str] = []

    low_due_validation = "частично или отсутствуют" in validation_low
    if low_due_validation:
        reasons.append("контент покрывает ключевые сущности частично")
    if suspicious_count > 0:
        reasons.append(f"обнаружены спорные реквизиты НПА: {suspicious_count}")
    if unverified_refs_replaced > 0:
        reasons.append(f"автозамена непроверенных реквизитов: {unverified_refs_replaced}")
    if quality_sources < 2:
        reasons.append("мало качественных официальных источников в выдаче")

    if low_due_validation or suspicious_count >= 2:
        return "Низкая", reasons[:2] or ["недостаточно подтверждений в контексте"]
    if unverified_refs_replaced > 0 or suspicious_count == 1 or quality_sources < 3:
        return "Средняя", reasons[:2] or ["часть деталей требует ручной проверки"]
    return "Высокая", ["критичные факты подтверждаются источниками выдачи"]
