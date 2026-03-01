import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, CommandHandler, MessageHandler,
    CallbackQueryHandler, ConversationHandler, filters
)
from services.storage import StorageService
from config import Config
from handlers.menu import get_main_menu_keyboard

logger = logging.getLogger(__name__)

UPLOADING = 1

async def upload_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user:
        return UPLOADING

    db = context.bot_data['db']
    user_id = update.effective_user.id
    await db.update_user_state(user_id, 'uploading')

    # Инициализация user_data
    if context.user_data is None:
        context.user_data = {}
    context.user_data['uploaded_count'] = 0
    context.user_data['photo_paths'] = []
    context.user_data['progress_message_id'] = None

    existing_count = await db.get_user_photo_count(user_id)

    text = (
        f"📸 *Загрузка селфи*\n\n"
        f"Отправляй мне свои фотографии по одной или несколько сразу.\n\n"
        f"*Требования к фото:*\n"
        f"✅ Чёткие, не размытые\n"
        f"✅ Хорошее освещение☀️\n"
        f"✅ Лицо видно полностью\n"
        f"✅ Разные ракурсы\n\n"
        f"*Количество:*\n"
        f"• Минимум: {Config.MIN_PHOTOS} фото\n"
        f"• Рекомендуется: {Config.RECOMMENDED_PHOTOS} фото\n"
        f"• Максимум: {Config.MAX_PHOTOS} фото\n"
    )

    if existing_count > 0:
        text += f"\n⚠️ У тебя уже загружено {existing_count} фото. Новые будут добавлены.\n"

    text += "\n📤 *Начинай отправлять фото!*"

    # ⚠️ Убрали inline-кнопки из первого сообщения
    sent = await update.message.reply_text(
        text,
        parse_mode='Markdown'
    )
    # Сохраняем ID этого сообщения, чтобы потом его можно было удалить (опционально)
    if context.user_data is not None:
        context.user_data['progress_message_id'] = sent.message_id

    return UPLOADING

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user:
        return UPLOADING

    user_id = update.effective_user.id
    logger.info(f"Получено фото от пользователя {user_id}")

    db = context.bot_data['db']
    photo = update.message.photo[-1]
    file_id = photo.file_id

    current_count = await db.get_user_photo_count(user_id)

    if current_count >= Config.MAX_PHOTOS:
        await update.message.reply_text(
            f"⚠️ Достигнут максимум ({Config.MAX_PHOTOS} фото). "
            f"Нажми «Готово» для продолжения."
        )
        return UPLOADING

    try:
        bot = update.get_bot()
        file_path = await StorageService.save_telegram_photo(
            bot, file_id, user_id, current_count + 1
        )

        await db.add_photo(user_id, file_id, file_path, "input")
        current_count += 1
        logger.info(f"Фото #{current_count} сохранено")

        # Создаём прогресс-бар
        filled = min(current_count, Config.RECOMMENDED_PHOTOS)
        empty = max(0, Config.RECOMMENDED_PHOTOS - current_count)
        progress_bar = "🟩" * filled + "⬜" * empty

        if current_count >= Config.MIN_PHOTOS:
            status_emoji = "✅"
            status_text = "Можно переходить к генерации!"
        else:
            status_emoji = "📸"
            remaining = Config.MIN_PHOTOS - current_count
            status_text = f"Нужно ещё минимум {remaining} фото"

        # В прогресс-сообщении добавляем все три кнопки: Готово, Удалить все селфи, Отмена
        keyboard = [
            [InlineKeyboardButton("✅ Готово", callback_data="done_uploading")],
            [InlineKeyboardButton("🗑 Удалить все селфи", callback_data="clear_photos")],
            [InlineKeyboardButton("❌ Отмена", callback_data="cancel_upload")]
        ]

        new_text = (
            f"{status_emoji} Фото #{current_count} загружено!\n\n"
            f"Прогресс: {current_count}/{Config.RECOMMENDED_PHOTOS}\n"
            f"[{progress_bar}]\n\n"
            f"{status_text}"
        )

        # Удаляем предыдущее сообщение с прогрессом (первое или предыдущее)
        progress_id = context.user_data.get('progress_message_id') if context.user_data else None
        if progress_id:
            try:
                await context.bot.delete_message(chat_id=user_id, message_id=progress_id)
            except Exception as e:
                logger.warning(f"Не удалось удалить предыдущее сообщение: {e}")

        # Отправляем новое сообщение с прогрессом и кнопками
        sent = await context.bot.send_message(
            chat_id=user_id,
            text=new_text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        if context.user_data is not None:
            context.user_data['progress_message_id'] = sent.message_id

    except Exception as e:
        logger.error(f"Ошибка при загрузке фото: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

    return UPLOADING

async def done_uploading_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is None or not update.effective_user:
        return ConversationHandler.END
    await query.answer()

    user_id = update.effective_user.id
    db = context.bot_data['db']
    count = await db.get_user_photo_count(user_id)

    if count < Config.MIN_PHOTOS:
        await query.edit_message_text(
            f"⚠️ Загружено только {count} фото.\n"
            f"Минимум нужно {Config.MIN_PHOTOS}.\n\n"
            f"Продолжай отправлять фотографии!"
        )
        return UPLOADING

    try:
        await query.delete_message()
    except Exception as e:
        logger.warning(f"Не удалось удалить сообщение: {e}")

    await db.update_user_state(user_id, 'ready_to_generate')

    # Сразу показываем меню стилей
    from handlers.styles import show_styles_menu
    await show_styles_menu(user_id, context)

    # Возвращаем главное меню с Reply-кнопками
    await context.bot.send_message(
        chat_id=user_id,
        text="👇 *Главное меню*:",
        parse_mode='Markdown',
        reply_markup=get_main_menu_keyboard()
    )

    return ConversationHandler.END

async def cancel_upload_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is None or not update.effective_user:
        return ConversationHandler.END
    await query.answer()

    user_id = update.effective_user.id
    db = context.bot_data['db']
    await db.update_user_state(user_id, 'idle')

    try:
        await query.delete_message()
    except Exception:
        pass

    await context.bot.send_message(
        chat_id=user_id,
        text="❌ *Загрузка отменена*\n\nИспользуй /upload чтобы начать заново.",
        parse_mode='Markdown',
        reply_markup=get_main_menu_keyboard()
    )

    return ConversationHandler.END

async def clear_photos_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is None or not update.effective_user:
        return UPLOADING
    await query.answer()

    user_id = update.effective_user.id
    db = context.bot_data['db']

    await db.clear_user_photos(user_id)
    StorageService.cleanup_user_uploads(user_id)

    new_text = "🗑 *Все фото удалены*\n\nОтправляй новые фотографии!"
    progress_id = context.user_data.get('progress_message_id') if context.user_data else None

    if progress_id:
        try:
            await context.bot.edit_message_text(
                chat_id=user_id,
                message_id=progress_id,
                text=new_text,
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.warning(f"Не удалось отредактировать сообщение: {e}")
            # Если не получилось отредактировать, отправляем новое и сохраняем его ID
            sent = await context.bot.send_message(
                chat_id=user_id,
                text=new_text,
                parse_mode='Markdown'
            )
            if context.user_data is not None:
                context.user_data['progress_message_id'] = sent.message_id
    else:
        # Если нет сообщения с прогрессом, просто отправляем новое
        sent = await context.bot.send_message(
            chat_id=user_id,
            text=new_text,
            parse_mode='Markdown'
        )
        if context.user_data is not None:
            context.user_data['progress_message_id'] = sent.message_id

    return UPLOADING

async def continue_upload_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is None or not update.effective_user:
        return UPLOADING
    await query.answer()

    user_id = update.effective_user.id
    db = context.bot_data['db']
    count = await db.get_user_photo_count(user_id)

    try:
        await query.delete_message()
    except Exception:
        pass

    filled = min(count, Config.RECOMMENDED_PHOTOS)
    empty = max(0, Config.RECOMMENDED_PHOTOS - count)
    progress_bar = "🟩" * filled + "⬜" * empty

    if count >= Config.MIN_PHOTOS:
        status_emoji = "✅"
        status_text = "Можно переходить к генерации!"
    else:
        status_emoji = "📸"
        remaining = Config.MIN_PHOTOS - count
        status_text = f"Нужно ещё минимум {remaining} фото"

    keyboard = [
        [InlineKeyboardButton("✅ Готово", callback_data="done_uploading")],
        [InlineKeyboardButton("🗑 Удалить все селфи", callback_data="clear_photos")],
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel_upload")]
    ]

    new_text = (
        f"{status_emoji} *Продолжай отправлять фото!*\n\n"
        f"Прогресс: {count}/{Config.RECOMMENDED_PHOTOS}\n"
        f"[{progress_bar}]\n\n"
        f"{status_text}"
    )

    sent = await context.bot.send_message(
        chat_id=user_id,
        text=new_text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    if context.user_data is not None:
        context.user_data['progress_message_id'] = sent.message_id

    return UPLOADING

upload_conversation = ConversationHandler(
    entry_points=[
        CommandHandler("upload", upload_command),
        MessageHandler(filters.Text(["📤 Загрузить фото"]), upload_command),
    ],
    states={
        UPLOADING: [
            MessageHandler(filters.PHOTO, handle_photo),
            CallbackQueryHandler(done_uploading_callback, pattern="^done_uploading$"),
            CallbackQueryHandler(clear_photos_callback, pattern="^clear_photos$"),
            CallbackQueryHandler(cancel_upload_callback, pattern="^cancel_upload$"),
            CallbackQueryHandler(continue_upload_callback, pattern="^continue_upload$"),
        ]
    },
    fallbacks=[
        CallbackQueryHandler(cancel_upload_callback, pattern="^cancel_upload$"),
    ],
    per_user=True,
    per_chat=True,
)