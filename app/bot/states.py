"""Стани FSM та спільний екземпляр роутера Telegram-бота."""
from __future__ import annotations

from aiogram import Router
from aiogram.fsm.state import State, StatesGroup

router = Router()


class Form(StatesGroup):
    filling = State()
    confirm = State()
    adding_admin = State()
