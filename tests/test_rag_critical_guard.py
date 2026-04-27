import app


def _mk_match(
    text: str,
    doc_type: str = "ФЕДЕРАЛЬНЫЙ ЗАКОН",
    doc_number: str = "171-ФЗ",
    source_file: str = "fz-22_11_1995.rtf",
):
    return (
        1.0,
        {
            "text": text,
            "metadata": {
                "doc_type": doc_type,
                "doc_number_text": doc_number,
                "source_file": source_file,
            },
        },
    )


def test_retail_query_detection_true():
    q = "Кто выдает лицензию на розничную продажу алкоголя?"
    assert app.is_retail_license_authority_query(q) is True


def test_retail_query_detection_false():
    q = "Какие документы нужны для продления лицензии на производство?"
    assert app.is_retail_license_authority_query(q) is False


def test_guard_corrects_forbidden_federal_claim():
    question = "Кто выдает лицензию на розничную продажу алкоголя?"
    bad_answer = (
        "Лицензию на розничную продажу алкогольной продукции выдает "
        "Росалкогольрегулирование."
    )
    matches = [_mk_match("... статья 19 171-ФЗ ...")]
    fixed, notes = app.enforce_critical_fact_guard(question, bad_answer, matches)
    assert "субъекта Российской Федерации" in fixed
    assert "retail_authority_corrected" in notes
    assert "retail_authority_forbidden_claim_detected" in notes


def test_guard_keeps_correct_answer():
    question = "Кто выдает лицензию на розничную продажу алкоголя?"
    good_answer = (
        "Лицензия на розничную продажу алкогольной продукции выдается "
        "уполномоченным органом исполнительной власти субъекта Российской Федерации."
    )
    matches = [_mk_match("... статья 19 171-ФЗ ...")]
    fixed, notes = app.enforce_critical_fact_guard(question, good_answer, matches)
    assert fixed == good_answer
    assert notes == []


def test_sanitize_hallucinated_doc_mentions_removes_unknown_bullets():
    text = (
        "### Источники\n"
        "- Постановление №723 от 17.07.2012\n"
        "- Федеральный закон №171-ФЗ\n"
        "В тексте встречается №374-ФЗ."
    )
    cleaned, removed = app.sanitize_hallucinated_doc_mentions(text, ["723", "374-фз"])
    assert removed >= 1
    assert "№723" not in cleaned
    assert "№171-ФЗ" in cleaned
    assert "реквизит требует проверки" in cleaned


def test_build_prompts_include_retail_jurisdiction_rule():
    matches = [_mk_match("... статья 16 и 19 171-ФЗ ...")]
    legal_prompt = app.build_legal_prompt("Кто выдает розничную лицензию?", matches)
    concise_prompt = app.build_concise_prompt("Кто выдает розничную лицензию?", matches, [])
    assert "уполномоченным органом субъекта Российской Федерации" in legal_prompt
    assert "орган выдачи лицензии — уполномоченный орган субъекта РФ" in concise_prompt


def test_sanitize_does_not_corrupt_171_when_single_digit_hallucination_present():
    text = "См. [Федеральный закон № 171-ФЗ](http://www.kremlin.ru/acts/bank/8506)."
    cleaned, removed = app.sanitize_hallucinated_doc_mentions(text, ["1"])
    assert removed == 0
    assert "№ 171-ФЗ" in cleaned
    assert "НПА вне текущего контекста71-ФЗ" not in cleaned
    assert "НПА вне текущего контекста" not in cleaned


def test_find_doc_numbers_ignores_single_digit_markers():
    used = app.find_doc_numbers_in_text("Пункт №1 и закон №171-ФЗ.")
    assert "1" not in used
    assert "171" in used
    assert "171-фз" in used


def test_sanitize_keeps_markdown_link_line_unchanged():
    line = "- [Федеральный закон № 171-ФЗ](http://www.kremlin.ru/acts/bank/8506)"
    cleaned, removed = app.sanitize_hallucinated_doc_mentions(line, ["171"])
    assert removed == 1
    assert cleaned == ""


def test_sanitize_uses_harmless_placeholder():
    text = "В тексте упомянут №723, которого нет в контексте."
    cleaned, _ = app.sanitize_hallucinated_doc_mentions(text, ["723"])
    assert "реквизит требует проверки" in cleaned
    assert "НПА вне текущего контекста" not in cleaned


