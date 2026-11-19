"""Команди меню, керування адмінами, вибір категорії/шаблону та перевірка завантажених .docx."""

from __future__ import annotations

import html
import logging
from contextlib import suppress
from io import BytesIO

from aiogram import Bot, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app import config
from app.bot.handlers.feedback import release_admin_ticket
from app.bot.handlers.form import ask
from app.bot.handlers.petitions import release_admin_petition
from app.bot.handlers.shared import drop_kb
from app.bot.keyboards import category_kb, main_menu
from app.bot.states import Form, router
from app.core.cleaners import parse_user_ids
from app.core.templates import CATEGORIES, TEMPLATES, Template, addressee_label
from app.docx.validator import check_docx

logger = logging.getLogger(__name__)

_ADDR_NOTE = {
	"equipment": " (для приміщення L.I.S. – центр тьюторства; інтерактивна дошка – Логойда + підпис ЕРДТ)",
}


def _addr_hint(tpl: Template) -> str:
	if len(tpl.addressees) > 1:
		return "обираєте нижче"
	base = (
		"директор / директорка обраного інституту"
		if tpl.addressees[0] == "institute"
		else addressee_label(tpl.addressees[0])
	)
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
	uid = c.from_user.id
	if config.is_admin(uid):
		return True
	await c.answer("⛔ Доступно лише адміністраторам.", show_alert=True)
	return False


async def _release_admin_locks(bot: Bot | None, admin_id: int) -> tuple[bool, bool]:
	fb = await release_admin_ticket(bot, admin_id)
	pet = await release_admin_petition(bot, admin_id)
	return fb, pet


@router.message(CommandStart())
async def start(m: Message, state: FSMContext) -> None:
	if m.from_user:
		await _release_admin_locks(m.bot, m.from_user.id)
	d = await state.get_data()
	await drop_kb(m.bot, m.chat.id, d.get("mid"))
	await state.clear()
	await m.answer(
		"Привіт! Я створюю клопотання у .docx 📄\nОберіть тип:\n\n<i>Перевірити готовий .docx – /check</i>",
		reply_markup=main_menu(),
	)


@router.message(Command("new"))
async def new(m: Message, state: FSMContext) -> None:
	if m.from_user:
		await _release_admin_locks(m.bot, m.from_user.id)
	d = await state.get_data()
	await drop_kb(m.bot, m.chat.id, d.get("mid"))
	await state.clear()
	await m.answer("Оберіть тип клопотання:", reply_markup=main_menu())


@router.message(Command("admins"))
async def admins_cmd(m: Message, state: FSMContext) -> None:
	if not await _require_admin_msg(m, state):
		return
	if m.from_user:
		await _release_admin_locks(m.bot, m.from_user.id)
	await state.clear()
	text, kb = _admins_view()
	await m.answer(text, reply_markup=kb)


@router.callback_query(F.data == "adm:list")
async def adm_list_cb(c: CallbackQuery, state: FSMContext) -> None:
	if not await _require_admin_cb(c):
		return
	await _release_admin_locks(c.bot, c.from_user.id)
	await state.clear()
	text, kb = _admins_view()
	await c.answer()
	if isinstance(c.message, Message):
		await c.message.edit_text(text, reply_markup=kb)


@router.callback_query(F.data == "adm:add")
async def adm_add_cb(c: CallbackQuery, state: FSMContext) -> None:
	if not await _require_admin_cb(c):
		return
	await _release_admin_locks(c.bot, c.from_user.id)
	await state.set_state(Form.adding_admin)
	b = InlineKeyboardBuilder()
	b.button(text="⬅️ Назад", callback_data="adm:list")
	await c.answer()
	if isinstance(c.message, Message):
		await c.message.edit_text(
			"Введіть <b>User ID</b> нового адміна (можна кілька через пробіл або кому):",
			reply_markup=b.as_markup(),
		)


@router.callback_query(F.data.startswith("adm:del:"))
async def adm_del_cb(c: CallbackQuery) -> None:
	if not await _require_admin_cb(c) or c.data is None:
		return
	if len(config.all_admin_ids()) <= 1:
		await c.answer("Не можна видалити єдиного адміністратора.", show_alert=True)
		return
	uid = int(c.data.split(":")[2])
	config.remove_admin_id(uid)
	await _release_admin_locks(c.bot, uid)
	text, kb = _admins_view()
	await c.answer("Адміна видалено")
	if isinstance(c.message, Message):
		await c.message.edit_text(text, reply_markup=kb)


