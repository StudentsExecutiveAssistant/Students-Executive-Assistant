"""Побудова inline-клавіатур та представлень для кроків діалогу."""

from __future__ import annotations

import html
from typing import Any

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app import config
from app.core.responsibles import (
	INST_ROLES,
	cat_added_count,
	categories,
	has_person_in_text,
	inst_added_status,
	join_parts,
	last_for,
	role_added_count,
)
from app.core.templates import (
	CATEGORIES,
	TEMPLATES,
	Step,
	addressee_label,
	has_time_step,
)


def cats_kb() -> InlineKeyboardBuilder:
	b = InlineKeyboardBuilder()
	for k, v in CATEGORIES.items():
		b.button(text=v, callback_data=f"cat:{k}")
	b.adjust(2)
	return b


def main_menu() -> InlineKeyboardMarkup:
	return cats_kb().as_markup()


def post_make_menu(tpl_id: str) -> InlineKeyboardMarkup:
	b = InlineKeyboardBuilder()
	b.button(text="🔁 Таке саме клопотання", callback_data=f"tpl:{tpl_id}")
	b.adjust(1)
	b.attach(cats_kb())
	return b.as_markup()


def category_kb(cat: str) -> InlineKeyboardMarkup:
	b = InlineKeyboardBuilder()
	for t in TEMPLATES.values():
		if t.category == cat:
			b.button(text=t.title, callback_data=f"tpl:{t.id}")
	b.button(text="⬅️ До категорій", callback_data="menu")
	b.adjust(1)
	return b.as_markup()


def tail_kb(optional: bool, edit: bool) -> InlineKeyboardBuilder:
	t = InlineKeyboardBuilder()
	if optional:
		t.button(text="⏭ Пропустити", callback_data="skip")
	t.button(text="⬅️ До перегляду" if edit else "⬅️ Назад", callback_data="back")
	t.button(text="✖️ Скасувати", callback_data="cancel")
	t.adjust(2, 1)
	return t


def kb_for(step: Step, edit: bool) -> InlineKeyboardMarkup:
	b = InlineKeyboardBuilder()
	if step.kind == "choice":
		for n, c in enumerate(step.choices):
			b.button(text=c[:60], callback_data=f"c:{n}")
		if step.custom:
			b.button(text="✍️ Інше", callback_data="custom")
		b.adjust(1)
	elif step.kind == "addressee":
		for n, k in enumerate(step.choices):
			b.button(text=addressee_label(k), callback_data=f"c:{n}")
		b.adjust(1)
	elif step.kind == "institute":
		for code in config.INSTITUTES:
			b.button(text=code, callback_data=f"i:{code}")
		b.adjust(4)
	b.attach(tail_kb(step.optional, edit))
	return b.as_markup()


def date_step_view(
	step: Step, i: int, total: int, tpl_id: str, dmode: str | None, edit: bool
) -> tuple[str, InlineKeyboardMarkup]:
	head = f"<b>{i + 1}/{total}. {step.prompt}</b>"
	b = InlineKeyboardBuilder()
	if dmode is None:
		text = head
		if step.hint:
			text += f"\n{step.hint}"
		text += "\n<i>Оберіть формат кнопкою або одразу надішліть дату текстом.</i>"
		b.button(text="📅 Один день", callback_data="dmode:one")
		b.button(text="📆 Період (з … до …)", callback_data="dmode:period")
		b.button(text="🗓 Кілька дат окремо", callback_data="dmode:multi")
		b.adjust(1)
		b.attach(tail_kb(step.optional, edit))
		return text, b.as_markup()
	if dmode == "one":
		text = (
			f"{head}\n<b>Один день</b>\n"
			"Приклади:\n"
			"• <code>26.11.2026</code>\n"
			"• <code>26 листопада 2026</code>\n"
			"Свій текст – з «!» на початку."
		)
	elif dmode == "period":
		text = (
			f"{head}\n<b>Період</b>\n"
			"Приклади:\n"
			"• <code>26-28.11.2026</code>\n"
			"• <code>з 26.11 по 02.12.2026</code>\n"
			"• <code>з 26 листопада до 2 грудня 2026</code>\n"
			"Свій текст – з «!» на початку."
		)
	else:
		text = (
			f"{head}\n<b>Кілька дат окремо</b>\n"
			"Приклади:\n"
			"• <code>26.11, 28.11.2026</code>\n"
			"• з нового рядка:\n"
			"<code>26.11.2026\n28.11.2026</code>"
		)
		if has_time_step(tpl_id):
			text += (
				"\n\nЯкщо в різні дні різний час – вкажіть одразу (окремий крок про час пропуститься):\n"
				"<code>26.11.2026 16:00-20:30\n28.11.2026 14:00-18:00</code>"
			)
		text += "\nСвій текст – з «!» на початку."
	b.button(text="⬅️ До вибору формату", callback_data="dmode:back")
	b.button(text="✖️ Скасувати", callback_data="cancel")
	b.adjust(1)
	return text, b.as_markup()


def _add_people_buttons(
	b: InlineKeyboardBuilder,
	entries: list[tuple[str, str]],
	joined: str,
	selected: list[int],
	cb_prefix: str,
) -> str:
	has_added = False
	for idx, (name, label) in enumerate(entries):
		if has_person_in_text(joined, name):
			has_added = True
			b.button(text=f"☑️ {label} (додано)", callback_data=f"{cb_prefix}:{idx}")
		elif idx in selected:
			b.button(text=f"✅ {label}", callback_data=f"{cb_prefix}:{idx}")
		else:
			b.button(text=f"⬜ {label}", callback_data=f"{cb_prefix}:{idx}")
	b.adjust(1)
	return "\n<i>☑️ — вже додано у клопотання</i>" if has_added else ""


