from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters
from handlers.menu import get_main_menu_keyboard
import logging

logger = logging.getLogger(__name__)

async def clean_photos_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Очистка всех загруженных селфи"""
    if not update.message or not update.effective_user:
        return

    user_id = update.effective_user.id
    db = context.bot_data['db']
    
    # Получаем количество фото до очистки
    count = await db.get_user_photo_count(user_id)
    
    if count == 0:
        await update.message.reply_text(
            "📭 У тебя нет загруженных селфи.",
            reply_markup=get_main_menu_keyboard()
        )
        return
    
    # Очищаем фото из базы данных
    await db.clear_user_photos(user_id)
    
    # Очищаем физические файлы (если есть функция)
    try:
        from services.storage import StorageService
        StorageService.cleanup_user_uploads(user_id)
    except:
        pass
    
    logger.info(f"Пользователь {user_id} очистил {count} фото")
    
    await update.message.reply_text(
        f"🗑 *Все {count} селфи удалены!*\n\n"
        f"Теперь ты можешь загрузить новые фото.",
        parse_mode='Markdown',
        reply_markup=get_main_menu_keyboard()
    )

# Обработчик для кнопки
clean_photos_handler = MessageHandler(filters.Text("🗑 Очистить селфи"), clean_photos_command)