def test_sanitize_unverified_doc_refs_keeps_allowed_and_replaces_unknown():
    matches = [_mk_match("...", doc_number="171-ФЗ")]
    text = "См. №171-ФЗ и №723."
    cleaned, replaced = app.sanitize_unverified_doc_refs(text, matches)
    assert "№171-ФЗ" in cleaned
    assert "№ [проверить реквизит]" in cleaned
    assert replaced >= 1


def test_enforce_strict_sources_rebuilds_from_matches():
    matches = [_mk_match("...", doc_number="171-ФЗ")]
    text = "### Краткий ответ\nТест.\n\n### Источники\n- Левый источник\n\n### Официальные ссылки\n- x"
    rebuilt, removed = app.enforce_strict_sources(text, matches, limit=4)
    assert removed is True
    assert "- Левый источник" not in rebuilt
    assert "### Источники" in rebuilt
    assert "171-ФЗ" in rebuilt


def test_applicant_clarification_retail_avoids_transport_checklist():
    q = "Кто выдает лицензию на розничную продажу алкоголя?"
    bullets = app.applicant_clarification_bullets(q)
    joined = " ".join(bullets).lower()
    assert "дал/год" not in joined
    assert "нефасованная спиртосодержащая" not in joined


def test_applicant_clarification_transport_keeps_ethanol_context():
    q = "Какие документы нужны для лицензии на перевозки этилового спирта?"
    bullets = app.applicant_clarification_bullets(q)
    joined = " ".join(bullets).lower()
    assert "этилов" in joined or "спирт" in joined
    assert "перевоз" in joined or "дал" in joined


def test_llm_unavailability_bannermentions_fallback():
    b = app.llm_availability_user_banner("[LLM недоступна] Error code: 503")
    assert "Сервис генерации временно недоступен" in b
    assert "локального контекста" in b


def test_build_requisites_review_block_when_unverified_present():
    block = app.build_requisites_review_block(2)
    assert "Контроль реквизитов" in block
    assert "проверить реквизит" in block


def test_dedupe_sources_sections_merges_same_law_variants():
    text = (
        "### Краткий ответ\nok\n\n"
        "### Источники\n"
        "- Федеральный закон № 171-ФЗ\n"
        "- 171-фз\n"
        "- [Федеральный закон №171-ФЗ](http://example.com)\n"
    )
    out = app.dedupe_sources_sections(text)
    assert out.count("### Источники") == 1
    # Only one bullet for the 171-FZ family should remain.
    assert out.count("\n- ") == 1


def test_sanitize_clarification_removes_transport_bullets_for_non_transport_question():
    q = "Кто выдает лицензию на розничную продажу алкоголя?"
    text = (
        "### Краткий ответ\nok\n\n"
        "### Что нужно уточнить у заявителя\n"
        "- Тип продукции: этиловый спирт или нефасованная спиртосодержащая продукция (>25%).\n"
        "- Планируемый годовой объем перевозок (в дал/год).\n"
        "- Субъект РФ и адрес объекта.\n"
    )
    out = app.sanitize_clarification_block_by_topic(text, q)
    assert "дал/год" not in out.lower()
    assert "нефасованная спиртосодержащая" not in out.lower()
    assert "Субъект РФ и адрес объекта." in out


def test_license_term_guard_injects_five_years_fact_when_missing():
    q = "На какой срок может быть выдана или продлена лицензия?"
    text = "Срок действия лицензии в предоставленных источниках не уточняется."
    fixed, notes = app.enforce_license_term_guard(q, text, [_mk_match("... статья 18 171-ФЗ ...")])
    assert ("пяти лет" in fixed.lower()) or ("5 лет" in fixed.lower())
    assert "license_term_corrected" in notes


def test_user_mode_sanitizer_drops_critical_fact_header():
    q = "Кто выдает лицензию на розничную продажу алкоголя?"
    text = (
        "### Критическая проверка фактов\n"
        "Служебный блок.\n\n"
        "### Краткий ответ\n"
        "Лицензию выдает субъект РФ.\n\n"
        "### Источники\n- x"
    )
    out = app.ensure_user_friendly_answer_with_sources(text, [_mk_match("...")], q)
    assert "Критическая проверка фактов" not in out


