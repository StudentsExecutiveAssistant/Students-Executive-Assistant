"""Обробники покрокового заповнення клопотання, попереднього перегляду, генерації та пересилання .docx."""

from __future__ import annotations

import html
import logging
from contextlib import suppress
from datetime import date
from typing import Any

from aiogram import F
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app import config
from app.bot.handlers.petitions import notify_admins
from app.bot.handlers.responsibles import (
	ask_resp,
	handle_resp_text,
	in_resp,
	set_done_handler,
)
from app.bot.handlers.shared import drop_kb, first_missing, send_step, steps_of
from app.bot.keyboards import (
	category_kb,
	date_step_view,
	kb_for,
	main_menu,
	post_make_menu,
)
from app.bot.states import Form, router
from app.core.cleaners import (
	clean_dept,
	clean_dorm,
	clean_order,
	clean_project,
	clean_purpose,
	clean_reason,
	clean_route,
	normalize_award_students,
	normalize_plates,
	normalize_students,
	sanitize,
	sanitize_lines,
)
from app.core.dates import format_schedule, format_time, parse_schedule, parse_time
from app.core.responsibles import save_last
from app.core.templates import (
	APPENDIX_THRESHOLD,
	CATEGORIES,
	TEMPLATES,
	Step,
	build_spec,
	has_time_step,
	parse_purchase_item,
)
from app.docx.builder import build_docx, preview_text, with_appendix_num
from app.docx.validator import check, format_issues

logger = logging.getLogger(__name__)

_FIELD_CLEANERS = {
	"route": clean_route,
	"dept": clean_dept,
	"project": clean_project,
	"order": clean_order,
	"dorm": clean_dorm,
}


async def cur_step(state: FSMContext) -> tuple[Step, dict[str, Any]]:
	d = await state.get_data()
	return steps_of(d)[d["i"]], d


async def ask(msg: Message, state: FSMContext, uid: int, edit: bool = False) -> None:
	d = await state.get_data()
	steps = steps_of(d)
	i = d["i"]
	if i >= len(steps):
		await show_preview(msg, state)
		return
	step = steps[i]
	if step.kind == "responsible":
		old = d["a"].get("responsible")
		parts = [[old, d["a"].get("_resp_n", 2)]] if old else []
		await state.update_data(rs={"stage": "menu", "parts": parts})
		await ask_resp(msg, state, uid)
		return
	if step.kind == "date":
		text, kb = date_step_view(
			step, i, len(steps), d["tpl"], d.get("dmode"), bool(d.get("edit"))
		)
	else:
		text = f"<b>{i + 1}/{len(steps)}. {step.prompt}</b>"
		if step.hint:
			text += f"\n{step.hint}"
		if step.kind == "lines":
			text += "\n<i>Одним повідомленням, кожен пункт з нового рядка.</i>"
		kb = kb_for(step, bool(d.get("edit")))
	if edit:
		with suppress(TelegramBadRequest):
			await msg.edit_text(text, reply_markup=kb)
		return
	await send_step(msg, state, text, kb)


async def store_and_next(
	msg: Message,
	state: FSMContext,
	uid: int,
	key: str,
	value: Any,
	extra: dict[str, Any] | None = None,
) -> None:
	d = await state.get_data()
	a = d["a"]
	prev_value = a.get(key)
	if value is None:
		a.pop(key, None)
	else:
		a[key] = value
	if key == "time" and value is None:
		a.pop("_time", None)
	if key == "responsible" and value is None:
		a.pop("_resp_n", None)
	if value != prev_value:
		if key == "when_kind":
			if str(value) == "Одноразово":
				for k_ in ("weekday", "sem"):
					a.pop(k_, None)
			else:
				for k_ in ("date", "_dates", "_timed", "_times"):
					a.pop(k_, None)
				if not str(value).startswith("Щотижня"):
					a.pop("weekday", None)
		if key == "addressee" and value != "institute":
			a.pop("inst", None)
		if d["tpl"] == "purchase" and key == "kind":
			a.pop("goal", None)
		if d["tpl"] == "absence" and key == "students" and isinstance(value, list):
			if len(value) == 1:
				a.pop("in_appendix", None)
			else:
				a.pop("who", None)
				if len(value) >= APPENDIX_THRESHOLD:
					a.pop("in_appendix", None)
	a.update(extra or {})
	d["a"] = a
	if d.get("edit"):
		missing = first_missing(d)
		if missing is not None:
			await state.update_data(a=a, i=missing, custom=False, dmode=None)
			await ask(msg, state, uid)
			return
		if (
			key == "date"
			and has_time_step(d["tpl"])
			and not (extra or {}).get("_timed")
			and "time" not in a
		):
			time_i = next((n for n, s in enumerate(steps_of(d)) if s.key == "time"), None)
			if time_i is not None:
				await state.update_data(a=a, i=time_i, custom=False, dmode=None)
				await ask(msg, state, uid)
				return
		await state.update_data(a=a, edit=False, custom=False, dmode=None)
		await show_preview(msg, state)
		return
	await state.update_data(a=a, i=d["i"] + 1, custom=False, dmode=None)
	await ask(msg, state, uid)


