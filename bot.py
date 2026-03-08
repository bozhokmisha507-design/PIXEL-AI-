import os
import sys
import logging
import asyncio
import warnings
from telegram.warnings import PTBUserWarning

warnings.filterwarnings("ignore", category=PTBUserWarning)

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, CallbackQueryHandler
from telegram import Update

from config import Config
from database.db import get_db  # Импортируем функцию

from handlers.start import start_handler, help_handler, handle_main_menu_buttons, gender_callback
from handlers.menu import menu_handler
from handlers.styles import styles_handler, show_styles_cb, style_selected_cb
from handlers.upload import upload_conversation
from handlers.clean import clean_photos_handler
from handlers.payment import buy_handler, check_payments_job

from webhook_server import start_webhook_server

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def post_init(application: Application) -> None:
    """Опционально: можно оставить для получения информации о боте."""
    try:
        bot_user = await application.bot.get_me()
        logger.info(f"🤖 Бот: @{bot_user.username}")
    except Exception as e:
        logger.warning(f"Не удалось получить информацию о боте: {e}")

async def main_async():
    if not Config.BOT_TOKEN:
        logger.error("❌ BOT_TOKEN не найден! Проверьте .env файл")
        return

    Config.ensure_dirs()
    logger.info("📁 Папки созданы/проверены")

    # Инициализируем БД (глобальный экземпляр)
    db = await get_db()
    logger.info("✅ База данных инициализирована")

    application = Application.builder()\
        .token(Config.BOT_TOKEN)\
        .post_init(post_init)\
        .build()

    # Регистрация обработчиков
    application.add_handler(start_handler)
    application.add_handler(help_handler)
    application.add_handler(menu_handler)
    application.add_handler(styles_handler)
    application.add_handler(upload_conversation)
    application.add_handler(show_styles_cb)
    application.add_handler(style_selected_cb)
    application.add_handler(CallbackQueryHandler(gender_callback, pattern="^set_gender_"))
    application.add_handler(buy_handler)
    
    application.add_handler(MessageHandler(
        filters.Text([
            "📤 Загрузить фото",
            "💳 Купить генерацию",
            "🖼️ Стили",
            "❓ Помощь",
            "🗑 Очистить селфи",
            "🏠 Главное меню"
        ]),
        handle_main_menu_buttons
    ))
    application.add_handler(clean_photos_handler)

    # Фоновая задача проверки платежей
    job_queue = application.job_queue
    job_queue.run_repeating(check_payments_job, interval=15, first=10)

    # Запускаем веб-сервер (ему тоже нужна БД, он её получит через get_db)
    asyncio.create_task(start_webhook_server(application.bot))
    logger.info("🌐 Веб-сервер запущен как фоновая задача")

    logger.info("🚀 Бот запускается...")

    # Ручной запуск (без run_polling, чтобы избежать конфликта циклов)
    await application.initialize()
    await application.start()
    await application.updater.start_polling()

    try:
        # Бесконечное ожидание
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        logger.info("Получен сигнал завершения")
    finally:
        await application.updater.stop()
        await application.stop()
        await application.shutdown()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main_async())
    except KeyboardInterrupt:
        logger.info("Бот остановлен вручную")