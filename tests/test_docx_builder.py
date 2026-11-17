"""Тести побудови документів .docx, таблиць, колонок, додатків та пакетної генерації."""
from __future__ import annotations

from io import BytesIO

from docx import Document
from docx.shared import Cm, Pt

from app import config
from app.core import cleaners, dates, templates
from app.docx import builder, validator
from tests.helpers import (
    BEST_DATE,
    BEST_REASON,
    REF_TODAY,
    STUDS_IARD_4,
    STUDS_IBIB_4,
    STUDS_IKNI_37,
    STUDS_IKTA_21,
    absence_answers,
    assert_clean_check,
    assert_hanging,
    assert_two_col_table_layout,
    make_spec,
)


def test_absence_thresholds_in_memory() -> None:
    assert templates.INLINE_COLS_THRESHOLD == 4
    assert templates.APPENDIX_THRESHOLD == 15
    head = (
        f"Просимо Вас вважати відсутність на заняттях {BEST_DATE} "
        f"як з поважних причин у зв’язку з {BEST_REASON}"
    )

    p1, a1 = templates.b_absence({"date": BEST_DATE, "reason": BEST_REASON, "students": ["Андрія Федика БД-206"]})
    assert a1 is None
    assert p1 == [{"t": f"{head} студента Андрія Федика, БД-206.", "k": "body"}]
    p1c, a1c = templates.b_absence({"date": BEST_DATE, "reason": BEST_REASON, "students": ["Андрія Федика, БД-206"]})
    assert a1c is None and p1c == p1

    for n in (2, 3):
        studs = STUDS_IBIB_4[:n]
        a = absence_answers("ІБІБ", studs)
        spec = make_spec("absence", a)
        assert spec["appendix"] is None
        assert [x["k"] for x in spec["paras"]] == ["body"] + ["list"] * n
        assert spec["paras"][0]["t"] == f"{head} наступних студентів:"
        assert all(x["t"] == f"-\t{s}" for x, s in zip(spec["paras"][1:], studs))
        pv = builder.preview_text(spec)
        assert "-\t" not in pv and all(f"- {s}" in pv for s in studs)
        data = builder.build_docx([spec])
        assert_clean_check("absence", a, spec, data)
        doc = Document(BytesIO(data))
        assert len(doc.tables) == 0
        assert any(p.text == f"{head} наступних студентів:" for p in doc.paragraphs)
        assert not any("на парах" in p.text for p in doc.paragraphs)
        list_ps = [p for p in doc.paragraphs if p.text.startswith("-\t")]
        assert len(list_ps) == n
        for p in list_ps:
            assert_hanging(p, 1.27, -0.63, 1.27, keep=True)

    for n in (10, 14):
        studs = STUDS_IKNI_37[:n]
        a = absence_answers("ІКНІ", studs)
        spec = make_spec("absence", a)
        assert spec["appendix"] is None
        assert len(spec["paras"]) == 2
        assert spec["paras"][0]["t"] == f"{head} наступних студентів:"
        assert spec["paras"][1] == {"k": "cols", "items": studs}
        pv = builder.preview_text(spec)
        assert "-\t" not in pv and all(f"- {s}" in pv for s in studs)
        data = builder.build_docx([spec])
        assert_clean_check("absence", a, spec, data)
        doc = Document(BytesIO(data))
        assert len(doc.tables) == 1
        assert any(p.text == f"{head} наступних студентів:" for p in doc.paragraphs)
        assert not any("на парах" in p.text for p in doc.paragraphs)
        c0, c1 = assert_two_col_table_layout(doc.tables[0], 8.8, 8.2)
        half = (n + 1) // 2
        assert [p.text for p in c0.paragraphs] == [f"-\t{s}" for s in studs[:half]]
        assert [p.text for p in c1.paragraphs] == [f"-\t{s}" for s in studs[half:]]
        for p in c0.paragraphs:
            assert_hanging(p, 1.27, -0.55, 1.27, keep=True)
        for p in c1.paragraphs:
            assert_hanging(p, 0.55, -0.55, 0.55, keep=True)

    long_studs = STUDS_IKNI_37[:9] + ["Дмитро-Маркіян Карпяк, АВ-32"]
    a_long = absence_answers("ІКНІ", long_studs)
    spec_long = make_spec("absence", a_long)
    data_long = builder.build_docx([spec_long])
    assert_clean_check("absence", a_long, spec_long, data_long)
    doc_long = Document(BytesIO(data_long))
    c0_long, c1_long = assert_two_col_table_layout(doc_long.tables[0], 8.8, 8.2)
    assert [p.text for p in c0_long.paragraphs] == [f"-\t{s}" for s in long_studs[:5]]
    assert [p.text for p in c1_long.paragraphs] == [f"-\t{s}" for s in long_studs[5:]]

    studs15 = STUDS_IKNI_37[:15]
    a15 = absence_answers("ІКНІ", studs15)
    spec15 = make_spec("absence", a15)
    assert spec15["paras"] == [{"t": f"{head} студентів, зазначених у Додатку 1.", "k": "body"}]
    assert spec15["appendix"] == {"kind": "students", "title": "Додаток 1", "items": studs15}
    issues15 = validator.check("absence", a15, spec15, today=REF_TODAY)
    assert ("info", "Студентів у списку: 15 (Додаток 1)") in issues15, issues15
    assert not any(lv in ("err", "warn") for lv, _ in issues15), issues15


