import os
import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, filters
from config import Config
from database.db import get_db
from handlers.menu import get_main_menu_keyboard

logger = logging.getLogger(__name__)

# Состояния для ConversationHandler
PHOTO = 1

async def upload_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начинает процесс загрузки фото"""
    user_id = update.effective_user.id
    db = await get_db()
    photo_count = await db.get_user_photo_count(user_id)

    if photo_count >= Config.MAX_PHOTOS:
        await update.message.reply_text(
            f"⚠️ У вас уже максимальное количество фото ({Config.MAX_PHOTOS}). "
            "Чтобы загрузить новые, сначала очистите старые через «🗑 Очистить селфи»."
        )
        return ConversationHandler.END

    # Создаём клавиатуру с кнопками Готово / Отмена
    keyboard = [
        [KeyboardButton("✅ Готово")],
        [KeyboardButton("❌ Отмена")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    await update.message.reply_text(
        f"📸 Отправь мне свои селфи (от {Config.MIN_PHOTOS} до {Config.MAX_PHOTOS} фото).\n\n"
        f"Сейчас загружено: {photo_count}\n"
        f"Рекомендуется {Config.RECOMMENDED_PHOTOS} фото для лучшего результата.\n\n"
        "Когда закончишь, нажми «✅ Готово».",
        reply_markup=reply_markup
    )
    return PHOTO

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает полученное фото"""
    if not update.message or not update.effective_user:
        return PHOTO

    user_id = update.effective_user.id
    db = await get_db()
    photo_count = await db.get_user_photo_count(user_id)

    if photo_count >= Config.MAX_PHOTOS:
        await update.message.reply_text(
            f"❌ Достигнут лимит ({Config.MAX_PHOTOS} фото). "
            "Чтобы добавить новые, сначала очисти старые через «🗑 Очистить селфи»."
        )
        return ConversationHandler.END

    # Получаем фото
    photo = update.message.photo[-1]  # берём самое большое фото
    file = await context.bot.get_file(photo.file_id)

    # Создаём папку для пользователя, если нет
    user_dir = os.path.join(Config.UPLOAD_DIR, str(user_id))
    os.makedirs(user_dir, exist_ok=True)

    # Сохраняем файл
    file_path = os.path.join(user_dir, f"photo_{photo_count + 1}.jpg")
    await file.download_to_drive(file_path)
    logger.info(f"Фото #{photo_count + 1} сохранено в {file_path}")

    # Сохраняем в БД
    await db.add_photo(user_id, photo.file_id, file_path, "input")

    # Обновляем счётчик
    new_count = await db.get_user_photo_count(user_id)
    remaining = Config.MAX_PHOTOS - new_count

    await update.message.reply_text(
        f"✅ Фото #{new_count} сохранено!\n"
        f"Загружено: {new_count}/{Config.MAX_PHOTOS}\n"
        f"Осталось: {remaining}"
    )

    return PHOTO

async def done_uploading(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Завершает загрузку фото (по кнопке или команде /done)"""
    user_id = update.effective_user.id
    db = await get_db()
    photo_count = await db.get_user_photo_count(user_id)

    if photo_count < Config.MIN_PHOTOS:
        await update.message.reply_text(
            f"⚠️ Нужно минимум {Config.MIN_PHOTOS} фото. Сейчас: {photo_count}\n\n"
            "Продолжай загружать."
        )
        return PHOTO

    await update.message.reply_text(
        f"✅ Загрузка завершена! У тебя {photo_count} фото.\n"
        "Теперь можешь выбрать стиль через «🖼️ Стили».",
        reply_markup=get_main_menu_keyboard()
    )
    return ConversationHandler.END

async def cancel_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отменяет загрузку (по кнопке или команде /cancel)"""
    await update.message.reply_text(
        "❌ Загрузка отменена.",
        reply_markup=get_main_menu_keyboard()
    )
    return ConversationHandler.END

# ConversationHandler
upload_conversation = ConversationHandler(
    entry_points=[
        CommandHandler("upload", upload_command),
        MessageHandler(filters.Text("📤 Загрузить фото"), upload_command)
    ],
    states={
        PHOTO: [
            MessageHandler(filters.PHOTO, handle_photo),
            # Обработчики для кнопок и команд
            MessageHandler(filters.Text("✅ Готово"), done_uploading),
            MessageHandler(filters.Text("❌ Отмена"), cancel_upload),
            CommandHandler("done", done_uploading),
            CommandHandler("cancel", cancel_upload),
        ]
    },
    fallbacks=[CommandHandler("cancel", cancel_upload)],
    per_message=False,
    per_user=True,
    per_chat=True
)