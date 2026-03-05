from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler
from database.db import get_db
from handlers.menu import get_main_menu_keyboard
import logging

logger = logging.getLogger(__name__)

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

    db = await get_db()
    user = update.effective_user
    await db.get_or_create_user(user.id, user.username, user.first_name)

    gender = await db.get_user_gender(user.id)
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

    await show_welcome(update, context, user.first_name)

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

    await query.edit_message_text(
        f"✅ Пол сохранён: {'мужской' if gender == 'male' else 'женский'}.\n\n"
        "Теперь вы можете пользоваться ботом!"
    )
    await context.bot.send_message(
        chat_id=user_id,
        text="👇 *Главное меню*:",
        parse_mode='Markdown',
        reply_markup=get_main_menu_keyboard()
    )

async def show_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE, first_name: str):
    if update.message is None:
        return
    welcome_text = (
        f"🎨 *Привет, {first_name}!*\n\n"
        f"Добро пожаловать в *AI Фотосессия Бот*! 📸\n\n"
        f"1️⃣ Загрузи селфи (2-5 фото)\n"
        f"2️⃣ Выбери стиль\n"
        f"3️⃣ Получи фотосессию!\n\n"
        f"Команды: /upload, /buy, /styles, /help"
    )
    await update.message.reply_text(
        welcome_text,
        parse_mode='Markdown',
        reply_markup=get_main_menu_keyboard()
    )

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