def _sample_rooms_ntb() -> bytes:
    date_in = "24.11.2026"
    time_in = "15:00-20:00"
    a = {
        "what": "залу на другому поверсі науково-технічної бібліотеки",
        "date": dates.format_dates(date_in),
        "_dates": [[s.isoformat(), e.isoformat()] for s, e in dates.parse_dates(date_in)],
        "time": dates.format_time(time_in),
        "_time": list(dates.parse_time(time_in)),
        "purpose": "проведення квартирника",
        "responsible": (
            "Голова проєктного відділу Колегії та профкому студентів та аспірантів – Гладчук Святослав "
            "та члени проєктного відділу Колегії та профкому студентів та аспірантів – "
            "Сорока Оксана, Перун Христина, Миронюк Владислав, Лепак Анджела та Семіков Гліб"
        ),
    }
    spec = make_spec("rooms", a)
    assert spec["appendix"] is None
    data = builder.build_docx([spec])
    assert_clean_check("rooms", a, spec, data)

    doc = Document(BytesIO(data))
    assert len(doc.tables) == 0
    texts = [p.text for p in doc.paragraphs]
    assert "Проректору" in texts and "Ігорю ГЕЛЬЖИНСЬКОМУ" in texts
    assert "КЛОПОТАННЯ" in texts
    assert any(
        "залу на другому поверсі науково-технічної бібліотеки 24 листопада 2026 року з 15:00 год до 20:00 год для проведення квартирника."
        in t
        for t in texts
    )
    assert any(t.startswith("Відповідальні за проведення: Голова проєктного відділу") for t in texts)
    return data


def test_rooms_ntb() -> None:
    _sample_rooms_ntb()


def _sample_absence_ikta_21() -> bytes:
    a = absence_answers("ІКТА", STUDS_IKTA_21)
    spec = make_spec("absence", a)
    issues = validator.check("absence", a, spec, today=REF_TODAY)
    assert ("info", "Студентів у списку: 21 (Додаток 1)") in issues, issues
    data = builder.build_docx([spec])
    assert_clean_check("absence", a, spec, data)

    doc = Document(BytesIO(data))
    assert len(doc.tables) == 1
    expected_body = (
        f"Просимо Вас вважати відсутність на заняттях {BEST_DATE} "
        f"як з поважних причин у зв’язку з {BEST_REASON} студентів, зазначених у Додатку 1."
    )
    assert any(p.text == expected_body for p in doc.paragraphs)
    title_p = [p for p in doc.paragraphs if p.text == "Додаток 1"]
    assert len(title_p) == 1
    assert title_p[0].paragraph_format.page_break_before is True
    assert title_p[0].paragraph_format.space_after == Pt(14)

    c0, c1 = assert_two_col_table_layout(doc.tables[0])
    col0 = [p.text for p in c0.paragraphs]
    col1 = [p.text for p in c1.paragraphs]
    assert len(col0) == 11 and len(col1) == 10
    assert col0[0] == "1.\tБойко Божена, КБ-305"
    assert col0[-1] == "11.\tМатусевич Ярослав, ІР-14"
    assert col1[0] == "12.\tБіляк Діана, ІР-14"
    assert col1[-1] == "21.\tСергієнко Владислав, КІ-103"
    for cell in (c0, c1):
        for p in cell.paragraphs:
            assert_hanging(p, 0.9, -0.9, 0.9, keep=None)
    return data


