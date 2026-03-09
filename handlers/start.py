from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ConversationHandler
from database.db import get_db
from handlers.menu import get_main_menu_keyboard
import logging

logger = logging.getLogger(__name__)

# ⚠️ СЮДА ВСТАВЛЯЙТЕ ЛЮБОЙ FILE_ID (фото, видео, GIF)
WELCOME_MEDIA_FILE_ID = "AgACAgIAAxkBAAIImmmtLU3VKHz659Im62n7MzgSrT50AAKCFGsbLidoSTQu7GHRWg2NAQADAgADeQADOgQ"

async def send_welcome_message(chat_id: int, first_name: str, bot: Bot):
    """Отправляет приветственное медиа (фото/видео/GIF) с подписью и главным меню."""
    welcome_text = (
        f"🎨 *Привет, {first_name}!*\n\n"
        f"Добро пожаловать в *AI Фотосессия Бот*! 📸\n\n"
        f"Вот примеры того, что мы можем создать — множество стилей на основе одного лица:\n\n"
        f"1️⃣ Загрузи свои селфи (2-5 фото)\n"
        f"2️⃣ Выбери стиль\n"
        f"3️⃣ Получи готовую фотосессию!\n\n"
        f"👇 Жми на кнопки ниже и пробуй!"
    )

    try:
        # Получаем информацию о файле по file_id
        file = await bot.get_file(WELCOME_MEDIA_FILE_ID)
        file_path = file.file_path

        # Определяем тип по расширению файла
        if file_path:
            ext = file_path.split('.')[-1].lower() if '.' in file_path else ''
            if ext in ['jpg', 'jpeg', 'png', 'webp']:
                # Это фото
                await bot.send_photo(
                    chat_id=chat_id,
                    photo=WELCOME_MEDIA_FILE_ID,
                    caption=welcome_text,
                    parse_mode='Markdown',
                    reply_markup=get_main_menu_keyboard()
                )
            elif ext in ['mp4', 'mov', 'avi', 'mkv']:
                # Это видео
                await bot.send_video(
                    chat_id=chat_id,
                    video=WELCOME_MEDIA_FILE_ID,
                    caption=welcome_text,
                    parse_mode='Markdown',
                    reply_markup=get_main_menu_keyboard()
                )
            elif ext in ['gif']:
                # Это GIF (анимация)
                await bot.send_animation(
                    chat_id=chat_id,
                    animation=WELCOME_MEDIA_FILE_ID,
                    caption=welcome_text,
                    parse_mode='Markdown',
                    reply_markup=get_main_menu_keyboard()
                )
            else:
                # Неизвестный тип – пробуем отправить как фото
                await bot.send_photo(
                    chat_id=chat_id,
                    photo=WELCOME_MEDIA_FILE_ID,
                    caption=welcome_text,
                    parse_mode='Markdown',
                    reply_markup=get_main_menu_keyboard()
                )
        else:
            # Нет пути – пробуем как фото
            await bot.send_photo(
                chat_id=chat_id,
                photo=WELCOME_MEDIA_FILE_ID,
                caption=welcome_text,
                parse_mode='Markdown',
                reply_markup=get_main_menu_keyboard()
            )
    except Exception as e:
        logger.error(f"Ошибка отправки медиа: {e}")
        # Если не получилось, отправляем просто текст
        await bot.send_message(
            chat_id=chat_id,
            text=welcome_text,
            parse_mode='Markdown',
            reply_markup=get_main_menu_keyboard()
        )

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start."""
    if context.args and context.args[0].startswith("payment_"):
        label = context.args[0].replace("payment_", "")
        user_id = update.effective_user.id
        db = await get_db()
        from handlers.payment import generate_paid_photo
        await generate_paid_photo(user_id, context.bot, db, context, label=label)
        return

    if not update.message or not update.effective_user:
        return

    user = update.effective_user
    user_id = user.id
    first_name = user.first_name
    db = await get_db()
    await db.get_or_create_user(user_id, user.username, first_name)

    gender = await db.get_user_gender(user_id)
    if gender is None:
        keyboard = [
            [InlineKeyboardButton("🤵🏼‍♂️ Мужской", callback_data="set_gender_male")],
            [InlineKeyboardButton("🤵🏼‍♀️ Женский", callback_data="set_gender_female")]
        ]
        await update.message.reply_text(
            "Пожалуйста, укажите ваш пол, чтобы мы могли подбирать стили правильно:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    await send_welcome_message(update.effective_chat.id, first_name, context.bot)

async def gender_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is None or query.data is None:
        return
    await query.answer()
    gender = query.data.replace("set_gender_", "")

    if update.effective_user is None:
        return
    user_id = update.effective_user.id
    db = await get_db()
    await db.set_user_gender(user_id, gender)

    await send_welcome_message(query.message.chat.id, update.effective_user.first_name, context.bot)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    help_text = (
        "📖 *Инструкция*\n\n"
        "1. Загрузите свои селфи через кнопку «📤 Загрузить фото».\n"
        "2. Выберите стиль фотосессии через кнопку «🖼️ Стили».\n"
        "3. Для получения фото нажмите «💳 Купить генерацию» и оплатите.\n"
        "4. После оплаты фото придёт автоматически.\n\n"
        "Если возникли вопросы, пишите super.mike.4@ya.ru."
    )
    await update.message.reply_text(help_text, parse_mode='Markdown', reply_markup=get_main_menu_keyboard())

async def handle_main_menu_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user:
        return
    text = update.message.text

    if text == "📤 Загрузить фото":
        from handlers.upload import upload_command
        await upload_command(update, context)
    elif text == "💳 Купить генерацию":
        from handlers.payment import buy_command
        await buy_command(update, context)
    elif text == "🖼️ Стили":
        from handlers.styles import styles_command
        await styles_command(update, context)
    elif text == "❓ Помощь":
        await help_command(update, context)
    elif text == "🗑 Очистить селфи":
        from handlers.clean import clean_photos_command
        await clean_photos_command(update, context)
    elif text == "🏠 Главное меню":
        await start_command(update, context)

# ================== СЕКРЕТНАЯ КОМАНДА ДЛЯ ПОЛУЧЕНИЯ FILE_ID ==================
WAITING_MEDIA = 1

# Список разрешённых пользователей (укажите свой user_id)
AUTHORIZED_USERS = [955206480]  # замените на ваш реальный user_id

async def secret_get_link_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало секретной команды /getlink – проверка авторизации."""
    user_id = update.effective_user.id
    if user_id not in AUTHORIZED_USERS:
        await update.message.reply_text("Команда не найдена.")
        return ConversationHandler.END
    await update.message.reply_text(
        "🔒 Секретный режим получения ссылки.\n"
        "Отправьте мне фото, видео или GIF, и я пришлю вам его file_id и прямую ссылку.\n"
        "Для отмены введите /cancel."
    )
    return WAITING_MEDIA

