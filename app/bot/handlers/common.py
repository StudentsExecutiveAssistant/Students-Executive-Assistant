"""Команди меню, керування адмінами, вибір категорії/шаблону та перевірка завантажених .docx."""
from __future__ import annotations

from contextlib import suppress
import html
from io import BytesIO
import logging

from aiogram import Bot, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app import config
from app.bot.handlers.form import ask, drop_kb
from app.bot.keyboards import category_kb, main_menu
from app.bot.states import Form, router
from app.core.templates import CATEGORIES, TEMPLATES, addressee_label
from app.core.cleaners import parse_user_ids
from app.docx.validator import check_docx

_ADDR_NOTE = {
    "equipment": " (для приміщення L.I.S. – центр тьюторства)",
}


def _addr_hint(tpl) -> str:
    if len(tpl.addressees) > 1:
        return "обираєте нижче"
    base = "директор обраного інституту" if tpl.addressees[0] == "institute" else addressee_label(tpl.addressees[0])
    return base + _ADDR_NOTE.get(tpl.id, "")


def _admins_view() -> tuple[str, InlineKeyboardMarkup]:
    all_admins = sorted(config.all_admin_ids())
    lines = [f"👑 <b>Адміни ({len(all_admins)}):</b>"]
    b = InlineKeyboardBuilder()
    if not all_admins:
        lines.append("<i>Список порожній.</i>")
    else:
        for uid in all_admins:
            lines.append(f"• <code>{uid}</code>")
            if len(all_admins) > 1:
                b.button(text=f"✖️ Видалити {uid}", callback_data=f"adm:del:{uid}")
        if len(all_admins) > 1:
            b.adjust(1)
    act = InlineKeyboardBuilder()
    act.button(text="➕ Додати нового адміна (User ID)", callback_data="adm:add")
    act.button(text="⬅️ До категорій клопотань", callback_data="menu")
    act.adjust(1)
    b.attach(act)
    return "\n".join(lines), b.as_markup()


async def _require_admin_msg(m: Message, state: FSMContext | None = None) -> bool:
    uid = m.from_user.id if m.from_user else None
    if config.is_admin(uid):
        return True
    if state is not None and await state.get_state() == Form.adding_admin.state:
        await state.clear()
    await m.answer("⛔ Доступно лише адміністраторам.")
    return False


async def _require_admin_cb(c: CallbackQuery) -> bool:
    uid = c.from_user.id if c.from_user else None
    if config.is_admin(uid):
        return True
    await c.answer("⛔ Доступно лише адміністраторам.", show_alert=True)
    return False


@router.message(CommandStart())
async def start(m: Message, state: FSMContext):
    d = await state.get_data()
    await drop_kb(m.bot, m.chat.id, d.get("mid"))
    await state.clear()
    await m.answer(
        "Привіт! Я створюю клопотання у .docx 📄\nОберіть тип:\n\n<i>Перевірити готовий .docx – /check</i>",
        reply_markup=main_menu(),
    )


@router.message(Command("new"))
async def new(m: Message, state: FSMContext):
    d = await state.get_data()
    await drop_kb(m.bot, m.chat.id, d.get("mid"))
    await state.clear()
    await m.answer("Оберіть тип клопотання:", reply_markup=main_menu())


@router.message(Command("admins"))
async def admins_cmd(m: Message, state: FSMContext):
    if not await _require_admin_msg(m, state):
        return
    await state.clear()
    text, kb = _admins_view()
    await m.answer(text, reply_markup=kb)


@router.callback_query(F.data == "adm:list")
async def adm_list_cb(c: CallbackQuery, state: FSMContext):
    if not await _require_admin_cb(c):
        return
    await state.clear()
    text, kb = _admins_view()
    await c.answer()
    await c.message.edit_text(text, reply_markup=kb)


@router.callback_query(F.data == "adm:add")
async def adm_add_cb(c: CallbackQuery, state: FSMContext):
    if not await _require_admin_cb(c):
        return
    await state.set_state(Form.adding_admin)
    b = InlineKeyboardBuilder()
    b.button(text="⬅️ Назад", callback_data="adm:list")
    await c.answer()
    await c.message.edit_text(
        "Введіть <b>User ID</b> нового адміна (можна кілька через пробіл або кому):",
        reply_markup=b.as_markup(),
    )


@router.callback_query(F.data.startswith("adm:del:"))
async def adm_del_cb(c: CallbackQuery):
    if not await _require_admin_cb(c):
        return
    if len(config.all_admin_ids()) <= 1:
        return await c.answer("Не можна видалити єдиного адміністратора.", show_alert=True)
    uid = int(c.data.split(":")[2])
    config.remove_admin_id(uid)
    text, kb = _admins_view()
    await c.answer("Адміна видалено")
    await c.message.edit_text(text, reply_markup=kb)


