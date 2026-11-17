"""Точка входу Telegram-бота для генерації та перевірки клопотань (.docx)."""
from __future__ import annotations

import asyncio
import os
from aiohttp import web
from app.bot import Form, StaleGuard, main, router, run

__all__ = ["Form", "StaleGuard", "main", "router", "run"]

async def handle(request):
    return web.Response(text="Bot is alive!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"Dummy web server started on port {port}")

async def main_wrapper():
    # Запускаємо вебсервер і асинхронну функцію main() в одному головному потоці
    await asyncio.gather(
        start_web_server(),
        main()
    )

if __name__ == "__main__":
    try:
        asyncio.run(main_wrapper())
    except KeyboardInterrupt:
        pass