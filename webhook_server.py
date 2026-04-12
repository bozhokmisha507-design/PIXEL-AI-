import os
import logging
from aiohttp import web
from telegram import Bot
from config import Config
from database.db import get_db
from handlers.robokassa import (
    robokassa_result_handler,
    robokassa_success_handler,
    robokassa_fail_handler,
)

logger = logging.getLogger(__name__)

async def start_webhook_server(bot: Bot):
    app = web.Application()
    app["bot"] = bot

    # Эндпоинты Robokassa
    app.router.add_post("/robokassa/result", robokassa_result_handler)
    app.router.add_get("/robokassa/success", robokassa_success_handler)
    app.router.add_get("/robokassa/fail", robokassa_fail_handler)

    port = int(os.getenv("WEBHOOK_PORT", 8443))
    logger.info(f"🌐 Запуск веб-сервера на порту {port}")

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"🌐 Веб-сервер для уведомлений Robokassa запущен на порту {port}")