def test_absence_ikta_21() -> None:
    _sample_absence_ikta_21()


def _sample_absence_ikni_37() -> bytes:
    a = absence_answers("ІКНІ", STUDS_IKNI_37)
    spec = make_spec("absence", a)
    issues = validator.check("absence", a, spec, today=REF_TODAY)
    assert ("info", "Студентів у списку: 37 (Додаток 1)") in issues, issues
    data = builder.build_docx([spec])
    assert_clean_check("absence", a, spec, data)

    doc = Document(BytesIO(data))
    assert len(doc.tables) == 1
    c0, c1 = assert_two_col_table_layout(doc.tables[0])
    col0 = [p.text for p in c0.paragraphs]
    col1 = [p.text for p in c1.paragraphs]
    assert len(col0) == 19 and len(col1) == 18
    assert col0[0] == "1.\tЛисяк Яніна, СА-32"
    assert col0[4] == "5.\tКлименко Нікіта, ITIC-11"
    assert col0[-1] == "19.\tДуманська Наталія, ПЗ-33"
    assert col1[0] == "20.\tКотюк Софія, ПЗ-32"
    assert col1[5] == "25.\tНікіфореску Марк-Тіберій, ПЗ-13"
    assert col1[-1] == "37.\tДевдюк Стас, ОІ-11"
    return data


def test_absence_ikni_37() -> None:
    _sample_absence_ikni_37()


def check_inline_4(inst: str, studs: list[str]) -> bytes:
    a = absence_answers(inst, studs)
    spec = make_spec("absence", a)
    assert spec["appendix"] is None
    issues = validator.check("absence", a, spec, today=REF_TODAY)
    assert ("info", "Студентів у списку: 4") in issues, issues
    pv = builder.preview_text(spec)
    assert "-\t" not in pv and all(f"- {s}" in pv for s in studs)

    data = builder.build_docx([spec])
    assert_clean_check("absence", a, spec, data)
    doc = Document(BytesIO(data))
    assert len(doc.tables) == 1
    c0, c1 = assert_two_col_table_layout(doc.tables[0], 8.8, 8.2)
    assert [p.text for p in c0.paragraphs] == [f"-\t{s}" for s in studs[:2]]
    assert [p.text for p in c1.paragraphs] == [f"-\t{s}" for s in studs[2:]]
    for p in c0.paragraphs:
        assert_hanging(p, 1.27, -0.55, 1.27, keep=True)
    for p in c1.paragraphs:
        assert_hanging(p, 0.55, -0.55, 0.55, keep=True)
    return data


def test_with_appendix_num_and_batch_in_memory() -> None:
    ibib = make_spec("absence", absence_answers("ІБІБ", STUDS_IBIB_4))
    ikta = make_spec("absence", absence_answers("ІКТА", STUDS_IKTA_21))
    ikni = make_spec("absence", absence_answers("ІКНІ", STUDS_IKNI_37))

    assert builder.with_appendix_num(ibib, 1) == ibib
    ikta_1 = builder.with_appendix_num(ikta, 1)
    ikni_2 = builder.with_appendix_num(ikni, 2)
    pv1 = builder.preview_text(ikta_1)
    pv2 = builder.preview_text(ikni_2)
    assert "у Додатку 1." in pv1 and "[Додаток 1: 21 студ.]" in pv1 and len(pv1) < 4096
    assert "у Додатку 2." in pv2 and "[Додаток 2: 37 студ.]" in pv2 and len(pv2) < 4096

    batch_bytes = builder.build_docx([ibib, ikta, ikni])
    doc = Document(BytesIO(batch_bytes))
    texts = [p.text for p in doc.paragraphs]
    assert any("зазначених у Додатку 1." in t for t in texts)
    assert any("зазначених у Додатку 2." in t for t in texts)
    pb_texts = [p.text for p in doc.paragraphs if p.paragraph_format.page_break_before]
    assert pb_texts == ["Додаток 1", "", "Додаток 2"], pb_texts
    rep = validator.check_docx(batch_bytes, today=REF_TODAY)
    assert "Знайшов клопотань: <b>3</b>" in rep[0], rep
    assert not any("❌" in line or "⚠️" in line for line in rep), rep


