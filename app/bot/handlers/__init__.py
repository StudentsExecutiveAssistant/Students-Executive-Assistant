"""Реєстрація обробників роутера (catch-all у common має підключатися останнім)."""

from app.bot.handlers import common, form, responsibles

__all__ = ["common", "form", "responsibles"]