@router.message(Form.adding_admin, F.text)
async def on_add_admin_text(m: Message, state: FSMContext) -> None:
	if not await _require_admin_msg(m, state) or m.text is None:
		return
	try:
		uids = parse_user_ids(m.text)
	except ValueError:
		await m.answer(
			"⚠️ Введіть числовий <b>User ID</b> (наприклад: <code>123456789</code>):"
		)
		return
	for uid in uids:
		config.add_admin_id(uid)
	await state.clear()
	text, kb = _admins_view()
	await m.answer(f"✅ Додано у список адмінів!\n\n{text}", reply_markup=kb)


@router.message(Command("help"))
async def help_(m: Message) -> None:
	lines = [
		"/new – нове клопотання",
		"/check – перевірити готовий .docx",
		"/feedback – надіслати фідбек",
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
async def check_cmd(m: Message) -> None:
	await m.answer(
		"Надішліть .docx (одне чи кілька клопотань в одному файлі) – я перевірю дати, адресата, "
		"підписи, лапки, апострофи, групи студентів, номери авто тощо 🔍"
	)


@router.message(Command("cancel"))
async def cancel_cmd(m: Message, state: FSMContext) -> None:
	released_fb, released_pet = (
		await _release_admin_locks(m.bot, m.from_user.id) if m.from_user else (False, False)
	)
	d = await state.get_data()
	await drop_kb(m.bot, m.chat.id, d.get("mid"))
	await state.clear()
	if released_fb:
		await m.answer("Скасовано. Фідбек повернуто іншим адміністраторам.")
	elif released_pet:
		await m.answer("Скасовано. Клопотання повернуто іншим адміністраторам.")
	else:
		await m.answer("Скасовано. /new – почати знову.")


@router.callback_query(F.data.startswith("cat:"))
async def pick_category(c: CallbackQuery) -> None:
	if c.data is None:
		return
	cat = c.data.split(":", 1)[1]
	if cat not in CATEGORIES:
		await c.answer("Категорію не знайдено", show_alert=True)
		return
	if isinstance(c.message, Message):
		await c.message.edit_text(CATEGORIES[cat], reply_markup=category_kb(cat))
	await c.answer()


@router.callback_query(F.data == "menu")
async def menu_cb(c: CallbackQuery) -> None:
	if isinstance(c.message, Message):
		await c.message.edit_text("Оберіть тип:", reply_markup=main_menu())
	await c.answer()


@router.callback_query(F.data.startswith("tpl:"))
async def pick_template(c: CallbackQuery, state: FSMContext) -> None:
	if c.data is None:
		return
	tpl_id = c.data.split(":", 1)[1]
	if tpl_id not in TEMPLATES:
		await c.answer("Шаблон не знайдено", show_alert=True)
		return
	await _release_admin_locks(c.bot, c.from_user.id)
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
	if isinstance(c.message, Message):
		await c.message.answer(
			f"📌 Адресат: <b>{html.escape(_addr_hint(tpl))}</b> (підставиться автоматично)"
		)
		await ask(c.message, state, c.from_user.id)


@router.message(F.document)
async def on_document(m: Message, bot: Bot) -> None:
	doc = m.document
	if doc is None:
		return
	if not (doc.file_name or "").lower().endswith(".docx"):
		await m.answer("Я перевіряю лише файли .docx 🙂")
		return
	if doc.file_size and doc.file_size > 10 * 1024 * 1024:
		await m.answer("Файл завеликий (понад 10 МБ).")
		return
	buf = BytesIO()
	await bot.download(doc, destination=buf)
	raw = buf.getvalue()
	try:
		chunks = check_docx(raw)
	except Exception:
		logger.exception("check_docx failed")
		await m.answer("Не вдалося прочитати файл 😔 Перевірте, що це справжній .docx")
		return
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
async def stale_cb(c: CallbackQuery) -> None:
	if isinstance(c.message, Message):
		with suppress(TelegramBadRequest):
			await c.message.edit_reply_markup(reply_markup=None)
	await c.answer("Ця кнопка вже неактуальна. Почніть заново: /new", show_alert=True)
