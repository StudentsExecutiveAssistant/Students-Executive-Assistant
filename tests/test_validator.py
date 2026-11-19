"""Тести валідатора тексту, чернеток клопотань з часом та перевірки готових .docx."""

from __future__ import annotations

from app.core import dates, templates
from app.docx import builder, validator
from tests.helpers import (
	REF_TODAY,
	STUDS_IARD_4,
	STUDS_IBIB_4,
	absence_answers,
	assert_clean_check,
	make_spec,
)


def test_timed_templates_and_checker_in_memory() -> None:
	sched = dates.parse_schedule("26.11.2026 16:00-20:30\n28.11.2026 14:00-18:00")
	rooms_timed = {
		"what": "приміщення актової зали навчального корпусу №1",
		"date": dates.format_schedule(sched),
		"_dates": [[s.isoformat(), e.isoformat()] for s, e, _ in sched],
		"_timed": True,
		"_times": [list(tm) for _, _, tm in sched if tm is not None],
		"time": "STALE_IGNORED",
		"purpose": "проведення репетицій та заходу",
		"responsible": "Голова Колегії – Петренко Петро",
		"_resp_n": 1,
	}
	rooms_spec = make_spec("rooms", rooms_timed)
	assert rooms_spec["paras"][0]["t"] == (
		"Просимо Вашого дозволу на використання приміщення актової зали навчального корпусу №1 "
		"26 листопада з 16:00 год до 20:30 год та 28 листопада 2026 року з 14:00 год до 18:00 год "
		"для проведення репетицій та заходу."
	)
	rooms_data = builder.build_docx([rooms_spec])
	assert_clean_check("rooms", rooms_timed, rooms_spec, rooms_data)
	assert "ЕРДТ" not in "\n".join(validator.check_docx(rooms_data, today=REF_TODAY))
	issues = validator.check("rooms", rooms_timed, rooms_spec, today=REF_TODAY)
	assert not any("Не вказано години" in msg for _, msg in issues), issues

	bad_time_issues = validator.check(
		"rooms", {**rooms_timed, "_times": [[1200, 1000]]}, rooms_spec, today=REF_TODAY
	)
	assert any(lv == "err" and "раніше" in msg for lv, msg in bad_time_issues), (
		bad_time_issues
	)

	aud_timed = {
		"num": "214",
		"building": "головного навчального корпусу",
		"when_kind": "Одноразово",
		"date": dates.format_schedule(sched),
		"_dates": [[s.isoformat(), e.isoformat()] for s, e, _ in sched],
		"_timed": True,
		"_times": [list(tm) for _, _, tm in sched if tm is not None],
		"time": "STALE_IGNORED",
		"purpose": "проведення дебатів",
		"responsible": "Голова Колегії – Петренко Петро",
		"_resp_n": 1,
	}
	aud_spec = make_spec("audience", aud_timed)
	assert aud_spec["paras"][0]["t"] == (
		"Просимо Вашого дозволу на використання приміщення 214 аудиторії головного навчального корпусу "
		"26 листопада з 16:00 год до 20:30 год та 28 листопада 2026 року з 14:00 год до 18:00 год "
		"для проведення дебатів."
	)
	assert_clean_check("audience", aud_timed, aud_spec, builder.build_docx([aud_spec]))
	tpl_aud = templates.TEMPLATES["audience"]
	assert "time" not in [s.key for s in templates.visible_steps(tpl_aud, aud_timed)]
	assert "time" in [
		s.key
		for s in templates.visible_steps(
			tpl_aud, {"when_kind": "Щотижня протягом семестру", "_timed": True}
		)
	]

	abs_4 = absence_answers(
		"ІБІБ", STUDS_IBIB_4, in_appendix="У тексті (на одному аркуші)"
	)
	abs_4_spec = make_spec("absence", abs_4)
	abs_4_data = builder.build_docx([abs_4_spec])
	assert_clean_check("absence", abs_4, abs_4_spec, abs_4_data)


