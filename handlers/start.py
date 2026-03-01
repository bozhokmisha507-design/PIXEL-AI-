from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler
from handlers.menu import get_main_menu_keyboard

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user:
        return

    db = context.bot_data['db']
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
    db = context.bot_data['db']
    await db.set_user_gender(user_id, gender)

    await query.edit_message_text(
        f"✅ Пол сохранён: {'мужской' if gender == 'male' else 'женский'}.\n\n"
        "Теперь вы можете пользоваться ботом!"
    )
    await context.bot.send_message(
        chat_id=user_id,
        text="👇 Главное меню:",
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
        f"Команды: /upload, /generate, /styles, /help"
    )
    await update.message.reply_text(
        welcome_text,
        parse_mode='Markdown',
        reply_markup=get_main_menu_keyboard()
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    help_text = "📖 Загрузи фото через /upload, затем /generate для создания фотосессии"
    await update.message.reply_text(help_text, reply_markup=get_main_menu_keyboard())

async def handle_main_menu_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user:
        return
    text = update.message.text
    
    if text == "📤 Загрузить фото":
        from handlers.upload import upload_command
        await upload_command(update, context)
    elif text == "📸 Генерировать":
        from handlers.generate import generate_command
        await generate_command(update, context)
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