"""Ініціалізація диспетчера та запуск Telegram-бота."""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from app import config
from app.bot import handlers as _handlers  # noqa: F401
from app.bot.middlewares import StaleGuard
from app.bot.states import Form, router

__all__ = ["Form", "StaleGuard", "create_dispatcher", "main", "router", "run"]


def create_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())
    router.callback_query.middleware(StaleGuard())
    dp.include_router(router)
    return dp


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    if not config.BOT_TOKEN:
        raise SystemExit("Задайте BOT_TOKEN (отримайте у @BotFather)")
    bot = Bot(config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = create_dispatcher()
    await dp.start_polling(bot)


def run() -> None:
    asyncio.run(main())
