import os
import sys
import logging
import asyncio
import warnings
from datetime import time
from telegram.warnings import PTBUserWarning

warnings.filterwarnings("ignore", category=PTBUserWarning)

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, CallbackQueryHandler
from telegram import Update

from config import Config
from database.db import get_db, _db_instance

from handlers.start import start_handler, help_handler, handle_main_menu_buttons, gender_callback, secret_link_conv, offer_callback
from handlers.menu import menu_handler
from handlers.styles import styles_handler, show_styles_cb, style_selected_cb, model_selected_cb, use_token_cb, buy_generation_cb
from handlers.upload import upload_conversation
from handlers.clean import clean_photos_handler
from handlers.payment import (
    buy_handler, buy_tokens_handler, buy_tokens_callback_handler
)
from handlers.couple import couple_conv
from handlers.video import video_conv
from handlers.custom_prompt import custom_prompt_conv
from handlers.admin import add_tokens_conv, broadcast_handler

from webhook_server import start_webhook_server

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def clean_old_files_job(context):
    """Удаляет файлы старше 7 дней из UPLOAD_DIR"""
    from datetime import datetime, timedelta
    now = datetime.now()
    deleted = 0
    if not os.path.exists(Config.UPLOAD_DIR):
        logger.warning(f"Папка {Config.UPLOAD_DIR} не найдена")
        return
    for root, dirs, files in os.walk(Config.UPLOAD_DIR):
        for file in files:
            file_path = os.path.join(root, file)
            try:
                mtime = datetime.fromtimestamp(os.path.getmtime(file_path))
                if now - mtime > timedelta(days=7):
                    os.remove(file_path)
                    deleted += 1
            except Exception as e:
                logger.warning(f"Ошибка удаления {file_path}: {e}")
    if deleted:
        logger.info(f"🗑️ Удалено {deleted} старых файлов из {Config.UPLOAD_DIR}")

async def post_init(application: Application) -> None:
    try:
        bot_user = await application.bot.get_me()
        logger.info(f"🤖 Бот: @{bot_user.username}")
    except Exception as e:
        logger.warning(f"Не удалось получить информацию о боте: {e}")

async def main_async():
    if not Config.BOT_TOKEN:
        logger.error("❌ BOT_TOKEN не найден!")
        return

    Config.ensure_dirs()
    logger.info("📁 Папки созданы/проверены")

    try:
        db = await get_db()
        logger.info("✅ База данных PostgreSQL инициализирована")
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации базы данных: {e}")
        return

    application = Application.builder().token(Config.BOT_TOKEN).post_init(post_init).build()

    # Регистрация обработчиков
    application.add_handler(start_handler)
    application.add_handler(help_handler)
    application.add_handler(menu_handler)
    application.add_handler(styles_handler)
    application.add_handler(upload_conversation)
    application.add_handler(couple_conv)
    application.add_handler(video_conv)
    application.add_handler(custom_prompt_conv)
    application.add_handler(secret_link_conv)

    # Callback-обработчики
    application.add_handler(show_styles_cb)
    application.add_handler(style_selected_cb)
    application.add_handler(model_selected_cb)
    application.add_handler(use_token_cb)
    application.add_handler(buy_generation_cb)
    application.add_handler(CallbackQueryHandler(gender_callback, pattern="^set_gender_"))
    application.add_handler(buy_tokens_callback_handler)
    application.add_handler(CallbackQueryHandler(offer_callback, pattern="^(accept_offer|decline_offer)$"))

    # Команды
    application.add_handler(buy_handler)
    application.add_handler(buy_tokens_handler)
    application.add_handler(add_tokens_conv)
    application.add_handler(broadcast_handler)

    # Обработчик кнопок главного меню
    application.add_handler(MessageHandler(
        filters.Text([
            "📤 Загрузить фото",
            "💳 Купить генерацию",
            "🖼️ Стили",
            "❓ Помощь",
            "🗑 Очистить селфи",
            "🏠 Главное меню",
            "👫 Парные фото",
            "💎 Мои жетоны",
            "✍️ Свой промпт",
            "🎬 Создать видео"
        ]),
        handle_main_menu_buttons
    ))
    application.add_handler(clean_photos_handler)

    # Планируем ежедневную очистку старых фото в 3:00 ночи
    job_queue = application.job_queue
    if job_queue:
        job_queue.run_daily(clean_old_files_job, time=time(hour=3, minute=0))
        logger.info("🗑️ Запланирована ежедневная очистка старых фото в 03:00")
    else:
        logger.warning("Job queue не доступна, очистка фото не запланирована")

    asyncio.create_task(start_webhook_server(application.bot))
    logger.info("🌐 Веб-сервер запущен как фоновая задача")

    logger.info("🚀 Бот запускается...")

    await application.initialize()
    await application.start()
    await application.updater.start_polling()

    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        logger.info("Получен сигнал завершения")
    except KeyboardInterrupt:
        logger.info("Бот остановлен вручную")
    finally:
        logger.info("🛑 Останавливаем бота и закрываем соединения...")
        await application.updater.stop()
        await application.stop()
        await application.shutdown()
        if _db_instance:
            await _db_instance.close()
            logger.info("✅ Соединение с БД закрыто")

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main_async())
    except KeyboardInterrupt:
        logger.info("Бот остановлен вручную")
    finally:
        pending = asyncio.all_tasks(loop)
        for task in pending:
            task.cancel()
        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        loop.close()
        logger.info("✅ Все задачи завершены, цикл событий закрыт")