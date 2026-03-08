from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from database.db import get_db
from handlers.menu import get_main_menu_keyboard
import logging

logger = logging.getLogger(__name__)

# ================== ОСНОВНАЯ ЛОГИКА (БЕЗ ФОТО) ==================
async def send_welcome_message(chat_id: int, first_name: str, bot: Bot):
    """Отправляет приветственное текстовое сообщение и главное меню."""
    welcome_text = (
        f"🎨 *Привет, {first_name}!*\n\n"
        f"Добро пожаловать в *AI Фотосессия Бот*! 📸\n\n"
        f"1️⃣ Загрузи свои селфи (2-5 фото)\n"
        f"2️⃣ Выбери стиль\n"
        f"3️⃣ Получи готовую фотосессию!\n\n"
        f"👇 Жми на кнопки ниже и пробуй!"
    )
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
            [InlineKeyboardButton("👨 Мужской", callback_data="set_gender_male")],
            [InlineKeyboardButton("👩 Женский", callback_data="set_gender_female")]
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

# ================== ВРЕМЕННЫЕ ОБРАБОТЧИКИ ДЛЯ ПОЛУЧЕНИЯ FILE_ID ==================
async def get_file_id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет подсказку для получения file_id."""
    await update.message.reply_text("📸 Отправьте мне фото, и я покажу его file_id.")

async def handle_photo_for_file_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает фото и возвращает file_id (без Markdown)."""
    if update.message.photo:
        # Берём самое большое фото (последнее в списке)
        file_id = update.message.photo[-1].file_id
        await update.message.reply_text(
            f"✅ FILE_ID получен:\n{file_id}\n\n"
            "Скопируйте эту строку и вставьте в переменную EXAMPLE_IMAGE_FILE_ID в handlers/start.py."
        )
    else:
        await update.message.reply_text("❌ Это не фото. Отправьте изображение.")

# ================== ЭКСПОРТ ОБРАБОТЧИКОВ ==================
start_handler = CommandHandler("start", start_command)
help_handler = CommandHandler("help", help_command)
# Временные обработчики (их нужно будет удалить после получения file_id)
temp_getid_handler = CommandHandler("getid", get_file_id_command)
temp_photo_handler = MessageHandler(filters.PHOTO, handle_photo_for_file_id)