def test_photo_templates_in_memory() -> None:
    p_fem, app_fem = templates.b_absence(
        {
            "date": BEST_DATE,
            "reason": BEST_REASON,
            "students": ["Ярош Марти Ігорівни ПП-16"],
            "who": "студентки",
        }
    )
    assert app_fem is None
    assert p_fem == [
        {
            "t": f"Просимо Вас вважати відсутність на заняттях {BEST_DATE} "
            f"як з поважних причин у зв’язку з {BEST_REASON} студентки Ярош Марти Ігорівни, ПП-16.",
            "k": "body",
        }
    ]
    tpl_abs = templates.TEMPLATES["absence"]
    assert "who" in [s.key for s in templates.visible_steps(tpl_abs, {"students": ["Ярош Марти Ігорівни ПП-16"]})]
    assert "who" not in [s.key for s in templates.visible_steps(tpl_abs, {"students": STUDS_IBIB_4[:2]})]

    eq_date_in = "24-26.10.2026"
    eq_a = {
        "items": "семи паяльних станцій",
        "date": dates.format_dates(eq_date_in),
        "_dates": [[s.isoformat(), e.isoformat()] for s, e in dates.parse_dates(eq_date_in)],
        "purpose": "з метою проведення події BEST Engineering Competition",
        "organizers": "Колегія та профком студентів та аспірантів",
        "responsible": "президент локального осередку BEST Lviv – Святослав Гонський",
        "_resp_n": 1,
    }
    eq_spec = make_spec("equipment", eq_a)
    assert [p["t"] for p in eq_spec["paras"]] == [
        "Просимо Вашого дозволу на використання семи паяльних станцій 24-26 жовтня 2026 року "
        "з метою проведення події BEST Engineering Competition.",
        "Організатори: Колегія та профком студентів та аспірантів.",
        "Відповідальний за проведення: президент локального осередку BEST Lviv – Святослав Гонський.",
    ]
    assert_clean_check("equipment", eq_a, eq_spec, builder.build_docx([eq_spec]))

    aud_date_in = "31.10.2026"
    aud_time_in = "09:00-19:00"
    aud_single = {
        "num": "214",
        "building": "головного навчального корпусу",
        "when_kind": "Одноразово",
        "date": dates.format_dates(aud_date_in),
        "_dates": [[s.isoformat(), e.isoformat()] for s, e in dates.parse_dates(aud_date_in)],
        "time": dates.format_time(aud_time_in),
        "_time": list(dates.parse_time(aud_time_in)),
        "purpose": "проведення дебатного турніру",
    }
    assert make_spec("audience", aud_single)["paras"] == [
        {
            "t": "Просимо Вашого дозволу на використання приміщення 214 аудиторії головного навчального корпусу "
            "31 жовтня 2026 року з 09:00 год до 19:00 год для проведення дебатного турніру.",
            "k": "body",
        }
    ]
    aud_multi = {
        **aud_single,
        "num": "401,402, 403, 404, 405",
        "building": "навчального корпусу №1",
        "responsible": "Голова проєктного відділу Колегії та профкому студентів та аспірантів – Гладчук Святослав",
        "_resp_n": 1,
    }
    aud_spec = make_spec("audience", aud_multi)
    assert aud_spec["paras"][0]["t"] == (
        "Просимо Вашого дозволу на використання приміщень 401, 402, 403, 404, 405 аудиторій навчального корпусу №1 "
        "31 жовтня 2026 року з 09:00 год до 19:00 год для проведення дебатного турніру."
    )
    assert_clean_check("audience", aud_multi, aud_spec, builder.build_docx([aud_spec]))
    bad_issues = validator.check("audience", {**aud_multi, "num": "актова"}, aud_spec, today=REF_TODAY)
    assert any(lv == "warn" and "Номер аудиторії" in msg for lv, msg in bad_issues), bad_issues

    placing_spec = make_spec(
        "placing",
        {
            "where": "у холі",
            "what": "фотозони",
            "date": "26 листопада 2026 року",
            "time": "10:00-18:00",
            "purpose": "для того, щоб провести ярмарок",
        },
    )
    placing_txt = placing_spec["paras"][0]["t"]
    assert "з метою для того" not in placing_txt and "для того, щоб провести ярмарок." in placing_txt, placing_txt


