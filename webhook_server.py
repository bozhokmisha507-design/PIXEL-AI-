import logging
from aiohttp import web
from telegram import Bot
from config import Config
from database.db import Database
from handlers.payment import handle_yoomoney_notification

logger = logging.getLogger(__name__)

async def yoomoney_webhook_handler(request):
    """Обрабатывает POST-запрос от ЮMoney с уведомлением об оплате."""
    try:
        # ЮMoney отправляет данные в формате application/x-www-form-urlencoded
        data = await request.post()
        # Преобразуем multidict в обычный dict для удобства
        data_dict = dict(data)
        logger.info(f"Получено уведомление от ЮMoney: {data_dict}")

        # Получаем экземпляры bot и db из приложения aiohttp
        app = request.app
        bot: Bot = app['bot']
        db: Database = app['db']

        # Вызываем функцию-обработчик из payment.py
        await handle_yoomoney_notification(data_dict, bot, db)

        # ЮMoney ожидает ответ 200 OK
        return web.Response(text='OK')
    except Exception as e:
        logger.error(f"Ошибка при обработке вебхука: {e}", exc_info=True)
        return web.Response(status=500, text='Internal Server Error')

async def start_webhook_server(bot: Bot, db: Database):
    """Запускает aiohttp сервер на указанном порту."""
    app = web.Application()
    app['bot'] = bot
    app['db'] = db
    app.router.add_post('/yoomoney-webhook', yoomoney_webhook_handler)

    # Порт можно задать в config.py, по умолчанию 8080
    port = Config.WEBHOOK_PORT
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logger.info(f"🌐 Веб-сервер для уведомлений запущен на порту {port}")