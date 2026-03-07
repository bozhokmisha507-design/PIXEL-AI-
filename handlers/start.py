from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler
from database.db import get_db
from handlers.menu import get_main_menu_keyboard
import logging

logger = logging.getLogger(__name__)

# Прямая ссылка на ваш коллаж-пример
EXAMPLE_IMAGE_URL = "https://i.ibb.co/VcxMcYvp/812f44c18ad43d9a7c944520a6998044-1cf83d27-0e6b-49f0-a3a0-007ed2cdc503.png"

async def send_welcome_with_photo(chat_id: int, first_name: str, bot: Bot):
    """Отправляет приветственное фото с подписью и главным меню."""
    caption = (
        f"🎨 *Привет, {first_name}!*\n\n"
        f"Добро пожаловать в *AI Фотосессия Бот*! 📸\n\n"
        f"Вот примеры того, что мы можем создать — 8 разных стилей на основе одного лица:\n\n"
        f"1️⃣ Загрузи свои селфи (2-5 фото)\n"
        f"2️⃣ Выбери стиль\n"
        f"3️⃣ Получи готовую фотосессию!\n\n"
        f"👇 Жми на кнопки ниже и пробуй!"
    )
    await bot.send_photo(
        chat_id=chat_id,
        photo=EXAMPLE_IMAGE_URL,
        caption=caption,
        parse_mode='Markdown',
        reply_markup=get_main_menu_keyboard()
    )

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start."""
    # Проверяем, есть ли аргумент, начинающийся с "payment_"
    if context.args and context.args[0].startswith("payment_"):
        label = context.args[0].replace("payment_", "")
        user_id = update.effective_user.id
        db = await get_db()
        from handlers.payment import generate_paid_photo
        await generate_paid_photo(user_id, context.bot, db, context, label=label)
        return

    # Обычный запуск /start
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

    # Если пол уже выбран, отправляем приветствие с фото
    await send_welcome_with_photo(update.effective_chat.id, first_name, context.bot)

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

    # После сохранения пола отправляем приветствие с фото
    await send_welcome_with_photo(query.message.chat.id, update.effective_user.first_name, context.bot)

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

start_handler = CommandHandler("start", start_command)
help_handler = CommandHandler("help", help_command)