def _sample_guest_names() -> bytes:
    date_in = "26-30.10.2026"
    a = {
        "who": "двох осіб",
        "date": dates.format_dates(date_in),
        "_dates": [[s.isoformat(), e.isoformat()] for s, e in dates.parse_dates(date_in)],
        "project": "проєкту «Плацкарт»",
        "names": ["Іваненко Олена Петрівна", "Петренко Петро Іванович"],
    }
    spec = make_spec("guest", a)
    assert spec["paras"] == [
        {
            "t": "Просимо Вас забезпечити поселення двох осіб, зазначених нижче, на період 26-30 жовтня 2026 року "
            "в межах проєкту «Плацкарт» на безкоштовній основі.",
            "k": "body",
        },
        {"t": "Іваненко Олена Петрівна", "k": "names"},
        {"t": "Петренко Петро Іванович", "k": "names"},
    ]
    assert "names" in [s.key for s in templates.TEMPLATES["guest"].steps]
    data = builder.build_docx([spec])
    assert_clean_check("guest", a, spec, data)
    doc = Document(BytesIO(data))
    texts = [p.text for p in doc.paragraphs]
    i = texts.index(spec["paras"][0]["t"])
    assert texts[i + 1] == "", texts[i:i + 4]
    for p, name in zip(doc.paragraphs[i + 2:i + 4], a["names"]):
        pf = p.paragraph_format
        assert p.text == name
        assert abs(pf.left_indent - Cm(1.27)) < Cm(0.01)
        assert not pf.first_line_indent

    no_names = make_spec("guest", {**a, "names": []})
    assert no_names["paras"] == [{
        "t": "Просимо Вас забезпечити поселення двох осіб на період 26-30 жовтня 2026 року "
        "в межах проєкту «Плацкарт» на безкоштовній основі.",
        "k": "body",
    }]
    return data


def test_guest_names_in_memory() -> None:
    _sample_guest_names()


def test_sport_inventory_in_memory() -> None:
    inv_what = "спортивного інвентарю навчального корпусу №22"
    assert inv_what in templates.SPORT

    tpl_sport = templates.TEMPLATES["sport"]
    assert "inv" not in [s.key for s in templates.visible_steps(tpl_sport, {"what": inv_what})]
    assert "inv" in [s.key for s in templates.visible_steps(tpl_sport, {"what": templates.SPORT[0]})]

    date_in = "25.10.2026"
    a = {
        "what": inv_what,
        "date": dates.format_dates(date_in),
        "_dates": [[s.isoformat(), e.isoformat()] for s, e in dates.parse_dates(date_in)],
        "purpose": "проведення змагань з бігу",
        "responsible": "Голова спортивного відділу Колегії та профкому студентів та аспірантів – Іванов Іван",
        "_resp_n": 1,
    }
    spec = make_spec("sport", a)
    assert spec["addressee"] == config.ADDRESSEES["helzhynskyi"][1]
    assert spec["paras"] == [
        {
            "t": "Просимо Вашого дозволу на використання спортивного інвентарю навчального корпусу №22 "
            "25 жовтня 2026 року для проведення змагань з бігу.",
            "k": "body",
        },
        {
            "t": "Відповідальний за проведення: Голова спортивного відділу Колегії та профкому "
            "студентів та аспірантів – Іванов Іван.",
            "k": "body",
        },
    ]
    assert_clean_check("sport", a, spec, builder.build_docx([spec]))

    # Якщо для залу обрано додатковий інвентар, адресатом лишається завкафедри фізвиховання.
    hall_a = {**a, "what": templates.SPORT[0], "inv": "Так (клопотання піде завідувачу кафедри фізвиховання)"}
    hall_spec = make_spec("sport", hall_a)
    assert hall_spec["addressee"] == config.ADDRESSEES["fizvykhovannia"][1]
    assert "та спортивного інвентарю" in hall_spec["paras"][0]["t"]
    assert "заходу та використання інвентарю:" in hall_spec["paras"][1]["t"]

    # Зали корп. №34 та вибір адресата (Гельжинський / Поліщук / Левків)
    assert "приміщення футбольного залу навчального корпусу №34" in templates.SPORT
    assert "приміщення баскетбольного залу навчального корпусу №34" in templates.SPORT
    assert "addressee" in [s.key for s in templates.visible_steps(tpl_sport, {"what": templates.SPORT[0]})]
    fields_a = {**a, "what": "2-ох футбольних полів за адресою Лукаша, 4"}
    assert make_spec("sport", fields_a)["addressee"] == config.ADDRESSEES["studmistechko"][1]
    explicit_helzh = make_spec("sport", {**hall_a, "addressee": "helzhynskyi"})
    assert explicit_helzh["addressee"] == config.ADDRESSEES["helzhynskyi"][1]


