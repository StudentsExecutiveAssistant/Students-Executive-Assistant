"""Обробка фідбеку в пам'яті: надсилання, ексклюзивне взяття адміном та одноразова відповідь."""

from __future__ import annotations

import html
import logging
import secrets
from contextlib import suppress
from dataclasses import dataclass, field

from aiogram import Bot, F
from aiogram.exceptions import AiogramError, TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message, User
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app import config
from app.bot.handlers.petitions import has_active_petition_reject
from app.bot.handlers.shared import drop_kb
from app.bot.keyboards import main_menu
from app.bot.states import Form, router

logger = logging.getLogger(__name__)

MAX_OPEN_TICKETS = 500
MAX_TEXT_LEN = 3000
MAX_HTML_LEN = 3500

_FEEDBACK_PROMPT = (
	"💬 <b>Напишіть ваш фідбек, побажання або повідомлення про помилку</b> "
	"одним текстовим повідомленням.\n\n<i>Для скасування натисніть кнопку нижче або /cancel.</i>"
)


@dataclass
class FeedbackTicket:
	ticket_id: str
	user_id: int
	author_html: str
	text: str
	claimed_by: int | None = None
	claimed_by_label: str = ""
	admin_messages: dict[int, int] = field(default_factory=dict)


_TICKETS: dict[str, FeedbackTicket] = {}


def reset_tickets() -> None:
	_TICKETS.clear()


def _active_ticket_for(admin_id: int) -> FeedbackTicket | None:
	for ticket in _TICKETS.values():
		if ticket.claimed_by == admin_id:
			return ticket
	return None


def _user_html(user: User) -> str:
	name_part = html.escape(user.full_name or str(user.id))
	user_part = f" (@{html.escape(user.username)})" if user.username else ""
	return f"{name_part}{user_part} [ID: <code>{user.id}</code>]"


def _admin_label_html(user: User) -> str:
	name = html.escape(user.full_name or str(user.id))
	return f"{name} (@{html.escape(user.username)})" if user.username else name


def _cancel_kb() -> InlineKeyboardMarkup:
	b = InlineKeyboardBuilder()
	b.button(text="✖️ Скасувати", callback_data="fb:cancel")
	b.adjust(1)
	return b.as_markup()


def _take_kb(ticket_id: str) -> InlineKeyboardMarkup:
	b = InlineKeyboardBuilder()
	b.button(text="✋ Взяти фідбек", callback_data=f"fb:take:{ticket_id}")
	b.adjust(1)
	return b.as_markup()


def _release_kb(ticket_id: str) -> InlineKeyboardMarkup:
	b = InlineKeyboardBuilder()
	b.button(text="↩️ Відпустити", callback_data=f"fb:release:{ticket_id}")
	b.adjust(1)
	return b.as_markup()


def _card_body(ticket: FeedbackTicket) -> str:
	return (
		f"💬 <b>Фідбек #{ticket.ticket_id}</b>\n"
		f"👤 Від: {ticket.author_html}\n\n"
		f"{html.escape(ticket.text)}"
	)


def _open_card_text(ticket: FeedbackTicket) -> str:
	return f"{_card_body(ticket)}\n\n🟡 <i>Очікує відповіді</i>"


async def _sync_open(bot: Bot | None, ticket: FeedbackTicket) -> None:
	if bot is None:
		return
	active_admins = config.all_admin_ids()
	text = _open_card_text(ticket)
	kb = _take_kb(ticket.ticket_id)
	for admin_uid, msg_id in list(ticket.admin_messages.items()):
		if admin_uid not in active_admins:
			with suppress(AiogramError, OSError):
				await bot.edit_message_reply_markup(
					chat_id=admin_uid, message_id=msg_id, reply_markup=None
				)
			ticket.admin_messages.pop(admin_uid, None)
			continue
		with suppress(AiogramError, OSError):
			await bot.edit_message_text(
				chat_id=admin_uid, message_id=msg_id, text=text, reply_markup=kb
			)