def test_user_mode_retail_force_direct_competence_fact():
    q = "Кто выдает лицензию на розничную продажу алкоголя?"
    text = "### Краткий ответ\nНужно уточнить в источниках."
    out = app.ensure_user_friendly_answer_with_sources(text, [_mk_match("...")], q)
    low = out.lower()
    assert "уполномоч" in low and "субъект" in low


def test_user_mode_fee_question_adds_33333_anchor():
    q = "Какой порядок уплаты госпошлины при лицензировании?"
    text = "### Краткий ответ\nОплатите госпошлину."
    out = app.ensure_user_friendly_answer_with_sources(text, [_mk_match("...")], q)
    assert "333.33" in out
    assert "333.40" in out


def test_user_mode_field_assessment_exceptions_adds_point_29():
    q = "В каких случаях выездная оценка может не проводиться?"
    text = "### Краткий ответ\nНужно проверить правила."
    out = app.ensure_user_friendly_answer_with_sources(text, [_mk_match("...")], q)
    assert "пункте 29" in out or "пункт 29" in out


def test_user_mode_statement_details_adds_article_19_anchor():
    q = "Какие сведения должны быть в заявлении о выдаче лицензии?"
    text = "### Краткий ответ\nУкажите сведения о заявителе."
    out = app.ensure_user_friendly_answer_with_sources(text, [_mk_match("...")], q)
    low = out.lower()
    assert "заявлен" in low
    assert "статье 19" in low or "статья 19" in low


def test_user_mode_fixation_question_adds_order_397_anchor():
    q = "Какие требования к специальным техническим средствам фиксации движения?"
    text = "### Краткий ответ\nТребования устанавливаются профильным приказом."
    out = app.ensure_user_friendly_answer_with_sources(text, [_mk_match("...")], q)
    assert ("№ 397" in out) or ("№397" in out)


def test_user_mode_submission_channel_adds_unified_portal_anchor():
    q = "Можно ли продлить лицензию без подачи через Госуслуги, на бумажном носителе?"
    text = "### Краткий ответ\nПодайте заявление через Госуслуги."
    out = app.ensure_user_friendly_answer_with_sources(text, [_mk_match("...")], q)
    low = out.lower()
    assert "единый портал" in low
    assert ("№ 199" in out) or ("№199" in out)


def test_user_mode_rejection_question_adds_article19_anchor():
    q = "Какие основания для отказа в выдаче лицензии?"
    text = "### Краткий ответ\nНужно проверить причины отказа."
    out = app.ensure_user_friendly_answer_with_sources(text, [_mk_match("...")], q)
    low = out.lower()
    assert "статье 19" in low or "статья 19" in low


def test_user_mode_adds_required_sections_when_missing():
    q = "Какие документы нужны для продления лицензии на алкоголь?"
    text = "Ответ без структуры."
    out = app.ensure_user_friendly_answer_with_sources(text, [_mk_match("...")], q)
    assert "### Краткий ответ" in out
    assert "### Что сделать заявителю сейчас" in out
    assert "### Какие документы подготовить" in out
    assert "### Что нужно уточнить у заявителя" in out
    assert "### Проверка актуальности норм" in out


def test_user_mode_adds_norm_quote_for_article_question():
    q = "Какие ключевые сведения должны быть в заявлении согласно статье 19 171-ФЗ?"
    text = "### Краткий ответ\nСведения указываются по закону."
    match = _mk_match(
        "Статья 19. Для получения лицензии организация представляет заявление с указанием сведений о заявителе и объекте деятельности.",
        doc_type="ФЕДЕРАЛЬНЫЙ ЗАКОН",
        doc_number="171-ФЗ",
    )
    out = app.ensure_user_friendly_answer_with_sources(text, [match], q)
    assert "### Цитата нормы" in out
    assert "Статья 19" in out
    assert "Источник цитаты" in out


def test_user_mode_adds_norm_quote_for_number_reference_question():
    q = "В каких случаях выездная оценка не проводится по постановлению №1720?"
    text = "### Краткий ответ\nПроверьте исключения по правилам."
    match = _mk_match(
        "Пункт 29 Правил: выездная оценка не проводится при досрочном прекращении лицензии и в иных случаях, указанных в правилах.",
        doc_type="ПОСТАНОВЛЕНИЕ",
        doc_number="1720",
    )
    out = app.ensure_user_friendly_answer_with_sources(text, [match], q)
    assert "### Цитата нормы" in out
    assert "Пункт 29" in out


