"""Реєстрація обробників роутера (catch-all у common має підключатися останнім)."""
from app.bot.handlers import responsibles, form, common

__all__ = ["common", "form", "responsibles"]
