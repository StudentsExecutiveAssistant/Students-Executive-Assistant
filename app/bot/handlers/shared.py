"""Спільні утиліти навігації по кроках та керування клавіатурою повідомлень."""

from __future__ import annotations

from contextlib import suppress
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, Message

from app.core.templates import TEMPLATES, Step, visible_steps


def steps_of(d: dict[str, Any]) -> list[Step]:
	return visible_steps(TEMPLATES[d["tpl"]], d["a"])


def first_missing(d: dict[str, Any]) -> int | None:
	return next(
		(n for n, s in enumerate(steps_of(d)) if s.key not in d["a"] and not s.optional),
		None,
	)


async def drop_kb(bot: Bot | None, chat_id: int, mid: int | None) -> None:
	if bot and mid:
		with suppress(TelegramBadRequest):
			await bot.edit_message_reply_markup(
				chat_id=chat_id, message_id=mid, reply_markup=None
			)


async def send_step(
	msg: Message, state: FSMContext, text: str, kb: InlineKeyboardMarkup
) -> None:
	d = await state.get_data()
	await drop_kb(msg.bot, msg.chat.id, d.get("mid"))
	sent = await msg.answer(text, reply_markup=kb)
	await state.update_data(mid=sent.message_id)