async def _sync_claimed(bot: Bot | None, ticket: FeedbackTicket) -> None:
	if bot is None:
		return
	body = _card_body(ticket)
	claimer_text = (
		f"{body}\n\n🟢 <b>Ви взяли цей фідбек.</b> "
		"Напишіть відповідь одним повідомленням (або натисніть «Відпустити»)."
	)
	other_text = f"{body}\n\n🔒 Взяв у роботу: <b>{ticket.claimed_by_label}</b>"
	release_kb = _release_kb(ticket.ticket_id)
	for admin_uid, msg_id in list(ticket.admin_messages.items()):
		is_claimer = admin_uid == ticket.claimed_by
		with suppress(AiogramError, OSError):
			await bot.edit_message_text(
				chat_id=admin_uid,
				message_id=msg_id,
				text=claimer_text if is_claimer else other_text,
				reply_markup=release_kb if is_claimer else None,
			)


async def _sync_closed(
	bot: Bot | None,
	ticket: FeedbackTicket,
	replier_id: int,
	replier_label: str,
	delivered: bool,
) -> None:
	if bot is None:
		return
	body = _card_body(ticket)
	if delivered:
		replier_text = f"{body}\n\n✅ <b>Ви відповіли на цей фідбек.</b>"
		other_text = f"{body}\n\n✅ Відповів: <b>{replier_label}</b>"
	else:
		replier_text = (
			f"{body}\n\n⚠️ Не вдалося доставити відповідь користувачу "
			"(можливо, він заблокував бота)."
		)
		other_text = f"{body}\n\n⚠️ Спроба відповіді від <b>{replier_label}</b>: користувач недоступний."
	for admin_uid, msg_id in list(ticket.admin_messages.items()):
		with suppress(AiogramError, OSError):
			await bot.edit_message_text(
				chat_id=admin_uid,
				message_id=msg_id,
				text=replier_text if admin_uid == replier_id else other_text,
				reply_markup=None,
			)


async def release_admin_ticket(bot: Bot | None, admin_id: int) -> bool:
	ticket = _active_ticket_for(admin_id)
	if ticket is None:
		return False
	ticket.claimed_by = None
	ticket.claimed_by_label = ""
	await _sync_open(bot, ticket)
	return True


def _evict_if_full() -> None:
	if len(_TICKETS) < MAX_OPEN_TICKETS:
		return
	victim = next((tid for tid, t in _TICKETS.items() if t.claimed_by is None), None)
	if victim is None:
		victim = next(iter(_TICKETS))
	_TICKETS.pop(victim, None)


def _new_ticket_id() -> str:
	while True:
		tid = secrets.token_hex(4)
		if tid not in _TICKETS:
			return tid


@router.callback_query(F.data == "fb:new")
async def fb_new_cb(c: CallbackQuery, state: FSMContext) -> None:
	if _active_ticket_for(c.from_user.id) is not None:
		await c.answer(
			"Спочатку дайте відповідь на взятий фідбек або натисніть «Відпустити».",
			show_alert=True,
		)
		return
	if has_active_petition_reject(c.from_user.id):
		await c.answer(
			"Спочатку завершіть або скасуйте відмову по клопотанню.",
			show_alert=True,
		)
		return
	if not config.all_admin_ids():
		await c.answer(
			"Зараз немає доступних адміністраторів для отримання фідбеку.",
			show_alert=True,
		)
		return
	old = await state.get_data()
	if isinstance(c.message, Message):
		await drop_kb(c.bot, c.message.chat.id, old.get("mid"))
		if c.message.message_id != old.get("mid"):
			await drop_kb(c.bot, c.message.chat.id, c.message.message_id)
	await state.clear()
	await state.set_state(Form.feedback)
	await c.answer()
	if isinstance(c.message, Message):
		sent = await c.message.answer(_FEEDBACK_PROMPT, reply_markup=_cancel_kb())
		await state.update_data(mid=sent.message_id)


@router.message(Command("feedback"))
async def fb_cmd(m: Message, state: FSMContext) -> None:
	if m.from_user and _active_ticket_for(m.from_user.id) is not None:
		await m.answer(
			"Спочатку дайте відповідь на взятий фідбек або натисніть «↩️ Відпустити» (чи /cancel)."
		)
		return
	if m.from_user and has_active_petition_reject(m.from_user.id):
		await m.answer(
			"Спочатку завершіть або скасуйте відмову по клопотанню (чи /cancel)."
		)
		return
	if not config.all_admin_ids():
		await m.answer("Зараз немає доступних адміністраторів для отримання фідбеку.")
		return
	old = await state.get_data()
	await drop_kb(m.bot, m.chat.id, old.get("mid"))
	await state.clear()
	await state.set_state(Form.feedback)
	sent = await m.answer(_FEEDBACK_PROMPT, reply_markup=_cancel_kb())
	await state.update_data(mid=sent.message_id)


