from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters
from handlers.menu import get_main_menu_keyboard

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    if not update.message or not update.effective_user:
        return

    db = context.bot_data['db']
    user = update.effective_user
    await db.get_or_create_user(user.id, user.username, user.first_name)

    welcome_text = (
        f"🎨 *Привет, {user.first_name}!*\n\n"
        f"Добро пожаловать в *AI Фотосессия Бот*! 📸\n\n"
        f"Я помогу тебе создать потрясающие профессиональные "
        f"фотографии с помощью искусственного интеллекта.\n\n"
        f"🔹 *Как это работает:*\n\n"
        f"1️⃣ *Загрузи селфи* — отправь мне 5-20 своих фотографий\n"
        f"2️⃣ *Выбери стиль* — бизнес, fashion, casual, арт и др.\n"
        f"3️⃣ *Получи фотосессию* — 1 уникальное фото!\n\n"
        f"📌 *Команды:*\n"
        f"/upload — Загрузить селфи\n"
        f"/generate — Сгенерировать фотосессию\n"
        f"/styles — Посмотреть доступные стили\n"
        f"/clean — Очистить все селфи\n"
        f"/help — Помощь\n\n"
        f"Используй кнопки внизу для навигации! 👇"
    )

    await update.message.reply_text(
        welcome_text,
        parse_mode='Markdown',
        reply_markup=get_main_menu_keyboard()
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    if not update.message:
        return

    help_text = (
        "📖 *Подробная инструкция:*\n\n"
        "*📸 Этап 1: Загрузка фотографий*\n"
        "• Нажми кнопку «📤 Загрузить фото» внизу\n"
        "• Загрузи от 5 до 20 своих фотографий\n"
        "• Фото должны быть чёткими, с хорошим освещением\n"
        "• Используй разные ракурсы\n\n"
        "*🎨 Этап 2: Генерация*\n"
        "• Нажми кнопку «📸 Генерировать»\n"
        "• Выбери стиль из списка\n"
        "• Подожди 1-2 минуты\n"
        "• Получи уникальное фото!\n\n"
        "*🗑 Очистка фото*\n"
        "• Нажми «🗑 Очистить селфи» чтобы удалить все загруженные фото\n\n"
        "*💡 Советы:*\n"
        "• Загружай качественные фото\n"
        "• Показывай лицо полностью\n"
        "• Используй естественное освещение"
    )

    await update.message.reply_text(
        help_text,
        parse_mode='Markdown',
        reply_markup=get_main_menu_keyboard()
    )

async def handle_main_menu_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на кнопки главного меню"""
    text = update.message.text
    
    if text == "📤 Загрузить фото":
        from handlers.upload import upload_command
        # Запускаем загрузку фото
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