@router.message(Form.adding_admin, F.text)
async def on_add_admin_text(m: Message, state: FSMContext):
    if not await _require_admin_msg(m, state):
        return
    try:
        uids = parse_user_ids(m.text)
    except ValueError:
        return await m.answer("⚠️ Введіть числовий <b>User ID</b> (наприклад: <code>123456789</code>):")
    for uid in uids:
        config.add_admin_id(uid)
    await state.clear()
    text, kb = _admins_view()
    await m.answer(f"✅ Додано у список адмінів!\n\n{text}", reply_markup=kb)


@router.message(Command("help"))
async def help_(m: Message):
    lines = [
        "/new – нове клопотання",
        "/check – перевірити готовий .docx",
        "/cancel – скасувати",
        "",
        "Кілька клопотань можна зібрати в один файл: «➕ Додати ще в цей файл».",
        (
            "Дати: <code>16.09.2026</code>, <code>17-18.10.2026</code>, <code>23.10.2026, 26.10.2026</code>; "
            "свій текст – з «!» на початку."
        ),
    ]
    await m.answer("\n".join(lines))


@router.message(Command("check"))
async def check_cmd(m: Message):
    await m.answer(
        "Надішліть .docx (одне чи кілька клопотань в одному файлі) – я перевірю дати, адресата, "
        "підписи, лапки, апострофи, групи студентів, номери авто тощо 🔍"
    )


@router.message(Command("cancel"))
async def cancel_cmd(m: Message, state: FSMContext):
    d = await state.get_data()
    await drop_kb(m.bot, m.chat.id, d.get("mid"))
    await state.clear()
    await m.answer("Скасовано. /new – почати знову.")


@router.callback_query(F.data.startswith("cat:"))
async def pick_category(c: CallbackQuery):
    cat = c.data.split(":", 1)[1]
    if cat not in CATEGORIES:
        return await c.answer("Категорію не знайдено", show_alert=True)
    await c.message.edit_text(CATEGORIES[cat], reply_markup=category_kb(cat))
    await c.answer()


@router.callback_query(F.data == "menu")
async def menu_cb(c: CallbackQuery):
    await c.message.edit_text("Оберіть тип:", reply_markup=main_menu())
    await c.answer()


@router.callback_query(F.data.startswith("tpl:"))
async def pick_template(c: CallbackQuery, state: FSMContext):
    tpl_id = c.data.split(":", 1)[1]
    if tpl_id not in TEMPLATES:
        return await c.answer("Шаблон не знайдено", show_alert=True)
    old = await state.get_data()
    if isinstance(c.message, Message) and c.message.message_id != old.get("mid"):
        await drop_kb(c.bot, c.message.chat.id, c.message.message_id)
    tpl = TEMPLATES[tpl_id]
    await state.update_data(
        tpl=tpl.id,
        i=0,
        a={},
        custom=False,
        edit=False,
        dmode=None,
        rs=None,
        batch=old.get("batch", []),
    )
    await state.set_state(Form.filling)
    await c.answer()
    await c.message.answer(f"📌 Адресат: <b>{html.escape(_addr_hint(tpl))}</b> (підставиться автоматично)")
    await ask(c.message, state, c.from_user.id)


@router.message(F.document)
async def on_document(m: Message, bot: Bot):
    doc = m.document
    if not (doc.file_name or "").lower().endswith(".docx"):
        return await m.answer("Я перевіряю лише файли .docx 🙂")
    if doc.file_size and doc.file_size > 10 * 1024 * 1024:
        return await m.answer("Файл завеликий (понад 10 МБ).")
    buf = BytesIO()
    await bot.download(doc, destination=buf)
    raw = buf.getvalue()
    try:
        chunks = check_docx(raw)
    except Exception:  # noqa: BLE001
        logging.exception("check_docx failed")
        return await m.answer("Не вдалося прочитати файл 😔 Перевірте, що це справжній .docx")
    out, cur = [], ""
    for ch in chunks:
        if len(cur) + len(ch) > 3800:
            out.append(cur)
            cur = ""
        cur += ch + "\n"
    out.append(cur)
    for part in out:
        await m.answer(part, reply_markup=None)


@router.callback_query()
async def stale_cb(c: CallbackQuery):
    if isinstance(c.message, Message):
        with suppress(TelegramBadRequest):
            await c.message.edit_reply_markup(reply_markup=None)
    await c.answer("Ця кнопка вже неактуальна. Почніть заново: /new", show_alert=True)
