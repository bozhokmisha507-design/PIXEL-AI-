import os
import sys
import logging
import warnings
from telegram.warnings import PTBUserWarning

warnings.filterwarnings("ignore", category=PTBUserWarning)

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, CallbackQueryHandler
from telegram import Update

from config import Config
from database.db import Database

from handlers.start import start_handler, help_handler, handle_main_menu_buttons, gender_callback
from handlers.menu import menu_handler
from handlers.styles import styles_handler, show_styles_cb, style_selected_cb
from handlers.upload import upload_conversation
from handlers.generate import generate_handler
from handlers.clean import clean_photos_handler

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def post_init(application: Application) -> None:
    db = Database()
    await db.init()
    application.bot_data['db'] = db
    logger.info("✅ База данных инициализирована")
    
    try:
        bot_user = await application.bot.get_me()
        logger.info(f"🤖 Бот: @{bot_user.username}")
    except Exception as e:
        logger.warning(f"Не удалось получить информацию о боте: {e}")

def main():
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
    application.add_handler(generate_handler)
    
    # ConversationHandler для загрузки фото
    application.add_handler(upload_conversation)
    
    # Inline-обработчики для стилей
    application.add_handler(show_styles_cb)
    application.add_handler(style_selected_cb)
    
    # Обработчик выбора пола (inline-кнопки)
    application.add_handler(CallbackQueryHandler(gender_callback, pattern="^set_gender_"))
    
    # Кнопки главного меню
    application.add_handler(MessageHandler(
        filters.Text([
            "📤 Загрузить фото", 
            "📸 Генерировать", 
            "🖼️ Стили", 
            "❓ Помощь",
            "🗑 Очистить селфи", 
            "🏠 Главное меню"
        ]), 
        handle_main_menu_buttons
    ))
    
    # Обработчик очистки
    application.add_handler(clean_photos_handler)
    
    logger.info("🚀 Бот запущен...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()