@router.callback_query(F.data == "fb:cancel")
async def fb_cancel_cb(c: CallbackQuery, state: FSMContext) -> None:
	if await state.get_state() != Form.feedback.state:
		if isinstance(c.message, Message):
			with suppress(TelegramBadRequest):
				await c.message.edit_reply_markup(reply_markup=None)
		await c.answer("Вже неактуально.")
		return
	await state.clear()
	await c.answer()
	if isinstance(c.message, Message):
		await c.message.edit_text(
			"Скасовано ✖️\nОберіть тип клопотання:", reply_markup=main_menu()
		)


@router.message(Form.feedback, F.text, ~F.text.startswith("/"))
async def on_feedback_text(m: Message, state: FSMContext) -> None:
	if m.from_user is None or m.text is None or m.bot is None:
		return
	text = m.text.strip()
	if not text:
		await m.answer("Напишіть текст фідбеку або натисніть «✖️ Скасувати».")
		return
	if len(text) > MAX_TEXT_LEN or len(html.escape(text)) > MAX_HTML_LEN:
		await m.answer(
			f"Повідомлення задовге (максимум {MAX_TEXT_LEN} символів). Скоротіть і надішліть ще раз."
		)
		return

	admins = sorted(config.all_admin_ids())
	d = await state.get_data()
	await drop_kb(m.bot, m.chat.id, d.get("mid"))
	await state.clear()

	if not admins:
		await m.answer(
			"Зараз немає доступних адміністраторів для отримання фідбеку.",
			reply_markup=main_menu(),
		)
		return

	ticket = FeedbackTicket(
		ticket_id=_new_ticket_id(),
		user_id=m.from_user.id,
		author_html=_user_html(m.from_user),
		text=text,
	)
	card_text = _open_card_text(ticket)
	kb = _take_kb(ticket.ticket_id)
	for admin_uid in admins:
		try:
			sent = await m.bot.send_message(admin_uid, card_text, reply_markup=kb)
			ticket.admin_messages[admin_uid] = sent.message_id
		except (AiogramError, OSError) as exc:
			logger.warning("Failed to deliver feedback to admin %s: %s", admin_uid, exc)

	if not ticket.admin_messages:
		await m.answer(
			"Не вдалося надіслати фідбек адміністраторам 😔 Спробуйте пізніше.",
			reply_markup=main_menu(),
		)
		return

	_evict_if_full()
	_TICKETS[ticket.ticket_id] = ticket
	await m.answer(
		"✅ Дякуємо! Ваш фідбек надіслано адміністраторам.\n"
		"Коли хтось із них відповість, відповідь прийде сюди.",
		reply_markup=main_menu(),
	)


@router.message(Form.feedback, ~F.text)
async def on_feedback_nontext(m: Message) -> None:
	await m.answer("Надішліть фідбек текстом (або натисніть «✖️ Скасувати» чи /cancel).")


@router.callback_query(F.data.startswith("fb:take:"))
async def fb_take_cb(c: CallbackQuery, state: FSMContext) -> None:
	if not config.is_admin(c.from_user.id):
		await c.answer("⛔ Доступно лише адміністраторам.", show_alert=True)
		return
	if c.data is None:
		return
	ticket_id = c.data.split(":", 2)[2]
	ticket = _TICKETS.get(ticket_id)
	if ticket is None:
		if isinstance(c.message, Message):
			with suppress(TelegramBadRequest):
				await c.message.edit_reply_markup(reply_markup=None)
		await c.answer("Цей фідбек вже закрито або недоступний.", show_alert=True)
		return
	if ticket.claimed_by == c.from_user.id:
		await c.answer("Ви вже взяли цей фідбек. Напишіть відповідь у чат.")
		return
	if ticket.claimed_by is not None:
		if isinstance(c.message, Message):
			with suppress(TelegramBadRequest):
				await c.message.edit_reply_markup(reply_markup=None)
		await c.answer("Цей фідбек вже взяв інший адміністратор.", show_alert=True)
		return
	if _active_ticket_for(c.from_user.id) is not None:
		await c.answer(
			"У вас вже є активний фідбек. Спочатку дайте відповідь або відпустіть його.",
			show_alert=True,
		)
		return
	if await state.get_state() is not None:
		await c.answer(
			"Спочатку завершіть поточну дію або виконайте /cancel.",
			show_alert=True,
		)
		return

	ticket.claimed_by = c.from_user.id
	ticket.claimed_by_label = _admin_label_html(c.from_user)

	await state.set_state(Form.feedback_reply)
	await state.update_data(fb_ticket_id=ticket.ticket_id)
	await c.answer("Фідбек закріплено за вами. Напишіть відповідь у чат.")
	await _sync_claimed(c.bot, ticket)