def test_user_mode_quote_source_label_is_canonical_for_document_type():
    q = "Какие сведения должны быть в заявлении по статье 19 171-ФЗ?"
    text = "### Краткий ответ\nСведения определяются законом."
    row = (
        1.0,
        {
            "text": "Статья 19. Заявление о выдаче лицензии включает сведения о заявителе и объекте деятельности.",
            "metadata": {
                "doc_type": "ДОКУМЕНТ",
                "doc_number_text": "171-ФЗ",
                "source_file": "random.txt",
            },
        },
    )
    out = app.ensure_user_friendly_answer_with_sources(text, [row], q)
    assert "Источник цитаты: Федеральный закон №171-ФЗ" in out
    assert "Источник цитаты: ДОКУМЕНТ" not in out


def test_user_mode_quote_filters_consultant_metadata_noise():
    q = "Как соотносятся 99-ФЗ и 171-ФЗ?"
    text = "### Краткий ответ\nПрименяется специальная норма 171-ФЗ."
    match = _mk_match(
        "Документ предоставлен КонсультантПлюс www.consultant.ru Дата сохранения: 02.04.2024 "
        "Федеральный закон от 22.11.1995 N 171-ФЗ определяет специальное регулирование.",
        doc_type="ФЕДЕРАЛЬНЫЙ ЗАКОН",
        doc_number="171-ФЗ",
    )
    out = app.ensure_user_friendly_answer_with_sources(text, [match], q)
    assert "КонсультантПлюс" not in out
    assert "Дата сохранения" not in out
    assert "www.consultant.ru" not in out


def test_user_mode_skips_norm_quote_for_non_reference_question():
    q = "Кто выдает лицензию на розничную продажу алкоголя?"
    text = "### Краткий ответ\nЛицензию выдает уполномоченный орган субъекта РФ."
    out = app.ensure_user_friendly_answer_with_sources(text, [_mk_match("...")], q)
    assert "### Цитата нормы" not in out


def test_user_mode_retail_action_block_is_contextual():
    q = "Какой орган компетентен выдавать лицензию на розничную продажу алкогольной продукции?"
    text = "### Краткий ответ\nЛицензию выдает уполномоченный орган субъекта РФ."
    out = app.ensure_user_friendly_answer_with_sources(text, [_mk_match("...")], q)
    assert "уполномоченный орган субъекта РФ" in out or "уполномоченный орган субъекта рф" in out.lower()


def test_user_mode_clarification_fixation_is_contextual():
    q = "Какие требования к средствам автоматической фиксации движения при лицензировании?"
    out = app.ensure_user_friendly_answer_with_sources("### Краткий ответ\nТребования установлены профильными приказами.", [_mk_match("...")], q)
    low = out.lower()
    assert "глонасс" in low or "gps" in low
    assert "егаис" in low


def test_user_mode_clarification_sources_of_funds_is_contextual():
    q = "Какими документами подтверждаются источники происхождения денежных средств для уставного капитала?"
    out = app.ensure_user_friendly_answer_with_sources("### Краткий ответ\nНужно подтвердить происхождение средств.", [_mk_match("...")], q)
    low = out.lower()
    assert "банк" in low
    assert "период" in low


def test_user_mode_clarification_99_vs_171_mentions_collision():
    q = "Как соотносятся 99-ФЗ и 171-ФЗ?"
    out = app.ensure_user_friendly_answer_with_sources("### Краткий ответ\n171-ФЗ — специальный закон.", [_mk_match("...")], q)
    low = out.lower()
    assert "коллиз" in low


def test_question_intent_dispatcher_detects_core_intents():
    assert app.question_intent("Какой порядок уплаты госпошлины?") == "fee"
    assert app.question_intent("Как соотносятся 99-ФЗ и 171-ФЗ?") == "law_relation_99_171"
    assert app.question_intent("Какие сведения в заявлении о выдаче лицензии?") == "statement_details"
    assert app.question_intent("Что должно быть обеспечено коммуникациями между единицами оборудования?") == "equipment_communications"


def test_user_mode_submission_channel_fact_consistency_fixes_paper_phrase():
    q = "Можно ли продлить лицензию на бумажном носителе без Госуслуг?"
    text = "### Краткий ответ\nДа, допускается подача на бумажном носителе."
    out = app.ensure_user_friendly_answer_with_sources(text, [_mk_match("...")], q)
    low = out.lower()
    assert "бумажный канал не применяется" in low or "подача осуществляется через епгу" in low