def test_text_issues_diagnostics() -> None:
	iss1 = validator.text_issues("Просимо дозволу з метою для проведення.")
	assert any(
		lv == "warn" and "Зайве «для» поруч із «з метою»" in m for lv, m in iss1
	), iss1
	iss2 = validator.text_issues("Просимо дозволу для.")
	assert any(lv == "warn" and "Зайве або обірване «для»" in m for lv, m in iss2), iss2
	iss_ok = validator.text_issues("Просимо дозволу для того, щоб провести захід.")
	assert not any("Зайве" in m for _, m in iss_ok), iss_ok

	iss_zz = validator.text_issues(
		"Просимо вважати відсутність у зв’язку з з організацією."
	)
	assert any(lv == "warn" and "Повтор слова «з»" in m for lv, m in iss_zz), iss_zz
	assert any(
		lv == "warn" and "Зайве «з» після «у зв’язку з»" in m for lv, m in iss_zz
	), iss_zz
	iss_ziz = validator.text_issues(
		"Просимо вважати відсутність у зв’язку з із організацією."
	)
	assert any(
		lv == "warn" and "Зайве «з» після «у зв’язку з»" in m for lv, m in iss_ziz
	), iss_ziz
	iss_cut = validator.text_issues("Просимо вважати відсутність у зв’язку з.")
	assert any(lv == "warn" and "Обірване «у зв’язку з»" in m for lv, m in iss_cut), (
		iss_cut
	)
	iss_init = validator.text_issues("Зустріч з З. І. Мельником.")
	assert not any("Повтор" in m for _, m in iss_init), iss_init

	monthly_a = {
		"dorm": "5",
		"who": "студенту",
		"course": "третього",
		"level": "бакалаврату",
		"inst": "ІКНІ",
		"fio": "Петренка Петра Петровича",
	}
	monthly_spec = make_spec("monthly", monthly_a)
	monthly_data = builder.build_docx([monthly_spec])
	monthly_rep = "\n".join(validator.check_docx(monthly_data, today=REF_TODAY))
	assert "ПЕТРИШИН" not in monthly_rep and "ЕРДТ" not in monthly_rep, monthly_rep
	assert "❌" not in monthly_rep and "⚠️" not in monthly_rep, monthly_rep

	eq_lis_a = {
		"items": "звукового супроводу",
		"place": "у приміщенні L.I.S. – центр тьюторства",
		"date": "26 листопада 2026 року",
		"_dates": [["2026-11-26", "2026-11-26"]],
		"time": "з 15:00 год до 18:00 год",
		"_time": [900, 1080],
		"purpose": "проведення заходу",
		"responsible": "Голова Колегії – Петренко Петро",
		"_resp_n": 1,
	}
	eq_lis_spec = make_spec("equipment", eq_lis_a)
	eq_lis_data = builder.build_docx([eq_lis_spec])
	eq_lis_rep = "\n".join(validator.check_docx(eq_lis_data, today=REF_TODAY))
	assert "Немає шапки" not in eq_lis_rep and "ЕРДТ" not in eq_lis_rep, eq_lis_rep
	assert "❌" not in eq_lis_rep and "⚠️" not in eq_lis_rep, eq_lis_rep

	# Інтерактивна дошка без підпису ЕРДТ має попереджати про відсутній підпис.
	board_spec = make_spec(
		"equipment",
		{
			"items": "інтерактивної дошки",
			"place": "в актовій залі навчального корпусу №1",
			"date": "26 листопада 2026 року",
			"_dates": [["2026-11-26", "2026-11-26"]],
			"time": "з 15:00 год до 18:00 год",
			"_time": [900, 1080],
			"purpose": "проведення воркшопу",
			"responsible": "Голова Колегії – Петренко Петро",
			"_resp_n": 1,
		},
	)
	board_no_tutor = {**board_spec, "signers": ["profkom", "kolehiia"]}
	board_rep = "\n".join(
		validator.check_docx(builder.build_docx([board_no_tutor]), today=REF_TODAY)
	)
	assert "Не бачу підпису з прізвищем ЕРДТ" in board_rep, board_rep

	# Інтерактивні стійки не повинні вимагати підпис ЕРДТ.
	stands_spec = make_spec(
		"placing",
		{
			"where": "в холі головного навчального корпусу",
			"what": "інтерактивних стійок",
			"date": "26 листопада 2026 року",
			"_dates": [["2026-11-26", "2026-11-26"]],
			"time": "з 10:00 год до 18:00 год",
			"_time": [600, 1080],
			"purpose": "проведення промоакції",
			"responsible": "Голова Колегії – Петренко Петро",
			"_resp_n": 1,
		},
	)
	stands_rep = "\n".join(
		validator.check_docx(builder.build_docx([stands_spec]), today=REF_TODAY)
	)
	assert "ЕРДТ" not in stands_rep, stands_rep

	# Шапка з «Директорці» розпізнається коректно.
	iard_spec = make_spec(
		"absence",
		absence_answers("ІАРД", STUDS_IARD_4, in_appendix="У тексті (на одному аркуші)"),
	)
	iard_rep = "\n".join(
		validator.check_docx(builder.build_docx([iard_spec]), today=REF_TODAY)
	)
	assert "Немає шапки" not in iard_rep and "❌" not in iard_rep, iard_rep

	bad_range_spec = make_spec(
		"rooms",
		{
			"what": "приміщення актової зали",
			"date": "26-32 листопада 2026 року",
			"time": "з 15:00 год до 18:00 год",
			"purpose": "проведення репетиції",
			"responsible": "Голова Колегії – Петренко Петро",
			"_resp_n": 1,
		},
	)
	bad_range_rep = "\n".join(
		validator.check_docx(builder.build_docx([bad_range_spec]), today=REF_TODAY)
	)
	assert "❌ Неіснуюча дата" in bad_range_rep, bad_range_rep