@router.callback_query(F.data.startswith("fb:release:"))
async def fb_release_cb(c: CallbackQuery, state: FSMContext) -> None:
	if not config.is_admin(c.from_user.id):
		await c.answer("⛔ Доступно лише адміністраторам.", show_alert=True)
		return
	if c.data is None:
		return
	ticket_id = c.data.split(":", 2)[2]
	ticket = _TICKETS.get(ticket_id)
	if ticket is None:
		if isinstance(c.message, Message):
			with suppress(TelegramBadRequest):
				await c.message.edit_reply_markup(reply_markup=None)
		await c.answer("Цей фідбек вже закрито.", show_alert=True)
		return
	if ticket.claimed_by != c.from_user.id:
		await c.answer(
			"Відпустити може лише той адміністратор, який взяв фідбек.",
			show_alert=True,
		)
		return

	ticket.claimed_by = None
	ticket.claimed_by_label = ""
	await state.clear()
	await c.answer("Фідбек повернуто іншим адміністраторам.")
	await _sync_open(c.bot, ticket)


@router.message(Form.feedback_reply, F.text, ~F.text.startswith("/"))
async def on_feedback_reply_text(m: Message, state: FSMContext) -> None:
	if m.from_user is None or m.text is None or m.bot is None:
		return
	uid = m.from_user.id
	if not config.is_admin(uid):
		await release_admin_ticket(m.bot, uid)
		await state.clear()
		await m.answer("⛔ Доступно лише адміністраторам.")
		return

	d = await state.get_data()
	ticket_id = d.get("fb_ticket_id")
	ticket = _TICKETS.get(ticket_id) if isinstance(ticket_id, str) else None
	if ticket is None or ticket.claimed_by != uid:
		await state.clear()
		await m.answer("Цей фідбек вже неактуальний.")
		return

	reply_text = m.text.strip()
	if not reply_text:
		await m.answer("Введіть текст відповіді або натисніть «↩️ Відпустити».")
		return
	if len(reply_text) > MAX_TEXT_LEN or len(html.escape(reply_text)) > MAX_HTML_LEN:
		await m.answer(
			f"Відповідь задовга (максимум {MAX_TEXT_LEN} символів). Скоротіть і надішліть ще раз."
		)
		return

	_TICKETS.pop(ticket.ticket_id, None)
	await state.clear()

	replier_label = ticket.claimed_by_label or _admin_label_html(m.from_user)
	delivered = False
	try:
		await m.bot.send_message(
			ticket.user_id,
			f"📩 <b>Відповідь адміністратора на ваш фідбек:</b>\n\n{html.escape(reply_text)}",
		)
		delivered = True
	except (AiogramError, OSError) as exc:
		logger.warning(
			"Failed to deliver feedback reply to user %s: %s", ticket.user_id, exc
		)

	await _sync_closed(m.bot, ticket, uid, replier_label, delivered)
	if delivered:
		await m.answer("✅ Відповідь надіслано користувачу. Фідбек закрито.")
	else:
		await m.answer(
			"⚠️ Не вдалося доставити відповідь користувачу (можливо, він заблокував бота). "
			"Фідбек закрито."
		)


@router.message(Form.feedback_reply, ~F.text)
async def on_feedback_reply_nontext(m: Message) -> None:
	await m.answer(
		"Надішліть відповідь текстом (або натисніть «↩️ Відпустити» чи /cancel)."
	)