def test_user_mode_quote_quality_drops_noisy_quote():
    q = "Как соотносятся 99-ФЗ и 171-ФЗ?"
    noisy = _mk_match(
        "Документ предоставлен КонсультантПлюс www.consultant.ru Дата сохранения: 02.04.2024",
        doc_type="ФЕДЕРАЛЬНЫЙ ЗАКОН",
        doc_number="171-ФЗ",
    )
    out = app.ensure_user_friendly_answer_with_sources("### Краткий ответ\n171-ФЗ является специальным.", [noisy], q)
    assert "### Цитата нормы" not in out


def test_user_mode_quote_prefers_expected_doc_number_from_question():
    q = "Что изменяет постановление №648 в порядке лицензирования?"
    text = "### Краткий ответ\nНужно учитывать профильное постановление."
    wrong = _mk_match(
        "Топливо твердое, топливо печное бытовое и керосин...",
        doc_type="ПОСТАНОВЛЕНИЕ",
        doc_number="239",
    )
    correct = _mk_match(
        "Постановление №648 устанавливает порядок лицензирования перевозок этилового спирта и "
        "нефасованной спиртосодержащей продукции автомобильным транспортом, включая требования "
        "к сведениям и порядку контроля в рамках лицензионной процедуры.",
        doc_type="ПОСТАНОВЛЕНИЕ",
        doc_number="648",
    )
    out = app.ensure_user_friendly_answer_with_sources(text, [wrong, correct], q)
    assert "Источник цитаты" in out
    assert "№648" in out
    assert "№239" not in out


def test_user_mode_comparative_question_adds_99_and_171_even_without_explicit_99():
    q = "Какой федеральный закон задаёт общие правила лицензирования вместе со специальными нормами по алкоголю?"
    out = app.ensure_user_friendly_answer_with_sources("### Краткий ответ\nПрименяется специальный закон.", [_mk_match("...")], q)
    low = out.lower()
    assert "99-фз" in low or "99 фз" in low
    assert "171-фз" in low or "171 фз" in low


def test_user_mode_sources_of_funds_adds_735_anchor():
    q = "Какими документами подтверждаются источники происхождения денежных средств для уставного капитала?"
    out = app.ensure_user_friendly_answer_with_sources("### Краткий ответ\nНужно подтвердить источники.", [_mk_match("...")], q)
    assert "№735" in out or "№ 735" in out


def test_user_mode_equipment_list_action_block_is_not_generic():
    q = "Где закреплён перечень видов основного технологического оборудования для лицензирования?"
    text = "### Краткий ответ\nПеречень установлен приказом №405."
    out = app.ensure_user_friendly_answer_with_sources(text, [_mk_match("...")], q)
    low = out.lower()
    assert "№405" in out or "№ 405" in out
    assert "опись оборудования" in low


def test_sources_block_filters_future_placeholder_source():
    rows = [
        (
            1.0,
            {
                "text": "x",
                "metadata": {
                    "doc_type": "Документ",
                    "doc_date_file": "01.01.2026",
                    "source_kind": "guide",
                    "source_file": "future.txt",
                    "doc_title": "8. Документы о подключении к ЕГАИС",
                },
            },
        ),
        _mk_match("...", doc_type="ПРИКАЗ", doc_number="199", source_file="norm_199.rtf"),
    ]
    out = app.sources_block(rows, limit=4)
    assert "01.01.2026" not in out
    assert "№199" in out


def test_sources_block_dedupes_same_source_with_url():
    row = (
        1.0,
        {
            "text": "x",
            "metadata": {
                "doc_type": "ПРИКАЗ",
                "doc_number_text": "199",
                "doc_date_file": "12.08.2019",
                "doc_title": "Об утверждении Административного регламента",
            },
        },
    )
    out = app.sources_block([row, row], limit=4)
    assert out.count("№199") == 1