set_done_handler(store_and_next)


def _note(fixes: list[str], a: dict[str, Any]) -> None:
	target = a.setdefault("_fixes", [])
	for f in fixes:
		if f not in target:
			target.append(f)


def make_spec(d: dict[str, Any]) -> dict[str, Any]:
	spec = build_spec(d["tpl"], d["a"])
	app_n = sum(bool(s.get("appendix")) for s in d.get("batch", [])) + 1
	return with_appendix_num(spec, app_n)


async def show_preview(msg: Message, state: FSMContext) -> None:
	d = await state.get_data()
	try:
		spec = make_spec(d)
	except Exception:
		logger.exception("build failed")
		await drop_kb(msg.bot, msg.chat.id, d.get("mid"))
		await state.clear()
		await msg.answer("Не вдалося зібрати документ 😔 Почніть заново: /new")
		return
	issues = check(d["tpl"], d["a"], spec)
	await state.update_data(spec=spec)
	await state.set_state(Form.confirm)
	n = len(d.get("batch", []))
	b = InlineKeyboardBuilder()
	has_err = any(lv == "err" for lv, _ in issues)
	b.button(
		text="⚠️ Створити попри помилки" if has_err else "✅ Створити .docx",
		callback_data="make",
	)
	b.button(text="✏️ Змінити відповідь", callback_data="edit")
	b.button(text="➕ Додати ще в цей файл", callback_data="more")
	b.button(text="🔁 Спочатку", callback_data="restart")
	b.adjust(1)
	extra = f"\n\n<i>У файлі вже клопотань: {n}</i>" if n else ""
	await send_step(
		msg,
		state,
		f"<pre>{html.escape(preview_text(spec))}</pre>\n{format_issues(issues)}{extra}",
		b.as_markup(),
	)


@router.callback_query(Form.filling, F.data == "cancel")
async def cancel_cb(c: CallbackQuery, state: FSMContext) -> None:
	d = await state.get_data()
	text = "<b>Скасувати це клопотання?</b>\nУсі введені відповіді буде втрачено."
	n = len(d.get("batch", []))
	if n:
		text += f"\nТакож буде втрачено вже додані у файл клопотання: {n}."
	b = InlineKeyboardBuilder()
	b.button(text="✅ Так, скасувати", callback_data="cancel:yes")
	b.button(text="⬅️ Ні, повернутись", callback_data="cancel:no")
	b.adjust(1)
	await c.answer()
	if isinstance(c.message, Message):
		await c.message.edit_text(text, reply_markup=b.as_markup())


@router.callback_query(Form.filling, F.data == "cancel:yes")
async def cancel_yes(c: CallbackQuery, state: FSMContext) -> None:
	await state.clear()
	await c.answer("Скасовано")
	if isinstance(c.message, Message):
		await c.message.edit_text(
			"Скасовано ✖️\nОберіть тип нового клопотання:", reply_markup=main_menu()
		)


@router.callback_query(Form.filling, F.data == "cancel:no")
async def cancel_no(c: CallbackQuery, state: FSMContext) -> None:
	await state.update_data(custom=False)
	await c.answer()
	if not isinstance(c.message, Message):
		return
	if await in_resp(state):
		await ask_resp(c.message, state, c.from_user.id, edit=True)
		return
	await ask(c.message, state, c.from_user.id, edit=True)


@router.callback_query(Form.filling, F.data.startswith("c:"))
async def on_choice(c: CallbackQuery, state: FSMContext) -> None:
	step, _ = await cur_step(state)
	if step.kind not in ("choice", "addressee") or c.data is None:
		await c.answer()
		return
	try:
		idx = int(c.data.split(":", 1)[1])
	except ValueError:
		await c.answer()
		return
	if not 0 <= idx < len(step.choices):
		await c.answer()
		return
	value = step.choices[idx]
	await c.answer()
	if isinstance(c.message, Message):
		await store_and_next(c.message, state, c.from_user.id, step.key, value)


