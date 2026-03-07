import os
import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, filters
from config import Config
from database.db import get_db
from handlers.menu import get_main_menu_keyboard

logger = logging.getLogger(__name__)

PHOTO = 1

async def upload_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # Проверяем лимит ДО старта загрузки
    db = await get_db()
    photo_count = await db.get_user_photo_count(user_id)
    context.user_data['photo_count'] = photo_count

    if photo_count >= Config.MAX_PHOTOS:
        await update.message.reply_text(
            f"⚠️ У вас уже максимальное количество фото ({Config.MAX_PHOTOS}). "
            "Чтобы загрузить новые, сначала очистите старые через «🗑 Очистить селфи».",
            reply_markup=get_main_menu_keyboard()
        )
        return ConversationHandler.END

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
    if not update.message or not update.effective_user:
        return PHOTO

    user_id = update.effective_user.id
    db = await get_db()
    photo_count = context.user_data.get('photo_count', 0)

    if photo_count >= Config.MAX_PHOTOS:
        await update.message.reply_text(
            f"❌ Достигнут лимит ({Config.MAX_PHOTOS} фото). "
            "Чтобы добавить новые, сначала очисти старые через «🗑 Очистить селфи».",
            reply_markup=get_main_menu_keyboard()
        )
        return ConversationHandler.END

    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)

    user_dir = os.path.join(Config.UPLOAD_DIR, str(user_id))
    os.makedirs(user_dir, exist_ok=True)

    file_path = os.path.join(user_dir, f"photo_{photo_count + 1}.jpg")
    await file.download_to_drive(file_path)
    logger.info(f"Фото #{photo_count + 1} сохранено в {file_path} (user {user_id})")

    await db.add_photo(user_id, photo.file_id, file_path, "input")

    new_count = await db.get_user_photo_count(user_id)
    context.user_data['photo_count'] = new_count
    remaining = Config.MAX_PHOTOS - new_count

    await update.message.reply_text(
        f"✅ Фото #{new_count} сохранено!\n"
        f"Загружено: {new_count}/{Config.MAX_PHOTOS}\n"
        f"Осталось: {remaining}"
    )
    return PHOTO

async def done_uploading(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    db = await get_db()
    photo_count = context.user_data.get('photo_count')
    if photo_count is None:
        photo_count = await db.get_user_photo_count(user_id)
        context.user_data['photo_count'] = photo_count

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
    await update.message.reply_text(
        "❌ Загрузка отменена.",
        reply_markup=get_main_menu_keyboard()
    )
    return ConversationHandler.END

upload_conversation = ConversationHandler(
    entry_points=[
        CommandHandler("upload", upload_command),
        MessageHandler(filters.Text("📤 Загрузить фото"), upload_command)
    ],
    states={
        PHOTO: [
            MessageHandler(filters.PHOTO, handle_photo),
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