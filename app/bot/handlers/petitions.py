"""Адмін-обробка створених клопотань у пам'яті: «Надруковано» та «Відмовлено» (з причиною або без)."""

from __future__ import annotations

import html
import logging
import secrets
from contextlib import suppress
from dataclasses import dataclass, field

from aiogram import Bot, F
from aiogram.exceptions import AiogramError, TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.methods import SendDocument
from aiogram.types import (
	BufferedInputFile,
	CallbackQuery,
	InlineKeyboardMarkup,
	Message,
	User,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app import config
from app.bot.states import Form, router
from app.core.templates import TEMPLATES

logger = logging.getLogger(__name__)

MAX_OPEN_REVIEWS = 500
MAX_TEXT_LEN = 3000
MAX_HTML_LEN = 3500
MAX_CAPTION_REASON_LEN = 300


@dataclass
class PetitionReview:
	review_id: str
	creator_id: int
	author_html: str
	tpl_title: str
	count: int
	base_caption: str
	admin_messages: dict[int, int] = field(default_factory=dict)
	rejecting_by: int | None = None
	rejecting_by_label: str = ""


_REVIEWS: dict[str, PetitionReview] = {}


def reset_reviews() -> None:
	_REVIEWS.clear()


def _active_reject_for(admin_id: int) -> PetitionReview | None:
	for review in _REVIEWS.values():
		if review.rejecting_by == admin_id:
			return review
	return None


def has_active_petition_reject(admin_id: int) -> bool:
	return _active_reject_for(admin_id) is not None


def _user_html(user: User) -> str:
	name_part = html.escape(user.full_name or str(user.id))
	user_part = f" (@{html.escape(user.username)})" if user.username else ""
	return f"{name_part}{user_part} [ID: <code>{user.id}</code>]"


def _admin_label_html(user: User) -> str:
	name = html.escape(user.full_name or str(user.id))
	return f"{name} (@{html.escape(user.username)})" if user.username else name


def _review_kb(review_id: str) -> InlineKeyboardMarkup:
	b = InlineKeyboardBuilder()
	b.button(text="🖨 Надруковано", callback_data=f"pet:print:{review_id}")
	b.button(text="❌ Відмовлено", callback_data=f"pet:reject:{review_id}")
	b.adjust(2)
	return b.as_markup()


def _rejecting_kb(review_id: str) -> InlineKeyboardMarkup:
	b = InlineKeyboardBuilder()
	b.button(text="📤 Надіслати без причини", callback_data=f"pet:noreason:{review_id}")
	b.button(text="↩️ Скасувати", callback_data=f"pet:cancel:{review_id}")
	b.adjust(1)
	return b.as_markup()


def _open_caption(review: PetitionReview) -> str:
	return f"{review.base_caption}\n\n🟡 <i>Очікує обробки</i>"


def _clip_caption_reason(reason: str) -> str:
	if len(reason) <= MAX_CAPTION_REASON_LEN:
		return html.escape(reason)
	return html.escape(reason[: MAX_CAPTION_REASON_LEN - 1].rstrip()) + "…"


async def _sync_open(bot: Bot | None, review: PetitionReview) -> None:
	if bot is None:
		return
	active_admins = config.all_admin_ids()
	caption = _open_caption(review)
	kb = _review_kb(review.review_id)
	for admin_uid, msg_id in list(review.admin_messages.items()):
		if admin_uid not in active_admins:
			with suppress(AiogramError, OSError):
				await bot.edit_message_reply_markup(
					chat_id=admin_uid, message_id=msg_id, reply_markup=None
				)
			review.admin_messages.pop(admin_uid, None)
			continue
		with suppress(AiogramError, OSError):
			await bot.edit_message_caption(
				chat_id=admin_uid, message_id=msg_id, caption=caption, reply_markup=kb
			)


async def _sync_rejecting(bot: Bot | None, review: PetitionReview) -> None:
	if bot is None:
		return
	claimer_caption = (
		f"{review.base_caption}\n\n⏳ <b>Оформлення відмови.</b> "
		"Напишіть причину одним повідомленням або скористайтеся кнопками нижче."
	)
	other_caption = (
		f"{review.base_caption}\n\n🔒 Оформлює відмову: <b>{review.rejecting_by_label}</b>"
	)
	kb = _rejecting_kb(review.review_id)
	for admin_uid, msg_id in list(review.admin_messages.items()):
		is_claimer = admin_uid == review.rejecting_by
		with suppress(AiogramError, OSError):
			await bot.edit_message_caption(
				chat_id=admin_uid,
				message_id=msg_id,
				caption=claimer_caption if is_claimer else other_caption,
				reply_markup=kb if is_claimer else None,
			)


async def _sync_printed(
	bot: Bot | None,
	review: PetitionReview,
	actor_id: int,
	actor_label: str,
	delivered: bool,
) -> None:
	if bot is None:
		return
	if delivered:
		actor_caption = (
			f"{review.base_caption}\n\n🖨 <b>Надруковано</b> (ви). Автора сповіщено."
		)
		other_caption = (
			f"{review.base_caption}\n\n🖨 <b>Надруковано</b>: <b>{actor_label}</b>"
		)
	else:
		actor_caption = (
			f"{review.base_caption}\n\n🖨 <b>Надруковано</b> (ви).\n"
			"⚠️ Не вдалося сповістити автора (можливо, він заблокував бота)."
		)
		other_caption = (
			f"{review.base_caption}\n\n🖨 <b>Надруковано</b>: <b>{actor_label}</b> "
			"(автора не вдалося сповістити)"
		)
	for admin_uid, msg_id in list(review.admin_messages.items()):
		with suppress(AiogramError, OSError):
			await bot.edit_message_caption(
				chat_id=admin_uid,
				message_id=msg_id,
				caption=actor_caption if admin_uid == actor_id else other_caption,
				reply_markup=None,
			)


async def _sync_rejected(
	bot: Bot | None,
	review: PetitionReview,
	actor_id: int,
	actor_label: str,
	reason: str | None,
	delivered: bool,
) -> None:
	if bot is None:
		return
	reason_line = f"\n💬 Причина: {_clip_caption_reason(reason)}" if reason else ""
	if delivered:
		actor_caption = f"{review.base_caption}\n\n❌ <b>Відмовлено</b> (ви). Автора сповіщено.{reason_line}"
		other_caption = f"{review.base_caption}\n\n❌ <b>Відмовлено</b>: <b>{actor_label}</b>{reason_line}"
	else:
		actor_caption = (
			f"{review.base_caption}\n\n❌ <b>Відмовлено</b> (ви).{reason_line}\n"
			"⚠️ Не вдалося сповістити автора (можливо, він заблокував бота)."
		)
		other_caption = (
			f"{review.base_caption}\n\n❌ <b>Відмовлено</b>: <b>{actor_label}</b> "
			f"(автора не вдалося сповістити){reason_line}"
		)
	for admin_uid, msg_id in list(review.admin_messages.items()):
		with suppress(AiogramError, OSError):
			await bot.edit_message_caption(
				chat_id=admin_uid,
				message_id=msg_id,
				caption=actor_caption if admin_uid == actor_id else other_caption,
				reply_markup=None,
			)


async def release_admin_petition(bot: Bot | None, admin_id: int) -> bool:
	review = _active_reject_for(admin_id)
	if review is None:
		return False
	review.rejecting_by = None
	review.rejecting_by_label = ""
	await _sync_open(bot, review)
	return True


def _evict_if_full() -> None:
	if len(_REVIEWS) < MAX_OPEN_REVIEWS:
		return
	victim = next((rid for rid, r in _REVIEWS.items() if r.rejecting_by is None), None)
	if victim is None:
		victim = next(iter(_REVIEWS))
	_REVIEWS.pop(victim, None)


def _new_review_id() -> str:
	while True:
		rid = secrets.token_hex(4)
		if rid not in _REVIEWS:
			return rid


async def notify_admins(
	bot: Bot | None, creator: User, data: bytes, filename: str, tpl_id: str, count: int
) -> int:
	if bot is None:
		return 0
	recipients = sorted(config.all_admin_ids() - {creator.id})
	if not recipients:
		return 0
	author = _user_html(creator)
	tpl_title = html.escape(TEMPLATES[tpl_id].title)
	if count == 1:
		base_caption = f"📥 <b>Нове клопотання</b>\n👤 Від: {author}\n📄 Тип: {tpl_title}"
	else:
		base_caption = (
			f"📥 <b>Нові клопотання</b> ({count} шт.)\n"
			f"👤 Від: {author}\n📄 Останній тип: {tpl_title}"
		)
	review = PetitionReview(
		review_id=_new_review_id(),
		creator_id=creator.id,
		author_html=author,
		tpl_title=tpl_title,
		count=count,
		base_caption=base_caption,
	)
	caption = _open_caption(review)
	kb = _review_kb(review.review_id)
	for admin_uid in recipients:
		try:
			sent = await bot(
				SendDocument(
					chat_id=admin_uid,
					document=BufferedInputFile(data, filename),
					caption=caption,
					reply_markup=kb,
				)
			)
			review.admin_messages[admin_uid] = sent.message_id
		except (AiogramError, OSError) as exc:
			logger.warning("Failed to notify admin %s: %s", admin_uid, exc)
	if review.admin_messages:
		_evict_if_full()
		_REVIEWS[review.review_id] = review
	return len(review.admin_messages)


async def _finalize_rejection(
	bot: Bot | None,
	review: PetitionReview,
	actor_id: int,
	actor_label: str,
	reason: str | None,
) -> bool:
	delivered = False
	if bot is not None:
		if review.count == 1:
			head = f"❌ <b>У клопотанні відмовлено</b>\n📄 Тип: {review.tpl_title}"
		else:
			head = (
				f"❌ <b>У клопотаннях ({review.count} шт.) відмовлено</b>\n"
				f"📄 Останній тип: {review.tpl_title}"
			)
		user_text = f"{head}\n💬 Причина: {html.escape(reason)}" if reason else head
		try:
			await bot.send_message(review.creator_id, user_text)
			delivered = True
		except (AiogramError, OSError) as exc:
			logger.warning(
				"Failed to notify petition author %s about rejection: %s",
				review.creator_id,
				exc,
			)
	await _sync_rejected(bot, review, actor_id, actor_label, reason, delivered)
	return delivered


@router.callback_query(F.data.startswith("pet:print:"))
async def pet_print_cb(c: CallbackQuery) -> None:
	if not config.is_admin(c.from_user.id):
		await c.answer("⛔ Доступно лише адміністраторам.", show_alert=True)
		return
	if c.data is None:
		return
	review_id = c.data.split(":", 2)[2]
	review = _REVIEWS.get(review_id)
	if review is None:
		if isinstance(c.message, Message):
			with suppress(TelegramBadRequest):
				await c.message.edit_reply_markup(reply_markup=None)
		await c.answer("Це клопотання вже оброблено або недоступне.", show_alert=True)
		return
	if review.rejecting_by == c.from_user.id:
		await c.answer(
			"Спочатку завершіть або скасуйте відмову для цього клопотання.",
			show_alert=True,
		)
		return
	if review.rejecting_by is not None:
		if isinstance(c.message, Message):
			with suppress(TelegramBadRequest):
				await c.message.edit_reply_markup(reply_markup=None)
		await c.answer(
			"Інший адміністратор зараз оформлює відмову по цьому клопотанню.",
			show_alert=True,
		)
		return

	_REVIEWS.pop(review_id, None)
	actor_label = _admin_label_html(c.from_user)
	delivered = False
	if c.bot is not None:
		if review.count == 1:
			user_text = f"🖨 <b>Ваше клопотання надруковано!</b>\n📄 Тип: {review.tpl_title}"
		else:
			user_text = (
				f"🖨 <b>Ваші клопотання ({review.count} шт.) надруковано!</b>\n"
				f"📄 Останній тип: {review.tpl_title}"
			)
		try:
			await c.bot.send_message(review.creator_id, user_text)
			delivered = True
		except (AiogramError, OSError) as exc:
			logger.warning(
				"Failed to notify petition author %s about print: %s",
				review.creator_id,
				exc,
			)
	await _sync_printed(c.bot, review, c.from_user.id, actor_label, delivered)
	await c.answer(
		"Позначено як надруковане. Автора сповіщено."
		if delivered
		else "Позначено як надруковане (не вдалося сповістити автора)."
	)


@router.callback_query(F.data.startswith("pet:reject:"))
async def pet_reject_cb(c: CallbackQuery, state: FSMContext) -> None:
	if not config.is_admin(c.from_user.id):
		await c.answer("⛔ Доступно лише адміністраторам.", show_alert=True)
		return
	if c.data is None:
		return
	review_id = c.data.split(":", 2)[2]
	review = _REVIEWS.get(review_id)
	if review is None:
		if isinstance(c.message, Message):
			with suppress(TelegramBadRequest):
				await c.message.edit_reply_markup(reply_markup=None)
		await c.answer("Це клопотання вже оброблено або недоступне.", show_alert=True)
		return
	if review.rejecting_by == c.from_user.id:
		await c.answer(
			"Ви вже оформлюєте відмову. Напишіть причину в чат або натисніть «Надіслати без причини»."
		)
		return
	if review.rejecting_by is not None:
		if isinstance(c.message, Message):
			with suppress(TelegramBadRequest):
				await c.message.edit_reply_markup(reply_markup=None)
		await c.answer(
			"Інший адміністратор зараз оформлює відмову по цьому клопотанню.",
			show_alert=True,
		)
		return
	if _active_reject_for(c.from_user.id) is not None:
		await c.answer(
			"У вас вже відкрита відмова по іншому клопотанню. Спочатку завершіть або скасуйте її.",
			show_alert=True,
		)
		return
	if await state.get_state() is not None:
		await c.answer(
			"Спочатку завершіть поточну дію або виконайте /cancel.",
			show_alert=True,
		)
		return

	review.rejecting_by = c.from_user.id
	review.rejecting_by_label = _admin_label_html(c.from_user)

	await state.set_state(Form.petition_reject)
	await state.update_data(pet_review_id=review.review_id)
	await c.answer(
		"Напишіть причину відмови в чат або натисніть «Надіслати без причини»."
	)
	await _sync_rejecting(c.bot, review)


@router.callback_query(F.data.startswith("pet:noreason:"))
async def pet_noreason_cb(c: CallbackQuery, state: FSMContext) -> None:
	if not config.is_admin(c.from_user.id):
		await c.answer("⛔ Доступно лише адміністраторам.", show_alert=True)
		return
	if c.data is None:
		return
	review_id = c.data.split(":", 2)[2]
	review = _REVIEWS.get(review_id)
	if review is None:
		if isinstance(c.message, Message):
			with suppress(TelegramBadRequest):
				await c.message.edit_reply_markup(reply_markup=None)
		await c.answer("Це клопотання вже оброблено.", show_alert=True)
		return
	if review.rejecting_by != c.from_user.id:
		await c.answer(
			"Підтвердити може лише той адміністратор, який почав оформлення відмови.",
			show_alert=True,
		)
		return

	_REVIEWS.pop(review_id, None)
	await state.clear()
	actor_label = review.rejecting_by_label or _admin_label_html(c.from_user)
	delivered = await _finalize_rejection(
		c.bot, review, c.from_user.id, actor_label, reason=None
	)
	await c.answer(
		"Відмову надіслано автору."
		if delivered
		else "Відмовлено (не вдалося сповістити автора)."
	)


@router.callback_query(F.data.startswith("pet:cancel:"))
async def pet_cancel_cb(c: CallbackQuery, state: FSMContext) -> None:
	if not config.is_admin(c.from_user.id):
		await c.answer("⛔ Доступно лише адміністраторам.", show_alert=True)
		return
	if c.data is None:
		return
	review_id = c.data.split(":", 2)[2]
	review = _REVIEWS.get(review_id)
	if review is None:
		if isinstance(c.message, Message):
			with suppress(TelegramBadRequest):
				await c.message.edit_reply_markup(reply_markup=None)
		await c.answer("Це клопотання вже оброблено.", show_alert=True)
		return
	if review.rejecting_by != c.from_user.id:
		await c.answer(
			"Скасувати може лише той адміністратор, який почав оформлення відмови.",
			show_alert=True,
		)
		return

	review.rejecting_by = None
	review.rejecting_by_label = ""
	await state.clear()
	await c.answer("Оформлення відмови скасовано.")
	await _sync_open(c.bot, review)


@router.message(Form.petition_reject, F.text, ~F.text.startswith("/"))
async def on_petition_reject_text(m: Message, state: FSMContext) -> None:
	if m.from_user is None or m.text is None or m.bot is None:
		return
	uid = m.from_user.id
	if not config.is_admin(uid):
		await release_admin_petition(m.bot, uid)
		await state.clear()
		await m.answer("⛔ Доступно лише адміністраторам.")
		return

	d = await state.get_data()
	review_id = d.get("pet_review_id")
	review = _REVIEWS.get(review_id) if isinstance(review_id, str) else None
	if review is None or review.rejecting_by != uid:
		await state.clear()
		await m.answer("Це клопотання вже неактуальне.")
		return

	reason = m.text.strip()
	if not reason:
		await m.answer(
			"Введіть причину відмови або натисніть «📤 Надіслати без причини» чи «↩️ Скасувати»."
		)
		return
	if len(reason) > MAX_TEXT_LEN or len(html.escape(reason)) > MAX_HTML_LEN:
		await m.answer(
			f"Причина задовга (максимум {MAX_TEXT_LEN} символів). Скоротіть і надішліть ще раз."
		)
		return

	_REVIEWS.pop(review.review_id, None)
	await state.clear()
	actor_label = review.rejecting_by_label or _admin_label_html(m.from_user)
	delivered = await _finalize_rejection(m.bot, review, uid, actor_label, reason=reason)
	if delivered:
		await m.answer("❌ Відмову з причиною надіслано автору.")
	else:
		await m.answer(
			"⚠️ Не вдалося доставити сповіщення автору (можливо, він заблокував бота). "
			"Статус оновлено."
		)


@router.message(Form.petition_reject, ~F.text)
async def on_petition_reject_nontext(m: Message) -> None:
	await m.answer(
		"Надішліть причину відмови текстом або натисніть «📤 Надіслати без причини» чи «↩️ Скасувати» (або /cancel)."
	)
