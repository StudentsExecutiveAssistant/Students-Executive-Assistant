"""Тести побудови документів .docx, таблиць, додатків та пакетної генерації."""

from __future__ import annotations

from io import BytesIO
from typing import Any

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
	assert_indented_list,
	make_spec,
)


def _nb(s: str) -> str:
	return builder._keep_groups_together(s)


def test_absence_thresholds_in_memory() -> None:
	assert templates.APPENDIX_THRESHOLD == 9
	head = (
		f"Просимо Вас вважати відсутність на заняттях {BEST_DATE} "
		f"як з поважних причин у зв’язку з {BEST_REASON}"
	)

	p1, a1 = templates.b_absence(
		{"date": BEST_DATE, "reason": BEST_REASON, "students": ["Андрія Федика БД-206"]}
	)
	assert a1 is None
	assert p1 == [{"t": f"{head} студента Андрія Федика БД-206.", "k": "body"}]
	p1c, a1c = templates.b_absence(
		{"date": BEST_DATE, "reason": BEST_REASON, "students": ["Андрія Федика, БД-206"]}
	)
	assert a1c is None and p1c == p1
	doc1 = Document(
		BytesIO(
			builder.build_docx(
				[make_spec("absence", absence_answers("ІБІБ", ["Андрія Федика, БД-206"]))]
			)
		)
	)
	assert any("Андрія Федика БД\u2011206." in p.text for p in doc1.paragraphs)

	p_comma_list, a_comma_list = templates.b_absence(
		{
			"date": BEST_DATE,
			"reason": BEST_REASON,
			"students": ["Бойко Божена, КБ-305", "Д’яченко Назар ОІ-31"],
			"in_appendix": "У тексті (на одному аркуші)",
		}
	)
	assert a_comma_list is None
	assert [x["t"] for x in p_comma_list[1:]] == [
		"Бойко Божена КБ-305",
		"Д’яченко Назар ОІ-31",
	]

	for n in (2, 4, 8):
		studs = STUDS_IKNI_37[:n]
		a = absence_answers("ІКНІ", studs, in_appendix="У тексті (на одному аркуші)")
		spec = make_spec("absence", a)
		assert spec["appendix"] is None
		assert [x["k"] for x in spec["paras"]] == ["body"] + ["list"] * n
		assert spec["paras"][0]["t"] == f"{head} наступних студентів:"
		assert [x["t"] for x in spec["paras"][1:]] == studs
		pv = builder.preview_text(spec)
		assert "-\t" not in pv and not any(f"- {s}" in pv for s in studs)
		assert all(s in pv for s in studs)
		data = builder.build_docx([spec])
		assert_clean_check("absence", a, spec, data)
		doc = Document(BytesIO(data))
		assert len(doc.tables) == 0
		assert any(p.text == f"{head} наступних студентів:" for p in doc.paragraphs)
		assert not any(p.text.startswith(("-\t", "- ")) for p in doc.paragraphs)
		body_idx = next(
			i
			for i, p in enumerate(doc.paragraphs)
			if p.text == f"{head} наступних студентів:"
		)
		list_ps = doc.paragraphs[body_idx + 1 : body_idx + 1 + n]
		assert [p.text for p in list_ps] == [_nb(s) for s in studs]
		for p in list_ps:
			assert_indented_list(p, 1.27, keep=True)

	for n in (2, 8):
		studs = STUDS_IKNI_37[:n]
		a_app = absence_answers("ІКНІ", studs, in_appendix="У Додатку 1")
		spec_app = make_spec("absence", a_app)
		assert spec_app["paras"] == [
			{"t": f"{head} студентів, зазначених у Додатку 1.", "k": "body"}
		]
		assert spec_app["appendix"] == {
			"kind": "students",
			"title": "Додаток 1",
			"items": studs,
		}
		data_app = builder.build_docx([spec_app])
		assert_clean_check("absence", a_app, spec_app, data_app)
		doc_app = Document(BytesIO(data_app))
		assert len(doc_app.tables) == 0
		app_idx = next(i for i, p in enumerate(doc_app.paragraphs) if p.text == "Додаток 1")
		app_ps = doc_app.paragraphs[app_idx + 1 : app_idx + 1 + n]
		assert [p.text for p in app_ps] == [_nb(s) for s in studs]
		for p in app_ps:
			assert_indented_list(p, 1.27, keep=None)

	for n in (9, 15):
		studs = STUDS_IKNI_37[:n]
		a_force = absence_answers("ІКНІ", studs, in_appendix="У тексті (на одному аркуші)")
		spec_force = make_spec("absence", a_force)
		assert spec_force["paras"] == [
			{"t": f"{head} студентів, зазначених у Додатку 1.", "k": "body"}
		]
		assert spec_force["appendix"] == {
			"kind": "students",
			"title": "Додаток 1",
			"items": studs,
		}
		issues_force = validator.check("absence", a_force, spec_force, today=REF_TODAY)
		assert ("info", f"Студентів у списку: {n} (Додаток 1)") in issues_force, (
			issues_force
		)
		assert not any(lv in ("err", "warn") for lv, _ in issues_force), issues_force

	tpl_abs = templates.TEMPLATES["absence"]
	assert "in_appendix" not in [
		s.key for s in templates.visible_steps(tpl_abs, {"students": STUDS_IBIB_4[:1]})
	]
	assert "in_appendix" in [
		s.key for s in templates.visible_steps(tpl_abs, {"students": STUDS_IKNI_37[:2]})
	]
	assert "in_appendix" in [
		s.key for s in templates.visible_steps(tpl_abs, {"students": STUDS_IKNI_37[:8]})
	]
	assert "in_appendix" not in [
		s.key for s in templates.visible_steps(tpl_abs, {"students": STUDS_IKNI_37[:9]})
	]


