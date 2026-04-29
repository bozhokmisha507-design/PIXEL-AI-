import os
import logging
import hmac
import hashlib
import asyncio
from aiohttp import web
from telegram import Bot
from config import Config
from database.db import get_db
from handlers.payment import process_yookassa_webhook

logger = logging.getLogger(__name__)

def verify_yookassa_signature(data: bytes, signature: str, secret_key: str) -> bool:
    """
    Проверяет подпись уведомления от ЮKassa.
    signature – значение из заголовка HTTP_YOKASSA_SIGNATURE (или аналогичного).
    """
    try:
        expected = hmac.new(
            secret_key.encode('utf-8'),
            data,
            hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature)
    except Exception as e:
        logger.error(f"Ошибка проверки подписи: {e}")
        return False

async def health_handler(request):
    """Эндпоинт для проверки работоспособности сервера."""
    return web.Response(text='OK')

async def yookassa_webhook_handler(request):
    # Логируем IP для отладки
    client_ip = request.remote
    logger.info(f"Вебхук запрос от {client_ip}")
    
    # Читаем тело запроса
    body = await request.read()
    signature = request.headers.get('HTTP_YOKASSA_SIGNATURE', '')
    
    # Проверка подписи (если настроен секретный ключ)
    if Config.YKASSA_SECRET_KEY:
        if not verify_yookassa_signature(body, signature, Config.YKASSA_SECRET_KEY):
            logger.warning(f"Неверная подпись от {client_ip}")
            return web.Response(status=403, text='Forbidden')
    else:
        logger.warning("YKASSA_SECRET_KEY не задан, подпись не проверяется")
    
    try:
        data = await request.json()
        event = data.get('event')
        logger.info(f"Получено событие: {event}")
        
        bot: Bot = request.app['bot']
        db = await get_db()
        
        # Обработка событий
        if event == 'payment.succeeded':
            # Запускаем обработку в фоне, чтобы сразу ответить OK
            asyncio.create_task(process_yookassa_webhook(data, bot, db))
        elif event == 'payment.canceled':
            logger.info(f"Платёж отменён: {data.get('object', {}).get('id')}")
        elif event == 'payment.waiting_for_capture':
            logger.info(f"Платёж ожидает подтверждения: {data.get('object', {}).get('id')}")
        else:
            logger.info(f"Необрабатываемое событие: {event}")
        
        # Отвечаем сразу, чтобы ЮKassa не повторял запрос
        return web.Response(text='OK')
    except Exception as e:
        logger.error(f"Ошибка при обработке вебхука: {e}", exc_info=True)
        return web.Response(status=500, text='Internal Server Error')

async def start_webhook_server(bot: Bot):
    app = web.Application()
    app['bot'] = bot
    app.router.add_post('/yookassa-webhook', yookassa_webhook_handler)
    app.router.add_get('/health', health_handler)

    port = int(os.getenv("WEBHOOK_PORT", 8443))
    logger.info(f"🌐 Запуск веб-сервера на порту {port}")
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logger.info(f"🌐 Веб-сервер для уведомлений ЮKassa запущен на порту {port}")