def test_sources_block_prefers_positive_relevance_for_question():
    rows = [
        (
            2.0,
            {
                "text": "Документы по уставному капиталу и происхождению денежных средств.",
                "metadata": {
                    "doc_type": "ПОСТАНОВЛЕНИЕ",
                    "doc_number_text": "735",
                    "doc_date_file": "31.05.2024",
                    "doc_title": "Про источники средств",
                },
            },
        ),
        (
            1.9,
            {
                "text": "Госпошлина, статья 333.33 НК РФ, порядок уплаты.",
                "metadata": {
                    "doc_type": "ПРИКАЗ",
                    "doc_number_text": "199",
                    "doc_date_file": "12.08.2019",
                    "doc_title": "Административный регламент",
                },
            },
        ),
    ]
    out = app.sources_block(rows, limit=4, question="Какой порядок уплаты и подтверждения госпошлины?")
    assert "№735" not in out


def test_sources_block_caps_noncore_sources_for_submission_channel():
    rows = [
        _mk_match("Подача заявления через ЕПГУ в электронной форме.", doc_type="ПРИКАЗ", doc_number="199"),
        _mk_match("Общие требования к оказанию госуслуг.", doc_type="ПОСТАНОВЛЕНИЕ", doc_number="2466"),
        _mk_match("Справочный фоновый порядок рассмотрения.", doc_type="ПОСТАНОВЛЕНИЕ", doc_number="423"),
    ]
    out = app.sources_block(
        rows,
        limit=4,
        question="Через какой канал подавать заявление на продление лицензии?",
    )
    assert "№199" in out
    assert ("№2466" in out) != ("№423" in out)


def test_sources_block_ensures_min_three_for_procedural_intent():
    rows = [
        _mk_match("Подача через ЕПГУ и ключевые сведения заявления.", doc_type="ПРИКАЗ", doc_number="199"),
        _mk_match("Требования к заявлению и проверка сведений.", doc_type="ФЕДЕРАЛЬНЫЙ ЗАКОН", doc_number="171-ФЗ"),
        _mk_match("Порядок административных процедур.", doc_type="ПОСТАНОВЛЕНИЕ", doc_number="1720"),
    ]
    out = app.sources_block(
        rows,
        limit=4,
        question="Какие ключевые сведения должны быть в заявлении о выдаче лицензии?",
    )
    assert out.count("\n- [") >= 3


def _row(cid: str, meta: dict, text: str = "x") -> dict:
    return {
        "chunk_id": cid,
        "text": text,
        "metadata": {"doc_type": "ФЕДЕРАЛЬНЫЙ ЗАКОН", "doc_number_text": "171-ФЗ", **meta},
        "tf": {"x": 1},
        "len": 1,
    }


def test_hierarchy_graph_expands_linear_neighbors():
    rows = {
        "d::c1": _row(
            "d::c1",
            {"neighbor_next_chunk_id": "d::c2", "article_key": "d::ст9", "article_part_index": 1},
        ),
        "d::c2": _row(
            "d::c2",
            {
                "neighbor_prev_chunk_id": "d::c1",
                "neighbor_next_chunk_id": "d::c3",
                "article_key": "d::ст9",
                "article_part_index": 2,
            },
        ),
        "d::c3": _row("d::c3", {"neighbor_prev_chunk_id": "d::c2", "article_key": "d::ст9", "article_part_index": 3}),
    }
    article_map = {"d::ст9": ["d::c1", "d::c2", "d::c3"]}
    matches = [(10.0, rows["d::c2"])]
    out = app._expand_matches_graph(
        matches,
        rows,
        article_map,
        official_only=True,
        neighbor_hops=1,
        max_extra_chunks=10,
        small_article_max_parts=4,
    )
    ids = {app.chunk_row_key(r) for _, r in out}
    assert ids == {"d::c1", "d::c2", "d::c3"}


def test_hierarchy_graph_fills_small_article_gap():
    rows = {
        "d::c1": _row("d::c1", {"article_key": "d::ст5", "article_part_index": 1}),
        "d::c2": _row("d::c2", {"article_key": "d::ст5", "article_part_index": 2}),
    }
    article_map = {"d::ст5": ["d::c1", "d::c2"]}
    matches = [(8.0, rows["d::c1"])]
    out = app._expand_matches_graph(
        matches,
        rows,
        article_map,
        official_only=True,
        neighbor_hops=0,
        max_extra_chunks=10,
        small_article_max_parts=4,
    )
    ids = {app.chunk_row_key(r) for _, r in out}
    assert "d::c2" in ids