def _sample_rooms_ntb() -> bytes:
	date_in = "24.11.2026"
	time_in = "15:00-20:00"
	a: dict[str, Any] = {
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
	assert any(
		t.startswith("Відповідальні за проведення: Голова проєктного відділу")
		for t in texts
	)
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
	assert len(doc.tables) == 0
	expected_body = (
		f"Просимо Вас вважати відсутність на заняттях {BEST_DATE} "
		f"як з поважних причин у зв’язку з {BEST_REASON} студентів, зазначених у Додатку 1."
	)
	assert any(p.text == expected_body for p in doc.paragraphs)
	title_idxs = [i for i, p in enumerate(doc.paragraphs) if p.text == "Додаток 1"]
	assert len(title_idxs) == 1
	title_idx = title_idxs[0]
	title_p = doc.paragraphs[title_idx]
	assert title_p.paragraph_format.page_break_before is True
	assert title_p.paragraph_format.space_after == Pt(14)

	stud_ps = doc.paragraphs[title_idx + 1 : title_idx + 1 + len(STUDS_IKTA_21)]
	assert [p.text for p in stud_ps] == [_nb(s) for s in STUDS_IKTA_21]
	assert stud_ps[0].text == "Бойко Божена КБ\u2011305"
	assert stud_ps[-1].text == "Сергієнко Владислав КІ\u2011103"
	for p in stud_ps:
		assert_indented_list(p, 1.27, keep=None)
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
	assert len(doc.tables) == 0
	title_idxs = [i for i, p in enumerate(doc.paragraphs) if p.text == "Додаток 1"]
	assert len(title_idxs) == 1
	title_idx = title_idxs[0]
	stud_ps = doc.paragraphs[title_idx + 1 : title_idx + 1 + len(STUDS_IKNI_37)]
	assert [p.text for p in stud_ps] == [_nb(s) for s in STUDS_IKNI_37]
	assert stud_ps[0].text == "Лисяк Яніна СА\u201132"
	assert stud_ps[4].text == "Клименко Нікіта ITIC\u201111"
	assert stud_ps[24].text == "Нікіфореску Марк-Тіберій ПЗ\u201113"
	assert stud_ps[-1].text == "Девдюк Стас ОІ\u201111"
	for p in stud_ps:
		assert_indented_list(p, 1.27, keep=None)
	return data


def test_absence_ikni_37() -> None:
	_sample_absence_ikni_37()


def check_inline_4(inst: str, studs: list[str]) -> bytes:
	a = absence_answers(inst, studs, in_appendix="У тексті (на одному аркуші)")
	spec = make_spec("absence", a)
	assert spec["appendix"] is None
	issues = validator.check("absence", a, spec, today=REF_TODAY)
	assert ("info", "Студентів у списку: 4") in issues, issues
	pv = builder.preview_text(spec)
	assert "-\t" not in pv and not any(f"- {s}" in pv for s in studs)
	assert all(s in pv for s in studs)

	data = builder.build_docx([spec])
	assert_clean_check("absence", a, spec, data)
	doc = Document(BytesIO(data))
	assert len(doc.tables) == 0
	expected_lines = [_nb(s) for s in studs]
	matched = [p for p in doc.paragraphs if p.text in expected_lines]
	assert [p.text for p in matched] == expected_lines
	for p in matched:
		assert_indented_list(p, 1.27, keep=True)
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
			f"як з поважних причин у зв’язку з {BEST_REASON} студентки Ярош Марти Ігорівни ПП-16.",
			"k": "body",
		}
	]
	tpl_abs = templates.TEMPLATES["absence"]
	assert "who" in [
		s.key
		for s in templates.visible_steps(
			tpl_abs, {"students": ["Ярош Марти Ігорівни ПП-16"]}
		)
	]
	assert "who" not in [
		s.key for s in templates.visible_steps(tpl_abs, {"students": STUDS_IBIB_4[:2]})
	]

	eq_date_in = "24-26.10.2026"
	eq_a: dict[str, Any] = {
		"items": "семи паяльних станцій",
		"date": dates.format_dates(eq_date_in),
		"_dates": [
			[s.isoformat(), e.isoformat()] for s, e in dates.parse_dates(eq_date_in)
		],
		"purpose": "з метою проведення події BEST Engineering Competition",
		"organizers": "Колегія та профком студентів та аспірантів",
		"responsible": "президент локального осередку BEST Lviv – Святослав Гонський",
		"_resp_n": 1,
	}
	eq_spec = make_spec("equipment", eq_a)
	assert [p["t"] for p in eq_spec["paras"]] == [
		(
			"Просимо Вашого дозволу на використання семи паяльних станцій 24-26 жовтня 2026 року "
			"з метою проведення події BEST Engineering Competition."
		),
		"Організатори: Колегія та профком студентів та аспірантів.",
		"Відповідальний за проведення: президент локального осередку BEST Lviv – Святослав Гонський.",
	]
	assert_clean_check("equipment", eq_a, eq_spec, builder.build_docx([eq_spec]))

	aud_date_in = "31.10.2026"
	aud_time_in = "09:00-19:00"
	aud_single: dict[str, Any] = {
		"num": "214",
		"building": "головного навчального корпусу",
		"when_kind": "Одноразово",
		"date": dates.format_dates(aud_date_in),
		"_dates": [
			[s.isoformat(), e.isoformat()] for s, e in dates.parse_dates(aud_date_in)
		],
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
	aud_multi: dict[str, Any] = {
		**aud_single,
		"num": "401,402, 403, 404, 405",
		"building": "навчального корпусу №1",
		"responsible": "Голова проєктного відділу Колегії та профкому студентів та аспірантів – Гладчук Святослав",
		"_resp_n": 1,
		"keys": ["Петренко Петро", "Іванова Ірина"],
	}
	aud_spec = make_spec("audience", aud_multi)
	assert aud_spec["paras"][0]["t"] == (
		"Просимо Вашого дозволу на використання приміщень 401, 402, 403, 404, 405 аудиторій навчального корпусу №1 "
		"31 жовтня 2026 року з 09:00 год до 19:00 год для проведення дебатного турніру."
	)
	assert aud_spec["paras"][-2:] == [
		{"t": "Петренко Петро", "k": "list"},
		{"t": "Іванова Ірина", "k": "list"},
	]
	aud_data = builder.build_docx([aud_spec])
	assert_clean_check("audience", aud_multi, aud_spec, aud_data)
	aud_doc = Document(BytesIO(aud_data))
	key_ps = [
		p for p in aud_doc.paragraphs if p.text in ("Петренко Петро", "Іванова Ірина")
	]
	assert len(key_ps) == 2
	for p in key_ps:
		assert_indented_list(p, 1.27, keep=True)

	bad_issues = validator.check(
		"audience", {**aud_multi, "num": "актова"}, aud_spec, today=REF_TODAY
	)
	assert any(lv == "warn" and "Номер аудиторії" in msg for lv, msg in bad_issues), (
		bad_issues
	)

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
	assert (
		"з метою для того" not in placing_txt
		and "для того, щоб провести ярмарок." in placing_txt
	), placing_txt


def _sample_guest_names() -> bytes:
	date_in = "26-30.10.2026"
	a: dict[str, Any] = {
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
	assert texts[i + 1] == "", texts[i : i + 4]
	for p, name in zip(doc.paragraphs[i + 2 : i + 4], a["names"], strict=True):
		pf = p.paragraph_format
		assert p.text == name
		assert pf.left_indent is not None and abs(pf.left_indent - Cm(1.27)) < Cm(0.01)
		assert not pf.first_line_indent

	no_names = make_spec("guest", {**a, "names": []})
	assert no_names["paras"] == [
		{
			"t": "Просимо Вас забезпечити поселення двох осіб на період 26-30 жовтня 2026 року "
			"в межах проєкту «Плацкарт» на безкоштовній основі.",
			"k": "body",
		}
	]
	return data


def test_guest_names_in_memory() -> None:
	_sample_guest_names()


def test_sport_inventory_in_memory() -> None:
	inv_what = "спортивного інвентарю навчального корпусу №22"
	assert inv_what in templates.SPORT

	tpl_sport = templates.TEMPLATES["sport"]
	assert "inv" not in [
		s.key for s in templates.visible_steps(tpl_sport, {"what": inv_what})
	]
	assert "inv" in [
		s.key for s in templates.visible_steps(tpl_sport, {"what": templates.SPORT[0]})
	]

	date_in = "25.10.2026"
	a: dict[str, Any] = {
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

	hall_a: dict[str, Any] = {
		**a,
		"what": templates.SPORT[0],
		"inv": "Так (клопотання піде завідувачу кафедри фізвиховання)",
	}
	hall_spec = make_spec("sport", hall_a)
	assert hall_spec["addressee"] == config.ADDRESSEES["fizvykhovannia"][1]
	assert "та спортивного інвентарю" in hall_spec["paras"][0]["t"]
	assert "заходу та використання інвентарю:" in hall_spec["paras"][1]["t"]

	assert "приміщення футбольного залу навчального корпусу №34" in templates.SPORT
	assert "приміщення баскетбольного залу навчального корпусу №34" in templates.SPORT
	assert "addressee" in [
		s.key for s in templates.visible_steps(tpl_sport, {"what": templates.SPORT[0]})
	]
	fields_a: dict[str, Any] = {**a, "what": "2-ох футбольних полів за адресою Лукаша, 4"}
	assert (
		make_spec("sport", fields_a)["addressee"] == config.ADDRESSEES["studmistechko"][1]
	)
	explicit_helzh = make_spec("sport", {**hall_a, "addressee": "helzhynskyi"})
	assert explicit_helzh["addressee"] == config.ADDRESSEES["helzhynskyi"][1]


def test_config_and_award_in_memory() -> None:
	for fname in (
		"officials.json",
		"responsibles.json",
		"institutes.json",
		"places.json",
	):
		assert (config.DATA_DIR / fname).is_file(), fname
	all_resp_people = [
		p for roles in config.RESPONSIBLES.values() for r in roles for p in r["people"]
	]
	assert len(all_resp_people) == len(set(all_resp_people)), (
		"Duplicate person in RESPONSIBLES"
	)
	assert set(config.INSTITUTES) == set(config.INSTITUTE_PEOPLE)
	assert "ІБІБ" in config.INSTITUTES and "ІБІС" not in config.INSTITUTES
	assert "ІКТЕ" in config.INSTITUTES and "ІТРЕ" not in config.INSTITUTES
	assert "ІПМТ" in config.INSTITUTE_PEOPLE and "ІПІТ" not in config.INSTITUTE_PEOPLE
	assert config.INSTITUTES["ІКТЕ"][1] == "Леоніду ОЗІРКОВСЬКОМУ"
	assert "ІПІТ" in config.LEGACY_INSTITUTES
	imfn_names = {p[0] for p in config.INSTITUTE_PEOPLE["ІМФН"]}
	for name in (
		"Сушельницька Софія",
		"Сушельницька Ірина",
		"Лесяк Роман",
		"Гвоздовська Софія",
		"Похна Софія",
	):
		assert name in imfn_names, name
	assert any(p[0] == "Суканець Олег" for p in config.INSTITUTE_PEOPLE["ІБІБ"])
	from app.core.responsibles import institute_parts

	ibib_parts = institute_parts("ІБІБ", config.INSTITUTE_PEOPLE["ІБІБ"])
	assert any(
		p[0]
		== "Голова спортивного відділу Колегії та профбюро студентів ІБІБ – Суканець Олег"
		for p in ibib_parts
	), ibib_parts
	ihht_names = {p[0] for p in config.INSTITUTE_PEOPLE["ІХХТ"]}
	for name in (
		"Літвінчук Анастасія",
		"Сухобрус Таїсія",
		"Дудка Ярослав",
		"Тарнавчик Олена",
		"Зеленько Марія",
	):
		assert name in ihht_names, name
	from app.core.responsibles import role_parts

	deputy_role = config.RESPONSIBLES["🤝 Заступники / заступниці"][0]
	assert role_parts(deputy_role, ["Пенгрин Романа", "Андибур Анастасія"])[0][
		0
	].startswith("Заступниці Голів ")
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
	a_inline = {
		"form": "бюджетної",
		"reason": "активну громадську діяльність",
		"students": rows_16,
	}
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
	assert (
		len(doc_inline.tables) == 1
		and len(doc_inline.tables[0].rows) == 16
		and len(doc_inline.tables[0].columns) == 3
	)

	rows_41 = [[f"Студент {k}", "ІБІБ", f"БД-{100 + k}"] for k in range(1, 42)]
	a_app = {
		"form": "комерційної",
		"reason": "організацію на «Тижні першокурсника»",
		"students": rows_41,
	}
	spec_app = make_spec("award", a_app)
	assert spec_app["appendix"] == {
		"kind": "award",
		"title": "Додаток 1",
		"items": rows_41,
	}
	assert "(Додаток 1):" in spec_app["paras"][0]["t"]
	spec_app2 = builder.with_appendix_num(spec_app, 2)
	assert (
		"(Додаток 2):" in spec_app2["paras"][0]["t"]
		and spec_app2["appendix"]["title"] == "Додаток 2"
	)
	data_app = builder.build_docx([spec_app])
	assert_clean_check("award", a_app, spec_app, data_app)
	doc_app = Document(BytesIO(data_app))
	assert (
		len(doc_app.tables) == 1
		and len(doc_app.tables[0].rows) == 41
		and len(doc_app.tables[0].columns) == 4
	)
	assert (
		doc_app.tables[0].rows[0].cells[0].text == "1."
		and doc_app.tables[0].rows[40].cells[0].text == "41."
	)

	bad_issues = validator.check(
		"award",
		{
			**a_inline,
			"students": [["Іванов Іван", "ІХЗ", "ЕЕ-11"], ["Іванов Іван", "", ""]],
		},
		spec_inline,
		today=REF_TODAY,
	)
	assert any(lv == "warn" and "невідомий інститут" in msg for lv, msg in bad_issues), (
		bad_issues
	)
	assert any(lv == "warn" and "дублікати" in msg for lv, msg in bad_issues), bad_issues


def test_audience_weekdays_and_purchase_fund_in_memory() -> None:
	aud_weekdays: dict[str, Any] = {
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
	assert (
		"у будні дні протягом осіннього семестру 2026/2027 навчального року з 08:00 год до 21:00 год"
		in aud_spec["paras"][0]["t"]
	)
	assert_clean_check("audience", aud_weekdays, aud_spec, builder.build_docx([aud_spec]))

	pur_a: dict[str, Any] = {
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
	assert (
		"Просимо Вашого сприяння у закупівлі техніки, зазначеної у Додатку 1,"
		in pur_spec["paras"][0]["t"]
	)
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


def test_female_director_titles_in_memory() -> None:
	female_insts = {"ІАРД", "ІГСН", "ІПМТ"}
	for code in config.INSTITUTES:
		expected = "Директорці" if code in female_insts else "Директору"
		assert config.INSTITUTE_TITLES[code] == expected, code
		a = absence_answers(code, STUDS_IARD_4, in_appendix="У тексті (на одному аркуші)")
		spec = make_spec("absence", a)
		assert spec["addressee"][0] == expected, (code, spec["addressee"])
		if code in female_insts or code == "ІБІБ":
			data = builder.build_docx([spec])
			assert_clean_check("absence", a, spec, data)
			doc = Document(BytesIO(data))
			assert any(p.text == expected for p in doc.paragraphs), code


def test_interactive_board_addressee_and_signer_in_memory() -> None:
	date_in = "26.11.2026"
	time_in = "15:00-18:00"
	base: dict[str, Any] = {
		"items": "інтерактивної дошки",
		"date": dates.format_dates(date_in),
		"_dates": [[s.isoformat(), e.isoformat()] for s, e in dates.parse_dates(date_in)],
		"time": dates.format_time(time_in),
		"_time": list(dates.parse_time(time_in)),
		"purpose": "проведення воркшопу",
		"responsible": "Голова проєктного відділу Колегії та профкому студентів та аспірантів – Гладчук Святослав",
		"_resp_n": 1,
	}
	for place in (
		None,
		"в актовій залі навчального корпусу №1",
		"в приміщенні студентського простору «L.I.S.» навчального корпусу №1",
	):
		a = {**base, **({"place": place} if place else {})}
		spec = make_spec("equipment", a)
		assert spec["addressee"] == config.ADDRESSEES["lohoida"][1], place
		assert spec["signers"] == ["profkom", "kolehiia", "tutor"], place
		data = builder.build_docx([spec])
		assert_clean_check("equipment", a, spec, data)
		doc = Document(BytesIO(data))
		texts = [p.text for p in doc.paragraphs]
		assert "Миколі ЛОГОЙДІ" in texts
		assert any("Наталія ЕРДТ" in t for t in texts)

	lis_sound = {
		**base,
		"items": "звукового супроводу",
		"place": "в приміщенні студентського простору «L.I.S.» навчального корпусу №1",
	}
	lis_spec = make_spec("equipment", lis_sound)
	assert lis_spec["addressee"] == config.ADDRESSEES["erdt"][1]
	assert lis_spec["signers"] == ["profkom", "kolehiia"]
