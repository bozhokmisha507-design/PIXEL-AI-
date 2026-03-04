import os
import logging
from aiohttp import web
from telegram import Bot
from config import Config
from database.db import get_db
from handlers.payment import handle_yoomoney_notification

logger = logging.getLogger(__name__)

async def yoomoney_webhook_handler(request):
    """Обрабатывает POST-запрос от ЮMoney с уведомлением об оплате."""
    try:
        data = await request.post()
        data_dict = dict(data)
        logger.info(f"Получено уведомление от ЮMoney: {data_dict}")

        bot: Bot = request.app['bot']
        db = await get_db()  # получаем глобальный экземпляр БД

        await handle_yoomoney_notification(data_dict, bot, db)

        return web.Response(text='OK')
    except Exception as e:
        logger.error(f"Ошибка при обработке вебхука: {e}", exc_info=True)
        return web.Response(status=500, text='Internal Server Error')

async def start_webhook_server(bot: Bot):
    """Запускает aiohttp сервер на указанном порту."""
    app = web.Application()
    app['bot'] = bot
    app.router.add_post('/yoomoney-webhook', yoomoney_webhook_handler)

    port = int(os.getenv("WEBHOOK_PORT", 8080))
    logger.info(f"🌐 Запуск веб-сервера на порту {port}")

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logger.info(f"🌐 Веб-сервер для уведомлений запущен на порту {port}")