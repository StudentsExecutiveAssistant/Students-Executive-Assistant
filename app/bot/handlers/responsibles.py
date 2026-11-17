"""Обробники інтерактивного конструктора «Відповідальні за проведення»."""
from __future__ import annotations

from contextlib import suppress
import html

from aiogram import F
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app import config
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


async def rs_set(state: FSMContext, **kw) -> dict:
    d = await state.get_data()
    rs = {**d["rs"], **kw}
    await state.update_data(rs=rs)
    return rs


def _cur_role(rs: dict) -> dict:
    return config.RESPONSIBLES[categories()[rs["cat"]]][rs["role"]]


async def in_resp(state: FSMContext) -> bool:
    from app.bot.handlers.form import steps_of

    d = await state.get_data()
    if not d.get("tpl") or not d.get("rs"):
        return False
    steps = steps_of(d)
    return d["i"] < len(steps) and steps[d["i"]].kind == "responsible"


async def ask_resp(msg: Message, state: FSMContext, uid: int, edit: bool = False) -> None:
    from app.bot.handlers.form import send_step, steps_of

    d = await state.get_data()
    n = len(steps_of(d))
    text, kb = resp_view(d["rs"], uid, d["i"], n, bool(d.get("edit")))
    if edit:
        with suppress(TelegramBadRequest):
            await msg.edit_text(text, reply_markup=kb)
        return
    await send_step(msg, state, text, kb)


async def handle_resp_text(m: Message, state: FSMContext, d: dict, raw: str, note_fn) -> None:
    uid = m.from_user.id
    a = d["a"]
    rs = d["rs"]
    if rs["stage"] == "inames":
        try:
            names, warns = parse_names(raw)
        except ValueError as e:
            return await m.answer(f"⚠️ {e}\nСпробуйте ще раз.")
        if warns:
            await m.answer("⚠️ " + "\n⚠️ ".join(html.escape(w) for w in warns))
        role = rs["irole"]
        gender = "ж" if role == "Заступниця" else None
        role = "Заступник" if role == "Заступниця" else role
        extra = [*rs.get("iextra", []), *[[n, role, *([gender] if gender else [])] for n in names]]
        await rs_set(state, iextra=extra, stage="ipeople")
        return await ask_resp(m, state, uid)
    if rs["stage"] == "custom":
        part, fx = sanitize(raw)
        note_fn(fx, a)
        await state.update_data(a=a)
        n_ = 1 if (" та " not in part and "," not in part) else 2
        await rs_set(state, parts=[*rs["parts"], [part, n_]], stage="more")
        return await ask_resp(m, state, uid)
    await m.answer("Оберіть варіант кнопкою ☝️")


@router.callback_query(Form.filling, F.data.regexp(r"^(r:|rc:|rr:|rp:|ri:|ip:|ro:)|^(rpok|ipok)$"))
async def on_resp(c: CallbackQuery, state: FSMContext):
    from app.bot.handlers.form import store_and_next

    if not await in_resp(state):
        return await c.answer()
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
            return await c.answer()
        if is_inst:
            people = config.INSTITUTE_PEOPLE.get(rs.get("code", ""), [])
        elif "cat" in rs and "role" in rs:
            people = _cur_role(rs)["people"]
        else:
            return await c.answer()
        if not 0 <= n_ < len(people):
            return await c.answer()
        name = people[n_][0] if is_inst else people[n_]
        if has_person(rs["parts"], name):
            return await c.answer(f"{name} вже додано у клопотання")
        sel_key = "isel" if is_inst else "sel"
        cur = rs[sel_key]
        await rs_set(state, **{sel_key: [x for x in cur if x != n_] if n_ in cur else [*cur, n_]})
        toggled = True
    elif data == "rpok":
        if not rs["sel"]:
            return await c.answer("Оберіть хоча б одну людину", show_alert=True)
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
        chosen = [people[n_] for n_ in sorted(rs["isel"])] + [tuple(p) for p in rs.get("iextra", [])]
        if not chosen:
            return await c.answer("Оберіть або впишіть хоча б одну людину", show_alert=True)
        await rs_set(state, parts=[*rs["parts"], *institute_parts(rs["code"], chosen)], stage="more")
    elif data == "r:custom":
        await rs_set(state, stage="custom")
    elif data == "r:last":
        last = last_for(uid)
        if not last:
            return await c.answer("Немає збереженого вибору", show_alert=True)
        t, n_ = last
        await rs_set(state, parts=[[t, n_]], stage="more")
    elif data == "r:undo":
        await rs_set(state, parts=rs["parts"][:-1], stage="menu")
    elif data == "r:done":
        parts = rs["parts"]
        await c.answer()
        text = join_parts(parts)
        return await store_and_next(
            c.message,
            state,
            uid,
            "responsible",
            text or None,
            {"_resp_n": sum(p[1] for p in parts)} if text else None,
        )
    await c.answer()
    if toggled:
        d = await state.get_data()
        _, kb = resp_view(d["rs"], uid, d["i"], 0, bool(d.get("edit")))
        return await c.message.edit_reply_markup(reply_markup=kb)
    await ask_resp(c.message, state, uid, edit=True)