def test_config_and_award_in_memory() -> None:
    for fname in ("officials.json", "responsibles.json", "institutes.json", "places.json"):
        assert (config.DATA_DIR / fname).is_file(), fname
    all_resp_people = [p for roles in config.RESPONSIBLES.values() for r in roles for p in r["people"]]
    assert len(all_resp_people) == len(set(all_resp_people)), "Duplicate person in RESPONSIBLES"
    assert set(config.INSTITUTES) == set(config.INSTITUTE_PEOPLE)
    assert "ІБІБ" in config.INSTITUTES and "ІБІС" not in config.INSTITUTES
    assert "ІКТЕ" in config.INSTITUTES and "ІТРЕ" not in config.INSTITUTES
    assert "ІПМТ" in config.INSTITUTE_PEOPLE and "ІПІТ" not in config.INSTITUTE_PEOPLE
    assert config.INSTITUTES["ІКТЕ"][1] == "Леоніду ОЗІРКОВСЬКОМУ"
    assert "ІПІТ" in config.LEGACY_INSTITUTES
    imfn_names = {p[0] for p in config.INSTITUTE_PEOPLE["ІМФН"]}
    for name in ("Сушельницька Софія", "Сушельницька Ірина", "Лесяк Роман", "Гвоздовська Софія", "Похна Софія"):
        assert name in imfn_names, name
    assert any(p[0] == "Суканець Олег" for p in config.INSTITUTE_PEOPLE["ІБІБ"])
    from app.core.responsibles import institute_parts
    ibib_parts = institute_parts("ІБІБ", config.INSTITUTE_PEOPLE["ІБІБ"])
    assert any("Голова спортивного відділу Колегії та профбюро студентів ІБІБ – Суканець Олег" == p[0] for p in ibib_parts), ibib_parts
    ihht_names = {p[0] for p in config.INSTITUTE_PEOPLE["ІХХТ"]}
    for name in ("Літвінчук Анастасія", "Сухобрус Таїсія", "Дудка Ярослав", "Тарнавчик Олена", "Зеленько Марія"):
        assert name in ihht_names, name
    from app.core.responsibles import role_parts
    deputy_role = config.RESPONSIBLES["🤝 Заступники / заступниці"][0]
    assert role_parts(deputy_role, ["Пенгрин Романа", "Андибур Анастасія"])[0][0].startswith("Заступниці Голів ")
    assert "навчального корпусу №9" in templates.BUILDINGS

    norm = cleaners.normalize_award_students(
        [
            "  1. Оршак Максим Олександрович\tІПМТ\tрк-31 ",
            "Богайчик Софія Володимирівна ІНЕМ ЕБ-32",
            "Мірінчик Богдан Віталійович, ІГСН, аспірант",
            "Васильків Мар'ян Вікторович ІБІБ БДАД",
            "Неповний рядок",
        ]
    )
    assert norm == [
        ["Оршак Максим Олександрович", "ІПМТ", "РК-31"],
        ["Богайчик Софія Володимирівна", "ІНЕМ", "ЕБ-32"],
        ["Мірінчик Богдан Віталійович", "ІГСН", "аспірант"],
        ["Васильків Мар’ян Вікторович", "ІБІБ", "БДАД"],
        ["Неповний рядок", "", ""],
    ], norm

    rows_16 = [[f"Студент {k}", "ІПМТ", f"РК-{10 + k}"] for k in range(1, 17)]
    a_inline = {"form": "бюджетної", "reason": "активну громадську діяльність", "students": rows_16}
    spec_inline = make_spec("award", a_inline)
    assert spec_inline["addressee"] == config.ADDRESSEES["rector"][1]
    assert spec_inline["appendix"] is None
    assert spec_inline["paras"][0]["t"] == (
        "Просимо Вас преміювати за активну громадську діяльність таких студентів бюджетної форми навчання:"
    )
    assert spec_inline["paras"][1] == {"k": "rows", "items": rows_16}
    data_inline = builder.build_docx([spec_inline])
    assert_clean_check("award", a_inline, spec_inline, data_inline)
    doc_inline = Document(BytesIO(data_inline))
    assert len(doc_inline.tables) == 1 and len(doc_inline.tables[0].rows) == 16 and len(doc_inline.tables[0].columns) == 3

    rows_41 = [[f"Студент {k}", "ІБІБ", f"БД-{100 + k}"] for k in range(1, 42)]
    a_app = {"form": "комерційної", "reason": "організацію на «Тижні першокурсника»", "students": rows_41}
    spec_app = make_spec("award", a_app)
    assert spec_app["appendix"] == {"kind": "award", "title": "Додаток 1", "items": rows_41}
    assert "(Додаток 1):" in spec_app["paras"][0]["t"]
    spec_app2 = builder.with_appendix_num(spec_app, 2)
    assert "(Додаток 2):" in spec_app2["paras"][0]["t"] and spec_app2["appendix"]["title"] == "Додаток 2"
    data_app = builder.build_docx([spec_app])
    assert_clean_check("award", a_app, spec_app, data_app)
    doc_app = Document(BytesIO(data_app))
    assert len(doc_app.tables) == 1 and len(doc_app.tables[0].rows) == 41 and len(doc_app.tables[0].columns) == 4
    assert doc_app.tables[0].rows[0].cells[0].text == "1." and doc_app.tables[0].rows[40].cells[0].text == "41."

    bad_issues = validator.check(
        "award",
        {**a_inline, "students": [["Іванов Іван", "ІХЗ", "ЕЕ-11"], ["Іванов Іван", "", ""]]},
        spec_inline,
        today=REF_TODAY,
    )
    assert any(lv == "warn" and "невідомий інститут" in msg for lv, msg in bad_issues), bad_issues
    assert any(lv == "warn" and "дублікати" in msg for lv, msg in bad_issues), bad_issues


