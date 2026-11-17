"""Мідлвари захисту від застарілих inline-кнопок."""
from __future__ import annotations

from contextlib import suppress

from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message


class StaleGuard(BaseMiddleware):
    """Ігнорує натискання кнопок під попередніми повідомленнями діалогу."""

    async def __call__(self, handler, event, data):
        if not (event.data or "").startswith(("menu", "cat:", "tpl:", "adm:")):
            state = data.get("state")
            mid = (await state.get_data()).get("mid") if state else None
            if mid and isinstance(event.message, Message) and event.message.message_id != mid:
                with suppress(TelegramBadRequest):
                    await event.message.edit_reply_markup(reply_markup=None)
                return await event.answer(
                    "Ця кнопка вже неактуальна – користуйтеся останнім повідомленням ⬇️",
                    show_alert=True,
                )
        return await handler(event, data)
