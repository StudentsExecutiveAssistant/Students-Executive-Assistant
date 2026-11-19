"""Реєстрація обробників роутера (catch-all у common має підключатися останнім)."""

from app.bot.handlers import common, feedback, form, petitions, responsibles

__all__ = ["common", "feedback", "form", "petitions", "responsibles"]
