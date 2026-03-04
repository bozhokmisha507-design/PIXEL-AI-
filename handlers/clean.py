import logging
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters
from database.db import get_db
from handlers.menu import get_main_menu_keyboard
from config import Config
import os
import shutil

logger = logging.getLogger(__name__)

async def clean_photos_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Очищает все загруженные фото пользователя."""
    if not update.effective_user:
        return
    user_id = update.effective_user.id

    db = await get_db()
    photo_paths = await db.get_user_photos(user_id, "input")

    if not photo_paths:
        await update.message.reply_text(
            "📭 У вас нет сохранённых фото.",
            reply_markup=get_main_menu_keyboard()
        )
        return

    # Удаляем файлы
    deleted_count = 0
    for path in photo_paths:
        try:
            if os.path.exists(path):
                os.remove(path)
                deleted_count += 1
        except Exception as e:
            logger.error(f"Ошибка удаления файла {path}: {e}")

    # Удаляем папку пользователя, если она пуста
    user_dir = os.path.join(Config.UPLOAD_DIR, str(user_id))
    try:
        if os.path.exists(user_dir) and not os.listdir(user_dir):
            os.rmdir(user_dir)
    except Exception as e:
        logger.error(f"Ошибка удаления папки {user_dir}: {e}")

    # Очищаем записи в БД
    await db.clear_user_photos(user_id)

    logger.info(f"Пользователь {user_id} очистил {deleted_count} фото")
    await update.message.reply_text(
        f"✅ Очищено {deleted_count} фото. Теперь можете загрузить новые.",
        reply_markup=get_main_menu_keyboard()
    )

clean_photos_handler = MessageHandler(filters.Text("🗑 Очистить селфи"), clean_photos_command)