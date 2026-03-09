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
from database.db import get_db

from handlers.start import start_handler, help_handler, handle_main_menu_buttons, gender_callback
from handlers.menu import menu_handler, tokens_handler
from handlers.styles import styles_handler, show_styles_cb, style_selected_cb, model_selected_cb, use_token_cb, buy_generation_cb
from handlers.upload import upload_conversation
from handlers.clean import clean_photos_handler
from handlers.payment import buy_handler, check_payments_job, buy_tokens_handler, buy_tokens_callback_handler

from webhook_server import start_webhook_server

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def post_init(application: Application) -> None:
    """Инициализация после создания приложения."""
    db = await get_db()
    application.bot_data['db'] = db
    logger.info("✅ База данных инициализирована")

    try:
        bot_user = await application.bot.get_me()
        logger.info(f"🤖 Бот: @{bot_user.username}")
    except Exception as e:
        logger.warning(f"Не удалось получить информацию о боте: {e}")

    # Запускаем веб-сервер как фоновую задачу после инициализации БД
    asyncio.create_task(start_webhook_server(application.bot))
    logger.info("🌐 Веб-сервер запущен как фоновая задача")

async def main_async():
    if not Config.BOT_TOKEN:
        logger.error("❌ BOT_TOKEN не найден! Проверьте .env файл")
        return

    Config.ensure_dirs()
    logger.info("📁 Папки созданы/проверены")

    application = Application.builder()\
        .token(Config.BOT_TOKEN)\
        .post_init(post_init)\
        .build()

    # Команды
    application.add_handler(start_handler)
    application.add_handler(help_handler)
    application.add_handler(menu_handler)
    application.add_handler(styles_handler)

    # ConversationHandler для загрузки фото
    application.add_handler(upload_conversation)

    # Inline-обработчики для стилей и выбора модели
    application.add_handler(show_styles_cb)
    application.add_handler(style_selected_cb)
    application.add_handler(model_selected_cb)
    # Колбэки для жетонов
    application.add_handler(use_token_cb)
    application.add_handler(buy_generation_cb)
    # Колбэк для покупки жетонов (inline-кнопка)
    application.add_handler(buy_tokens_callback_handler)

    # Обработчик выбора пола
    application.add_handler(CallbackQueryHandler(gender_callback, pattern="^set_gender_"))

    # Команда покупки одной генерации
    application.add_handler(buy_handler)
    # Команда для покупки пакета жетонов
    application.add_handler(buy_tokens_handler)

    # Обработчик кнопки "💎 Мои жетоны" (текстовая кнопка главного меню)
    application.add_handler(tokens_handler)

    # Кнопки главного меню (остальные текстовые кнопки)
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

    # Обработчик очистки фото
    application.add_handler(clean_photos_handler)

    # Фоновая задача проверки платежей (каждые 15 секунд)
    job_queue = application.job_queue
    job_queue.run_repeating(check_payments_job, interval=15, first=10)

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

def main():
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main_async())
    except KeyboardInterrupt:
        logger.info("Бот остановлен вручную")

if __name__ == "__main__":
    main()