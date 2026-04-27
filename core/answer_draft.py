from __future__ import annotations

from dataclasses import dataclass, field
import re


SECTION_TITLES = {
    "краткий ответ": "summary",
    "что сделать заявителю сейчас": "actions",
    "какие документы подготовить": "documents",
    "что нужно уточнить у заявителя": "clarifications",
    "цитата нормы": "norm_quote",
    "проверка актуальности норм": "checks",
    "источники": "sources",
}


@dataclass
class AnswerDraft:
    summary: str = ""
    actions: list[str] = field(default_factory=list)
    documents: list[str] = field(default_factory=list)
    clarifications: list[str] = field(default_factory=list)
    checks: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    norm_quote: str = ""


def parse_user_markdown_to_draft(text: str) -> AnswerDraft:
    draft = AnswerDraft()
    if not text:
        return draft
    blocks = re.split(r"(?m)^###\s+", text.strip())
    for raw in blocks:
        raw = raw.strip()
        if not raw:
            continue
        if "\n" not in raw:
            title = raw.lower().strip()
            body = ""
        else:
            title, body = raw.split("\n", 1)
            title = title.strip().lower()
            body = body.strip()
        key = SECTION_TITLES.get(title)
        if not key:
            # Keep unknown parts in summary tail to avoid data loss.
            if body:
                draft.summary = f"{draft.summary}\n\n{body}".strip()
            continue
        if key in {"actions", "documents", "clarifications", "checks", "sources"}:
            lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
            setattr(draft, key, lines)
        else:
            setattr(draft, key, body)
    return draft


def render_draft_to_user_markdown(draft: AnswerDraft) -> str:
    lines: list[str] = []
    lines.append("### Краткий ответ")
    lines.append(draft.summary.strip() or "Недостаточно данных в предоставленном контексте.")
    lines.append("")

    lines.append("### Что сделать заявителю сейчас")
    lines.extend(draft.actions or ["- Проверить применимые нормы и порядок подачи."])
    lines.append("")

    lines.append("### Какие документы подготовить")
    lines.extend(draft.documents or ["- Подготовить заявление и подтверждающие документы по профилю вопроса."])
    lines.append("")

    lines.append("### Что нужно уточнить у заявителя")
    lines.extend(draft.clarifications or ["- Уточнить вид деятельности и субъект Российской Федерации."])
    lines.append("")

    if draft.norm_quote.strip():
        lines.append("### Цитата нормы")
        lines.append(draft.norm_quote.strip())
        lines.append("")

    lines.append("### Проверка актуальности норм")
    lines.extend(draft.checks or ["- Сверьте редакцию применимых НПА на дату обращения."])
    lines.append("")

    lines.append("### Источники")
    lines.extend(draft.sources or ["- [Портал официальных публикаций правовых актов](http://publication.pravo.gov.ru)"])
    return "\n".join(lines).strip()