def resp_view(
	rs: dict[str, Any], uid: int, i: int, n: int, edit: bool
) -> tuple[str, InlineKeyboardMarkup]:
	st, parts = rs["stage"], rs["parts"]
	joined = join_parts(parts)
	now = f"\n\nЗараз у клопотанні:\n<i>{html.escape(joined)}</i>" if joined else ""
	b = InlineKeyboardBuilder()
	menu = InlineKeyboardBuilder()
	menu.button(text="⬅️ Меню", callback_data="r:menu")
	if st == "menu":
		text = (
			f"<b>{i + 1}/{n}. Відповідальні за проведення</b>\nОберіть, кого додати:{now}"
		)
		for ci, name in enumerate(categories()):
			cnt = cat_added_count(joined, name)
			b.button(text=f"{name} (✅ {cnt})" if cnt else name, callback_data=f"rc:{ci}")
		inst_cnt = sum(
			1 for code in config.INSTITUTES if inst_added_status(joined, code)[1]
		)
		b.button(
			text=f"🏫 Профбюро інституту (✅ {inst_cnt})"
			if inst_cnt
			else "🏫 Профбюро інституту",
			callback_data="r:inst",
		)
		b.button(text="✍️ Свій текст", callback_data="r:custom")
		if not parts and last_for(uid):
			b.button(text="↩️ Як минулого разу", callback_data="r:last")
		if parts:
			b.button(text="🗑 Прибрати останнє", callback_data="r:undo")
			b.button(text="✅ Готово", callback_data="r:done")
		b.adjust(1)
		b.attach(tail_kb(not parts, edit))
	elif st == "roles":
		cat = categories()[rs["cat"]]
		roles = [(ri, r) for ri, r in enumerate(config.RESPONSIBLES[cat]) if r["people"]]
		text = f"<b>{cat}</b>\n" + (
			"Оберіть посаду:" if roles else "Порожньо – допишіть у data/responsibles.json."
		)
		for ri, r in roles:
			total = len(r["people"])
			added = role_added_count(joined, r)
			label = (
				f"{'✅' if added == total else '☑️'} {r['one'][:40]} ({added}/{total})"
				if added
				else f"{r['one'][:48]} ({total})"
			)
			b.button(text=label, callback_data=f"rr:{ri}")
		b.adjust(1)
		b.attach(menu)
	elif st == "rpeople":
		role = config.RESPONSIBLES[categories()[rs["cat"]]][rs["role"]]
		text = f"<b>{html.escape(role['one'])}</b>\nОберіть людей (можна кількох), потім «Додати»:"
		entries = [(p, p) for p in role["people"]]
		text += _add_people_buttons(b, entries, joined, rs["sel"], "rp")
		e = InlineKeyboardBuilder()
		e.button(text=f"➕ Додати ({len(rs['sel'])})", callback_data="rpok")
		e.button(text="⬅️ Назад", callback_data="r:cat")
		e.adjust(2)
		b.attach(e)
	elif st == "inst":
		text = "<b>Профбюро якого інституту?</b>"
		for code in config.INSTITUTES:
			b.button(
				text=f"✅ {code}" if inst_added_status(joined, code)[1] else code,
				callback_data=f"ri:{code}",
			)
		b.adjust(4)
		b.attach(menu)
	elif st == "ipeople":
		code = rs["code"]
		people = config.INSTITUTE_PEOPLE.get(code, [])
		extra = rs.get("iextra", [])
		text = f"<b>Колегія та профбюро студентів {code}</b>\n"
		text += (
			"Оберіть людей зі списку"
			if people
			else "У data/institutes.json ще немає людей цього інституту"
		)
		text += " або впишіть вручну:"
		if extra:
			text += "\n\nВписано вручну: " + html.escape(
				", ".join(f"{p[0]} ({p[1]})" for p in extra)
			)
		entries = [(p[0], f"{p[0]} · {p[1]}") for p in people]
		text += _add_people_buttons(b, entries, joined, rs["isel"], "ip")
		e = InlineKeyboardBuilder()
		e.button(text="✍️ Вписати вручну", callback_data="r:iman")
		e.button(text=f"➕ Додати ({len(rs['isel']) + len(extra)})", callback_data="ipok")
		e.button(text="⬅️ Меню", callback_data="r:menu")
		e.adjust(1, 2)
		b.attach(e)
	elif st == "irole":
		text = f"<b>Хто саме ({rs['code']})?</b>"
		for r in INST_ROLES:
			b.button(text=r if r != "Член" else "Члени", callback_data=f"ro:{r}")
		b.adjust(2)
		e = InlineKeyboardBuilder()
		e.button(text="⬅️ Назад", callback_data="r:ipeople")
		b.attach(e)
	elif st == "inames":
		text = (
			f"<b>{'Члени' if rs['irole'] == 'Член' else rs['irole']} {config.INSTITUTE_UNIT} {rs['code']}:</b>\n"
			"Впишіть прізвище та імʼя через кому.\n<i>Напр.: Іванов Іван, Петренко Петро</i>"
		)
		e = InlineKeyboardBuilder()
		e.button(text="⬅️ Назад", callback_data="r:ipeople")
		b.attach(e)
	elif st == "custom":
		text = "Напишіть текст відповідальних (як він має стояти в клопотанні):"
		b.attach(menu)
	else:
		text = f"Додано ✅{now}"
		b.button(text="➕ Ще когось", callback_data="r:menu")
		b.button(text="✅ Готово", callback_data="r:done")
		b.adjust(1)
	return text, b.as_markup()