async def secret_get_link_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка полученного фото."""
    user_id = update.effective_user.id
    if user_id not in AUTHORIZED_USERS:
        return ConversationHandler.END

    file_id = update.message.photo[-1].file_id
    file = await context.bot.get_file(file_id)
    file_url = f"https://api.telegram.org/file/bot{context.bot.token}/{file.file_path}"
    await update.message.reply_text(
        f"✅ **File ID (фото):**\n`{file_id}`\n\n🔗 **Прямая ссылка:**\n`{file_url}`",
        parse_mode='Markdown'
    )
    return ConversationHandler.END

async def secret_get_link_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка полученного видео."""
    user_id = update.effective_user.id
    if user_id not in AUTHORIZED_USERS:
        return ConversationHandler.END

    file_id = update.message.video.file_id
    file = await context.bot.get_file(file_id)
    file_url = f"https://api.telegram.org/file/bot{context.bot.token}/{file.file_path}"
    await update.message.reply_text(
        f"✅ **File ID (видео):**\n`{file_id}`\n\n🔗 **Прямая ссылка:**\n`{file_url}`",
        parse_mode='Markdown'
    )
    return ConversationHandler.END

async def secret_get_link_animation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка полученной анимации (GIF)."""
    user_id = update.effective_user.id
    if user_id not in AUTHORIZED_USERS:
        return ConversationHandler.END

    file_id = update.message.animation.file_id
    file = await context.bot.get_file(file_id)
    file_url = f"https://api.telegram.org/file/bot{context.bot.token}/{file.file_path}"
    await update.message.reply_text(
        f"✅ **File ID (GIF):**\n`{file_id}`\n\n🔗 **Прямая ссылка:**\n`{file_url}`",
        parse_mode='Markdown'
    )
    return ConversationHandler.END

async def secret_get_link_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена операции."""
    await update.message.reply_text("Операция отменена.")
    return ConversationHandler.END

# Создаём ConversationHandler с поддержкой фото, видео и анимаций
secret_link_conv = ConversationHandler(
    entry_points=[CommandHandler("getlink", secret_get_link_start)],
    states={
        WAITING_MEDIA: [
            MessageHandler(filters.PHOTO, secret_get_link_photo),
            MessageHandler(filters.VIDEO, secret_get_link_video),
            MessageHandler(filters.ANIMATION, secret_get_link_animation),
            CommandHandler("cancel", secret_get_link_cancel)
        ]
    },
    fallbacks=[CommandHandler("cancel", secret_get_link_cancel)],
    per_user=True,
    per_chat=True
)

# ================== ЭКСПОРТ ОБРАБОТЧИКОВ ==================
start_handler = CommandHandler("start", start_command)
help_handler = CommandHandler("help", help_command)