@router.callback_query(Form.filling, F.data.startswith("i:"))
async def on_institute(c: CallbackQuery, state: FSMContext) -> None:
	step, _ = await cur_step(state)
	if c.data is None:
		await c.answer()
		return
	code = c.data.split(":", 1)[1]
	if step.kind != "institute" or code not in config.INSTITUTES:
		await c.answer()
		return
	await c.answer()
	if isinstance(c.message, Message):
		await store_and_next(c.message, state, c.from_user.id, step.key, code)


@router.callback_query(Form.filling, F.data == "custom")
async def on_custom(c: CallbackQuery, state: FSMContext) -> None:
	await state.update_data(custom=True)
	if isinstance(c.message, Message):
		await c.message.answer("Напишіть свій варіант:")
	await c.answer()


@router.callback_query(Form.filling, F.data == "skip")
async def on_skip(c: CallbackQuery, state: FSMContext) -> None:
	step, _ = await cur_step(state)
	if not step.optional:
		await c.answer()
		return
	await c.answer()
	if isinstance(c.message, Message):
		await store_and_next(c.message, state, c.from_user.id, step.key, None)


@router.callback_query(Form.filling, F.data.startswith("dmode:"))
async def on_dmode(c: CallbackQuery, state: FSMContext) -> None:
	step, _ = await cur_step(state)
	if step.kind != "date" or c.data is None:
		await c.answer()
		return
	mode = c.data.split(":", 1)[1]
	if mode not in ("back", "one", "period", "multi"):
		await c.answer()
		return
	await state.update_data(dmode=None if mode == "back" else mode)
	await c.answer()
	if isinstance(c.message, Message):
		await ask(c.message, state, c.from_user.id, edit=True)


@router.callback_query(Form.filling, F.data == "back")
async def on_back(c: CallbackQuery, state: FSMContext) -> None:
	d = await state.get_data()
	if d.get("edit"):
		if first_missing(d) is not None:
			await c.answer("Спершу заповніть цей пункт – він обовʼязковий", show_alert=True)
			return
		await state.update_data(edit=False, custom=False, dmode=None)
		await c.answer()
		if isinstance(c.message, Message):
			await show_preview(c.message, state)
		return
	if d["i"] == 0:
		tpl = TEMPLATES[d["tpl"]]
		await state.set_state(None)
		await state.update_data(mid=None, custom=False, dmode=None)
		await c.answer()
		if isinstance(c.message, Message):
			await c.message.edit_text(
				CATEGORIES[tpl.category], reply_markup=category_kb(tpl.category)
			)
		return
	await state.update_data(i=d["i"] - 1, custom=False, dmode=None)
	await c.answer()
	if isinstance(c.message, Message):
		await ask(c.message, state, c.from_user.id)


@router.message(Form.filling, F.text)
async def on_text(m: Message, state: FSMContext) -> None:
	if not m.from_user or m.text is None:
		return
	step, d = await cur_step(state)
	uid = m.from_user.id
	raw = m.text.strip()
	a = d["a"]
	if step.kind == "responsible":
		await handle_resp_text(m, state, d, raw, _note)
		return
	try:
		if step.kind in ("choice", "addressee", "institute") and not d.get("custom"):
			await m.answer("Оберіть варіант кнопкою ☝️")
			return
		extra: dict[str, Any] = {}
		value: Any
		if step.kind == "date":
			if raw.startswith("!"):
				value = raw[1:].strip()
				if not value:
					raise ValueError("Порожня дата")
				extra = {"_dates": None, "_timed": None, "_times": None}
			else:
				entries = parse_schedule(
					raw, date.today().year, allow_time=has_time_step(d["tpl"])
				)
				extra["_dates"] = [[s.isoformat(), e.isoformat()] for s, e, _ in entries]
				value = format_schedule(entries)
				if entries[0][2] is not None:
					extra["_timed"] = True
					extra["_times"] = [list(tm) for _, _, tm in entries if tm is not None]
					a.pop("time", None)
					a.pop("_time", None)
				else:
					extra["_timed"] = None
					extra["_times"] = None
		elif step.kind == "time":
			value = format_time(raw)
			extra["_time"] = None if raw.startswith("!") else list(parse_time(raw))
		elif step.kind == "lines":
			lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
			fx: list[str] = []
			if d["tpl"] == "award":
				parsed_lines: list[Any] = normalize_award_students(lines)
			elif d["tpl"] == "purchase" and step.key == "items":
				for ln in lines:
					parse_purchase_item(ln)
				parsed_lines = lines
			elif d["tpl"] == "absence":
				parsed_lines = normalize_students(lines)
			else:
				parsed_lines = lines
			if not parsed_lines:
				raise ValueError("Порожньо")
			value = sanitize_lines(parsed_lines, fx)
			_note(fx, a)
		else:
			value, fx = sanitize(raw)
			if step.key == "purpose":
				value, p_fx = clean_purpose(
					value, mode="meta" if d["tpl"] == "placing" else "dlya"
				)
				fx += p_fx
			elif step.key == "reason":
				value, rs_fx = clean_reason(
					value, mode="za" if d["tpl"] == "award" else "zvyazku"
				)
				fx += rs_fx
			elif cleaner := _FIELD_CLEANERS.get(step.key):
				value, c_fx = cleaner(value)
				fx += c_fx
			_note(fx, a)
			if step.key == "plates":
				value = ", ".join(normalize_plates(value))
		for k_, v_ in list(extra.items()):
			if v_ is None:
				a.pop(k_, None)
				extra.pop(k_)
		await state.update_data(a=a)
	except (ValueError, IndexError) as e:
		await m.answer(f"⚠️ {e}\nСпробуйте ще раз.")
		return
	await store_and_next(m, state, uid, step.key, value, extra)