def test_chunk_corpus_sequence_metadata():
    import importlib.util
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("chunk_corpus", root / "scripts" / "chunk_corpus.py")
    assert spec and spec.loader
    cc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cc)
    recs = [
        {
            "chunk_id": "doc::chunk_0001",
            "doc_id": "doc",
            "text": "a",
            "metadata": {"doc_type": "ФЕДЕРАЛЬНЫЙ ЗАКОН"},
        },
        {
            "chunk_id": "doc::chunk_0002",
            "doc_id": "doc",
            "text": "b",
            "metadata": {"doc_type": "ФЕДЕРАЛЬНЫЙ ЗАКОН"},
        },
    ]
    cc._link_chunk_sequence(recs, doc_id="doc", block={"article_number": "18", "chapter_title": "Глава 2"})
    m0, m1 = recs[0]["metadata"], recs[1]["metadata"]
    assert m0.get("neighbor_next_chunk_id") == "doc::chunk_0002"
    assert m1.get("neighbor_prev_chunk_id") == "doc::chunk_0001"
    assert m0.get("article_key") == "doc::ст18"
    assert m0.get("article_part_total") == 2
    dense = cc.list_density_score("1) первый пункт\n2) второй пункт\n3) третий пункт")
    assert dense > 0.5


def test_parent_child_expansion_pulls_same_parent_neighbors():
    rows = {
        "d::c1": _row("d::c1", {"article_key": "d::ст18", "article_part_index": 1, "chunk_index": 1}),
        "d::c2": _row("d::c2", {"article_key": "d::ст18", "article_part_index": 2, "chunk_index": 2}),
        "d::c3": _row("d::c3", {"article_key": "d::ст18", "article_part_index": 3, "chunk_index": 3}),
    }
    scored = [(12.0, rows["d::c2"]), (11.0, rows["d::c1"]), (10.0, rows["d::c3"])]
    matches = [(12.0, rows["d::c2"])]
    out = app._expand_matches_parent_child(
        scored,
        matches,
        rows,
        {"article::d::ст18": ["d::c1", "d::c2", "d::c3"]},
        official_only=True,
        top_k=3,
        parent_top_n=3,
        max_extra_chunks=6,
        window=2,
        full_parent_parts=5,
    )
    ids = {app.chunk_row_key(r) for _, r in out}
    assert {"d::c1", "d::c2", "d::c3"} <= ids


def test_query_norm_refs_extracts_article_and_subpoint():
    q = "171-ФЗ статья 19 подпункт 3 какие документы"
    refs = app.query_norm_refs(q)
    assert "171-фз" in refs
    assert "ст19" in refs
    assert "171-фз:ст19" in refs
    assert "пп3" in refs


def test_query_norm_refs_extracts_doc_number():
    q = "Что говорит приказ №199 по срокам?"
    refs = app.query_norm_refs(q)
    assert "199" in refs


def test_parent_child_window_for_list_query_is_wider():
    q = "Где закреплен перечень видов оборудования?"
    assert app.parent_child_window_for_query(q) >= 3


def test_user_mode_includes_decision_header_and_confidence():
    q = "Можно ли продлить лицензию без подачи через Госуслуги, на бумажном носителе?"
    out = app.ensure_user_friendly_answer_with_sources(
        "### Краткий ответ\nПодайте заявление через ЕПГУ.",
        [_mk_match("...")],
        q,
        include_trust_blocks=True,
    )
    assert "### Decision header" in out
    assert "- Итог:" in out
    assert "- Канал подачи:" in out
    assert "- Критичный риск:" in out
    assert "### Уверенность ответа" in out


def test_user_mode_adds_status_prefixes_to_action_and_clarification_blocks():
    q = "Какие документы нужны для продления лицензии на алкоголь?"
    out = app.ensure_user_friendly_answer_with_sources("### Краткий ответ\nНужно подготовить пакет.", [_mk_match("...")], q)
    assert "Обязательно:" in out
    assert "Рекомендуется:" in out
    assert "Проверить:" in out


def test_user_mode_confidence_becomes_low_on_suspicious_references():
    q = "Какими документами подтверждаются источники происхождения денежных средств для уставного капитала?"
    out = app.ensure_user_friendly_answer_with_sources(
        "### Краткий ответ\nПодтверждение по профилю вопроса.",
        [_mk_match("...")],
        q,
        suspicious_doc_numbers=["723", "9999"],
        include_trust_blocks=True,
    )
    assert "**Низкая**" in out