def test_audience_weekdays_and_purchase_fund_in_memory() -> None:
    aud_weekdays = {
        "num": "018",
        "building": "головного навчального корпусу",
        "when_kind": "У будні дні протягом семестру",
        "sem": "осіннього семестру 2026/2027 навчального року",
        "time": "з 08:00 год до 21:00 год",
        "purpose": "проведення засідань Колегії та профбюро студентів ІЕСК",
        "responsible": "Голова Колегії та профбюро студентів ІЕСК – Удуд Христина",
        "addressee": "institute",
        "inst": "ІЕСК",
    }
    aud_spec = make_spec("audience", aud_weekdays)
    assert "Андрію МАЛЯРУ" in aud_spec["addressee"]
    assert "у будні дні протягом осіннього семестру 2026/2027 навчального року з 08:00 год до 21:00 год" in aud_spec["paras"][0]["t"]
    assert_clean_check("audience", aud_weekdays, aud_spec, builder.build_docx([aud_spec]))

    pur_a = {
        "kind": "Сприяння у закупівлі техніки (Благодійний фонд)",
        "items": [
            "Проектор Samsung The Freestyle 2nd Gen; 1; 30000",
            "Фотоапарат Sony Alpha a7S III Body; 2*; 120000",
        ],
        "note": "Закупівля по 1 одиниці, однак, за можливості, у кількості 2 одиниць.",
        "addressee": "rector",
    }
    pur_spec = make_spec("purchase", pur_a)
    assert pur_spec["addressee"] == config.ADDRESSEES["rector"][1]
    assert "Просимо Вашого сприяння у закупівлі техніки, зазначеної у Додатку 1," in pur_spec["paras"][0]["t"]
    assert "Благодійного фонду" in pur_spec["paras"][0]["t"]
    assert pur_spec["appendix"]["rows"][1][2] == "2*"
    assert pur_spec["appendix"]["rows"][-1][-1] == "270000"
    pur_spec2 = builder.with_appendix_num(pur_spec, 2)
    assert "у Додатку 2," in pur_spec2["paras"][0]["t"]
    data = builder.build_docx([pur_spec])
    assert_clean_check("purchase", pur_a, pur_spec, data)
    doc = Document(BytesIO(data))
    assert doc.tables[0].rows[2].cells[2].text == "2*"
    assert any("Закупівля по 1 одиниці" in p.text for p in doc.paragraphs)

    non_fund_paras, _ = templates.b_purchase(
        {
            "kind": "Забезпечення технікою та обладнанням (стандартне)",
            "items": ["Мікрофон; 1; 1000"],
        }
    )
    assert "Благодійного фонду" not in non_fund_paras[0]["t"]
