"""Точка входу Telegram-бота для генерації та перевірки клопотань (.docx)."""
from __future__ import annotations

from app.bot import Form, StaleGuard, main, router, run

__all__ = ["Form", "StaleGuard", "main", "router", "run"]

if __name__ == "__main__":
    run()
