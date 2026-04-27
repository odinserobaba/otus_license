from __future__ import annotations

import re

from .answer_draft import AnswerDraft


def with_status_prefixes(items: list[str], mode: str) -> list[str]:
    if not items:
        return items
    out: list[str] = []
    labels = ["Обязательно", "Рекомендуется", "Проверить"]
    for i, line in enumerate(items):
        clean = line.strip()
        if not clean:
            continue
        bullet = clean if clean.startswith("- ") else f"- {clean.lstrip('- ').strip()}"
        body = bullet[2:].strip()
        if mode == "clarifications":
            label = "Проверить"
        else:
            label = labels[min(i, len(labels) - 1)]
        if body.lower().startswith(("обязательно:", "рекомендуется:", "проверить:")):
            out.append(f"- {body}")
            continue
        out.append(f"- {label}: {body}")
    return out


def infer_submission_channel(question: str, body_text: str) -> str:
    ql = (question or "").lower()
    low = (body_text or "").lower()
    if "епгу" in low or "единый портал" in low or "госуслуг" in ql:
        return "ЕПГУ (электронная подача)"
    if "субъект" in low and "рознич" in ql:
        return "Уполномоченный орган субъекта РФ"
    return "По профильному регламенту"


def infer_critical_risk(body_text: str, confidence_label: str) -> str:
    low = (body_text or "").lower()
    if "бумажный канал не применяется" in low:
        return "Неверный канал подачи может привести к отказу"
    if "проверить реквизит" in low:
        return "Есть непроверенные реквизиты НПА"
    if confidence_label == "Низкая":
        return "Нужна ручная юридическая верификация перед действием"
    return "Критичных конфликтов не выявлено"


def _normalize_summary_line(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    text = re.sub(r"^#+\s*", "", text)
    text = re.sub(r"^\*\*|\*\*$", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > 180:
        text = text[:177].rstrip() + "..."
    return text


def infer_human_summary(question: str, body_text: str) -> str:
    ql = (question or "").lower()
    low = (body_text or "").lower()
    if ("госуслуг" in ql or "бумаж" in ql or "портал" in ql) and ("продл" in ql and "лиценз" in ql):
        return "Продление подается через ЕПГУ; бумажный канал не применяется."
    if "госпошлин" in ql or "пошлин" in ql:
        return "Госпошлина уплачивается до подачи заявления, с проверкой реквизитов и статуса платежа."
    if "рознич" in ql and "лиценз" in ql and ("кто" in ql or "орган" in ql):
        return "Розничную лицензию выдает уполномоченный орган исполнительной власти субъекта РФ."
    if ("выезд" in ql and "оцен" in ql) and ("исключ" in ql or "не провод" in ql):
        return "Выездная оценка не проводится только в прямо установленных исключениях."
    if "сведен" in ql and "заявлен" in ql:
        return "Заявление должно содержать обязательные сведения по статье 19 171-ФЗ."
    # Fallback: use first meaningful sentence/line from answer body.
    for line in (body_text or "").splitlines():
        clean = _normalize_summary_line(line)
        if not clean:
            continue
        if clean.lower().startswith(("краткий ответ", "источники", "что сделать", "какие документы", "что нужно")):
            continue
        if clean.startswith("- "):
            clean = clean[2:].strip()
        return clean
    # Secondary fallback by sentence split.
    for sent in re.split(r"(?<=[.!?])\s+", (body_text or "").strip()):
        clean = _normalize_summary_line(sent)
        if clean:
            return clean
    return "Ответ требует просмотра ключевых блоков ниже."


def build_decision_header(
    question: str,
    body_text: str,
    confidence_label: str,
) -> str:
    summary = infer_human_summary(question, body_text)
    channel = infer_submission_channel(question, body_text)
    risk = infer_critical_risk(body_text, confidence_label)
    return (
        "### Decision header\n"
        f"- Итог: {summary}\n"
        f"- Канал подачи: {channel}\n"
        f"- Критичный риск: {risk}"
    )


def build_confidence_block(label: str, reasons: list[str]) -> str:
    lines = [f"### Уверенность ответа\n**{label}**"]
    if reasons:
        for reason in reasons[:2]:
            lines.append(f"- {reason}")
    return "\n".join(lines)


def render_answer_with_trust_blocks(
    draft: AnswerDraft,
    decision_header: str,
    confidence_block: str,
) -> str:
    draft.actions = with_status_prefixes(draft.actions, mode="actions")
    draft.clarifications = with_status_prefixes(draft.clarifications, mode="clarifications")
    sections: list[str] = [decision_header, confidence_block, ""]
    sections.append("### Краткий ответ")
    sections.append(draft.summary.strip() or "Недостаточно данных в предоставленном контексте.")
    sections.append("")
    sections.append("### Что сделать заявителю сейчас")
    sections.extend(draft.actions)
    sections.append("")
    sections.append("### Какие документы подготовить")
    sections.extend(draft.documents)
    sections.append("")
    sections.append("### Что нужно уточнить у заявителя")
    sections.extend(draft.clarifications)
    sections.append("")
    if draft.norm_quote.strip():
        sections.append("### Цитата нормы")
        sections.append(draft.norm_quote.strip())
        sections.append("")
    sections.append("### Проверка актуальности норм")
    sections.extend(draft.checks)
    sections.append("")
    sections.append("### Источники")
    sections.extend(draft.sources)
    return "\n".join(sections).strip()


def render_answer_without_trust_blocks(draft: AnswerDraft) -> str:
    draft.actions = with_status_prefixes(draft.actions, mode="actions")
    draft.clarifications = with_status_prefixes(draft.clarifications, mode="clarifications")
    sections: list[str] = []
    sections.append("### Краткий ответ")
    sections.append(draft.summary.strip() or "Недостаточно данных в предоставленном контексте.")
    sections.append("")
    sections.append("### Что сделать заявителю сейчас")
    sections.extend(draft.actions)
    sections.append("")
    sections.append("### Какие документы подготовить")
    sections.extend(draft.documents)
    sections.append("")
    sections.append("### Что нужно уточнить у заявителя")
    sections.extend(draft.clarifications)
    sections.append("")
    if draft.norm_quote.strip():
        sections.append("### Цитата нормы")
        sections.append(draft.norm_quote.strip())
        sections.append("")
    sections.append("### Проверка актуальности норм")
    sections.extend(draft.checks)
    sections.append("")
    sections.append("### Источники")
    sections.extend(draft.sources)
    return "\n".join(sections).strip()