@router.callback_query(Form.confirm, F.data == "edit")
async def edit_menu(c: CallbackQuery, state: FSMContext) -> None:
	d = await state.get_data()
	b = InlineKeyboardBuilder()
	for i, s in enumerate(steps_of(d)):
		b.button(text=s.prompt.split("(")[0].strip(" ?:")[:40], callback_data=f"e:{i}")
	b.adjust(2)
	back = InlineKeyboardBuilder()
	back.button(text="⬅️ До перегляду", callback_data="preview")
	b.attach(back)
	await c.answer()
	if isinstance(c.message, Message):
		await send_step(c.message, state, "Що змінити?", b.as_markup())


@router.callback_query(Form.confirm, F.data == "preview")
async def back_to_preview(c: CallbackQuery, state: FSMContext) -> None:
	await c.answer()
	if isinstance(c.message, Message):
		await show_preview(c.message, state)


@router.callback_query(Form.confirm, F.data.startswith("e:"))
async def edit_step(c: CallbackQuery, state: FSMContext) -> None:
	if c.data is None:
		await c.answer()
		return
	d = await state.get_data()
	try:
		idx = int(c.data.split(":", 1)[1])
	except ValueError:
		await c.answer()
		return
	if not 0 <= idx < len(steps_of(d)):
		await c.answer()
		return
	await state.set_state(Form.filling)
	await state.update_data(i=idx, edit=True, custom=False, dmode=None)
	await c.answer()
	if isinstance(c.message, Message):
		await ask(c.message, state, c.from_user.id)


@router.callback_query(Form.confirm, F.data == "make")
async def make(c: CallbackQuery, state: FSMContext) -> None:
	d = await state.get_data()
	specs = [*d.get("batch", []), d["spec"]]
	if d["a"].get("responsible"):
		save_last(c.from_user.id, d["a"]["responsible"], d["a"].get("_resp_n", 2))
	data = build_docx(specs)
	name = f"Клопотання_{date.today():%d-%m-%Y}.docx"
	sent_admins = await notify_admins(
		c.bot, c.from_user, data, name, d["tpl"], len(specs)
	)
	caption = f"Готово ✅ ({len(specs)} шт.)" + (
		"\n📨 Копію надіслано адмінам." if sent_admins > 0 else ""
	)
	if isinstance(c.message, Message):
		await c.message.answer_document(BufferedInputFile(data, name), caption=caption)
		await drop_kb(c.bot, c.message.chat.id, c.message.message_id)
	await state.clear()
	if isinstance(c.message, Message):
		await c.message.answer(
			"Хочете створити ще одне клопотання?", reply_markup=post_make_menu(d["tpl"])
		)
	await c.answer()


@router.callback_query(Form.confirm, F.data == "more")
async def more(c: CallbackQuery, state: FSMContext) -> None:
	d = await state.get_data()
	batch = [*d.get("batch", []), d["spec"]]
	if isinstance(c.message, Message):
		await drop_kb(c.bot, c.message.chat.id, c.message.message_id)
	await state.update_data(batch=batch, mid=None)
	await state.set_state(None)
	if isinstance(c.message, Message):
		await c.message.answer(
			f"Додано ({len(batch)}). Оберіть тип наступного:", reply_markup=main_menu()
		)
	await c.answer()


@router.callback_query(Form.confirm, F.data == "restart")
async def restart(c: CallbackQuery, state: FSMContext) -> None:
	await state.set_state(Form.filling)
	await state.update_data(i=0, a={}, custom=False, edit=False, dmode=None)
	await c.answer()
	if isinstance(c.message, Message):
		await ask(c.message, state, c.from_user.id)
