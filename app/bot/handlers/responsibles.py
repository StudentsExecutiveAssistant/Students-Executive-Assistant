"""Обробники інтерактивного конструктора «Відповідальні за проведення»."""

from __future__ import annotations

import html
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Any

from aiogram import F
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app import config
from app.bot.handlers.shared import send_step, steps_of
from app.bot.keyboards import resp_view
from app.bot.states import Form, router
from app.core.cleaners import parse_names, sanitize
from app.core.responsibles import (
	categories,
	has_person,
	institute_parts,
	join_parts,
	last_for,
	role_parts,
)

DoneHandler = Callable[
	[Message, FSMContext, int, str, Any, dict[str, Any] | None], Awaitable[None]
]
_done_handler: DoneHandler | None = None


def set_done_handler(fn: DoneHandler) -> None:
	global _done_handler
	_done_handler = fn


async def rs_set(state: FSMContext, **kw: Any) -> dict[str, Any]:
	d = await state.get_data()
	rs = {**d["rs"], **kw}
	await state.update_data(rs=rs)
	return rs


def _cur_role(rs: dict[str, Any]) -> dict[str, Any]:
	return config.RESPONSIBLES[categories()[rs["cat"]]][rs["role"]]


async def in_resp(state: FSMContext) -> bool:
	d = await state.get_data()
	if not d.get("tpl") or not d.get("rs"):
		return False
	steps = steps_of(d)
	return d["i"] < len(steps) and steps[d["i"]].kind == "responsible"


async def ask_resp(
	msg: Message, state: FSMContext, uid: int, edit: bool = False
) -> None:
	d = await state.get_data()
	n = len(steps_of(d))
	text, kb = resp_view(d["rs"], uid, d["i"], n, bool(d.get("edit")))
	if edit:
		with suppress(TelegramBadRequest):
			await msg.edit_text(text, reply_markup=kb)
		return
	await send_step(msg, state, text, kb)


async def handle_resp_text(
	m: Message,
	state: FSMContext,
	d: dict[str, Any],
	raw: str,
	note_fn: Callable[[list[str], dict[str, Any]], None],
) -> None:
	if m.from_user is None:
		return
	uid = m.from_user.id
	a = d["a"]
	rs = d["rs"]
	if rs["stage"] == "inames":
		try:
			names, warns = parse_names(raw)
		except ValueError as e:
			await m.answer(f"⚠️ {e}\nСпробуйте ще раз.")
			return
		if warns:
			await m.answer("⚠️ " + "\n⚠️ ".join(html.escape(w) for w in warns))
		role = rs["irole"]
		gender = "ж" if role == "Заступниця" else None
		role = "Заступник" if role == "Заступниця" else role
		extra = [
			*rs.get("iextra", []),
			*[[n, role, *([gender] if gender else [])] for n in names],
		]
		await rs_set(state, iextra=extra, stage="ipeople")
		await ask_resp(m, state, uid)
		return
	if rs["stage"] == "custom":
		part, fx = sanitize(raw)
		note_fn(fx, a)
		await state.update_data(a=a)
		n_ = 1 if (" та " not in part and "," not in part) else 2
		await rs_set(state, parts=[*rs["parts"], [part, n_]], stage="more")
		await ask_resp(m, state, uid)
		return
	await m.answer("Оберіть варіант кнопкою ☝️")


@router.callback_query(
	Form.filling, F.data.regexp(r"^(r:|rc:|rr:|rp:|ri:|ip:|ro:)|^(rpok|ipok)$")
)
async def on_resp(c: CallbackQuery, state: FSMContext) -> None:
	if not await in_resp(state) or c.data is None:
		await c.answer()
		return
	data, uid = c.data, c.from_user.id
	d = await state.get_data()
	rs = d["rs"]
	toggled = False
	if data == "r:menu":
		await rs_set(state, stage="menu")
	elif data.startswith("rc:"):
		await rs_set(state, stage="roles", cat=int(data[3:]))
	elif data == "r:cat":
		await rs_set(state, stage="roles")
	elif data.startswith("rr:"):
		await rs_set(state, stage="rpeople", role=int(data[3:]), sel=[])
	elif data.startswith(("rp:", "ip:")):
		is_inst = data.startswith("ip:")
		try:
			n_ = int(data[3:])
		except ValueError:
			await c.answer()
			return
		if is_inst:
			inst_people = config.INSTITUTE_PEOPLE.get(rs.get("code", ""), [])
			if not 0 <= n_ < len(inst_people):
				await c.answer()
				return
			name = inst_people[n_][0]
		elif "cat" in rs and "role" in rs:
			role_people = _cur_role(rs)["people"]
			if not 0 <= n_ < len(role_people):
				await c.answer()
				return
			name = str(role_people[n_])
		else:
			await c.answer()
			return
		if has_person(rs["parts"], name):
			await c.answer(f"{name} вже додано у клопотання")
			return
		sel_key = "isel" if is_inst else "sel"
		cur = rs[sel_key]
		await rs_set(
			state, **{sel_key: [x for x in cur if x != n_] if n_ in cur else [*cur, n_]}
		)
		toggled = True
	elif data == "rpok":
		if not rs["sel"]:
			await c.answer("Оберіть хоча б одну людину", show_alert=True)
			return
		role = _cur_role(rs)
		names = [role["people"][n_] for n_ in sorted(rs["sel"])]
		await rs_set(state, parts=[*rs["parts"], *role_parts(role, names)], stage="more")
	elif data == "r:inst":
		await rs_set(state, stage="inst")
	elif data.startswith("ri:"):
		await rs_set(state, stage="ipeople", code=data[3:], isel=[], iextra=[])
	elif data == "r:ipeople":
		await rs_set(state, stage="ipeople")
	elif data == "r:iman":
		await rs_set(state, stage="irole")
	elif data.startswith("ro:"):
		await rs_set(state, stage="inames", irole=data[3:])
	elif data == "ipok":
		people = config.INSTITUTE_PEOPLE.get(rs["code"], [])
		chosen = [people[n_] for n_ in sorted(rs["isel"])] + [
			tuple(p) for p in rs.get("iextra", [])
		]
		if not chosen:
			await c.answer("Оберіть або впишіть хоча б одну людину", show_alert=True)
			return
		await rs_set(
			state,
			parts=[*rs["parts"], *institute_parts(rs["code"], chosen)],
			stage="more",
		)
	elif data == "r:custom":
		await rs_set(state, stage="custom")
	elif data == "r:last":
		last = last_for(uid)
		if not last:
			await c.answer("Немає збереженого вибору", show_alert=True)
			return
		t, n_ = last
		await rs_set(state, parts=[[t, n_]], stage="more")
	elif data == "r:undo":
		await rs_set(state, parts=rs["parts"][:-1], stage="menu")
	elif data == "r:done":
		parts = rs["parts"]
		await c.answer()
		text = join_parts(parts)
		if isinstance(c.message, Message) and _done_handler is not None:
			await _done_handler(
				c.message,
				state,
				uid,
				"responsible",
				text or None,
				{"_resp_n": sum(p[1] for p in parts)} if text else None,
			)
		return
	await c.answer()
	if not isinstance(c.message, Message):
		return
	if toggled:
		d = await state.get_data()
		_, kb = resp_view(d["rs"], uid, d["i"], 0, bool(d.get("edit")))
		await c.message.edit_reply_markup(reply_markup=kb)
		return
	await ask_resp(c.message, state, uid, edit=True)