def test_decision_header_summary_is_human_friendly_for_submission_channel():
    q = "Можно ли продлить лицензию без подачи через Госуслуги, на бумажном носителе?"
    out = app.ensure_user_friendly_answer_with_sources(
        "### Краткий ответ\nПодайте заявление через ЕПГУ.",
        [_mk_match("...")],
        q,
        include_trust_blocks=True,
    )
    assert "Итог: Продление подается через ЕПГУ; бумажный канал не применяется." in out


def test_user_mode_default_hides_trust_blocks():
    q = "Какой порядок уплаты и подтверждения госпошлины при подаче заявления на лицензирование?"
    out = app.ensure_user_friendly_answer_with_sources("### Краткий ответ\nОплатите пошлину.", [_mk_match("...")], q)
    assert "### Decision header" not in out
    assert "### Уверенность ответа" not in out


def test_point33_docs_query_returns_explicit_documents_list():
    q = "Какие документы указаны в подпунктах 1–3, 6 пункта 33 Административного регламента?"
    row = _mk_match(
        "Для получения лицензии заявитель вправе представить:\n"
        "1) копии документов о государственной регистрации транспорта;\n"
        "2) копии документов, подтверждающих право владения/пользования транспортом;\n"
        "3) сведения о технических средствах фиксации движения;\n"
        "6) копии сертификатов соответствия и (или) деклараций о соответствии оборудования учета.\n",
        doc_type="ПРИКАЗ",
        doc_number="199",
    )
    row[1]["metadata"]["section_title"] = "Для получения лицензии на перевозки"
    out = app.ensure_user_friendly_answer_with_sources("### Краткий ответ\nСм. перечень.", [row], q)
    assert "1) Копия документа о государственной регистрации заявителя." in out
    assert "2) Копия документа о постановке заявителя на учет в налоговом органе" in out
    assert "3) Копия документа об уплате государственной пошлины за предоставление лицензии." in out
    assert "6) Копия документа, подтверждающего значение координат характерных точек границ" in out


def test_point33_docs_query_keeps_only_subpoints_1_3_and_6():
    q = "Какие документы указаны в подпунктах 1–3, 6 пункта 33 Административного регламента?"
    row = _mk_match(
        "1) документ о госрегистрации; 2) документ о постановке на учет; "
        "3) документ об уплате госпошлины; 4) документ по лаборатории; "
        "5) документы по помещениям; 6) документ по координатам границ.",
        doc_type="ПРИКАЗ",
        doc_number="199",
    )
    row[1]["metadata"]["section_title"] = "Для получения лицензии на перевозки"
    out = app.ensure_user_friendly_answer_with_sources("### Краткий ответ\nСм. перечень.", [row], q)
    assert "1) Копия документа о государственной регистрации заявителя." in out
    assert "2) Копия документа о постановке заявителя на учет в налоговом органе" in out
    assert "3) Копия документа об уплате государственной пошлины за предоставление лицензии." in out
    assert "6) Копия документа, подтверждающего значение координат характерных точек границ" in out
    assert "4) документ по лаборатории" not in out
    assert "5) документы по помещениям" not in out


def test_explicit_documents_list_query_falls_back_to_no_info_when_no_list_found():
    q = "Нужен список документов для процедуры."
    out = app.ensure_user_friendly_answer_with_sources(
        "### Краткий ответ\nПо вопросу применяются нормы регламента без раскрытого перечня.",
        [_mk_match("Текст без нумерованного списка и без явных документов.")],
        q,
    )
    assert "нет явного перечня документов по этому вопросу" in out


def test_explicit_documents_list_query_extracts_numbered_items_from_matches():
    q = "Какие документы нужны? Нужен список документов."
    row = _mk_match(
        "1) заявление о выдаче лицензии; 2) копия документа об уплате госпошлины; "
        "3) документы, подтверждающие право пользования объектом.",
        doc_type="ПРИКАЗ",
        doc_number="199",
    )
    out = app.ensure_user_friendly_answer_with_sources("### Краткий ответ\nСм. перечень.", [row], q)
    assert "1) заявление о выдаче лицензии" in out
    assert "2) копия документа об уплате госпошлины" in out
    assert "3) документы, подтверждающие право пользования объектом" in out
