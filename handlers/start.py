import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ConversationHandler
from config import Config
from database.db import get_db
from handlers.menu import get_main_menu_keyboard

logger = logging.getLogger(__name__)

WELCOME_MEDIA_FILE_ID = "BAACAgIAAxkBAAINK2m2ovEkC-IgPrVDWBdZEP3xnt2bAALjlQAC5UGxSQOUHY4Gm49-OgQ"

# Пробуем разные имена файла оферты
OFFER_FILE_NAMES = ["Публичная_оферта.pdf", "Публичная_оферта.pdf.pdf"]

async def send_welcome_message(chat_id: int, first_name: str, bot):
    welcome_text = (
        f"🎨 *Привет, {first_name}!*\n\n"
        f"Добро пожаловать в *AI Фотосессия Бот*! 📸\n\n"
        f"Вот что я умею:\n\n"
        f"👤 *Одиночные фото*\n"
        f"• Загрузи 2–5 своих селфи и выбери стиль\n"
        f"• Gemini (базовое) – 38₽ / 1 жетон\n"
        f"• GPT Image High (премиум) – 76₽ / 2 жетона\n"
        f"• 🍌 Nano Banana Pro (премиум-портрет) – 75₽ / 2 жетона\n\n"
        f"👫 *Парные фото*\n"
        f"• Загрузи фото мужчины и женщины, выбери стиль\n"
        f"• Nano Banana Pro – 75₽ / 2 жетона (максимальное качество)\n\n"
        f"🎬 *Видео*\n"
        f"• Создание видео по текстовому описанию\n"
        f"• Sora 2 Pro – 280₽ / 8 жетонов\n\n"
        f"💎 *Жетоны*\n"
        f"• Пакет 20 жетонов – 700₽\n"
        f"• Gemini = 1 жетон, GPT Image / Nano Banana = 2 жетона\n"
        f"• Видео = 8 жетонов\n\n"
        f"👇 Жми на кнопки ниже и пробуй!"
    )
    # Пробуем отправить как видео
    try:
        await bot.send_video(chat_id, video=WELCOME_MEDIA_FILE_ID, caption=welcome_text, parse_mode='Markdown', reply_markup=get_main_menu_keyboard())
    except Exception as e:
        # Если не получилось – пробуем как фото
        try:
            await bot.send_photo(chat_id, photo=WELCOME_MEDIA_FILE_ID, caption=welcome_text, parse_mode='Markdown', reply_markup=get_main_menu_keyboard())
        except Exception as e2:
            logger.error(f"Ошибка отправки приветствия: {e2}")
            await bot.send_message(chat_id, text=welcome_text, parse_mode='Markdown', reply_markup=get_main_menu_keyboard())

async def send_offer_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет файл оферты (ищет по списку возможных имён)."""
    file_content = None
    used_name = None
    for name in OFFER_FILE_NAMES:
        if os.path.exists(name):
            used_name = name
            break
    if used_name:
        with open(used_name, "rb") as f:
            file_content = f.read()
    if file_content:
        await update.message.reply_document(
            document=InputFile(used_name, filename="Публичная_оферта.pdf"),
            caption=(
                "📜 *Публичная оферта*\n\n"
                "Пожалуйста, ознакомьтесь с условиями. Для продолжения нажмите кнопку ниже."
            ),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Принимаю", callback_data="accept_offer")],
                [InlineKeyboardButton("❌ Не принимаю", callback_data="decline_offer")]
            ])
        )
    else:
        logger.error("Файл оферты не найден ни по одному из имён")
        await update.message.reply_text(
            "📜 *Публичная оферта*\n\n"
            "К сожалению, файл оферты временно недоступен. Пожалуйста, примите условия для продолжения.\n\n"
            "Нажимая кнопку, вы соглашаетесь с условиями.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Принимаю", callback_data="accept_offer")],
                [InlineKeyboardButton("❌ Не принимаю", callback_data="decline_offer")]
            ])
        )

async def offer_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    db = await get_db()

    if query.data == "accept_offer":
        await db.set_user_agreed_to_offer(user_id, True)
        await query.edit_message_text("✅ Спасибо! Вы приняли условия оферты.")
        await show_gender_selection(update, context)
    else:
        await query.edit_message_text(
            "❌ Вы не приняли оферту. К сожалению, без этого мы не можем предоставить услуги."
        )

async def show_gender_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🤵🏼‍♂️ Мужской", callback_data="set_gender_male")],
        [InlineKeyboardButton("🤵🏼‍♀️ Женский", callback_data="set_gender_female")]
    ]
    if update.callback_query:
        await update.callback_query.message.reply_text(
            "Пожалуйста, укажите ваш пол, чтобы мы могли подбирать стили правильно:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update.message.reply_text(
            "Пожалуйста, укажите ваш пол, чтобы мы могли подбирать стили правильно:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await send_welcome_message(update.effective_chat.id, user.first_name, context.bot)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args and context.args[0].startswith("payment_"):
        label = context.args[0].replace("payment_", "")
        user_id = update.effective_user.id
        db = await get_db()
        from handlers.robokassa import generate_paid_photo
        await generate_paid_photo(user_id, context.bot, db, context, label=label)
        return
    # Обработка других возвратов (couple_, custom_, video_) аналогично
    elif context.args and context.args[0].startswith("couple_"):
        # ... (оставьте как было)
        pass
    elif context.args and context.args[0].startswith("custom_"):
        pass
    elif context.args and context.args[0].startswith("video_"):
        pass

    user = update.effective_user
    user_id = user.id
    db = await get_db()
    await db.get_or_create_user(user_id, user.username, user.first_name)

    agreed = await db.get_user_agreed_to_offer(user_id)
    if agreed:
        await show_gender_selection(update, context)
    else:
        await send_offer_file(update, context)

async def gender_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query or not query.data:
        return
    await query.answer()
    gender = query.data.replace("set_gender_", "")
    user_id = update.effective_user.id
    db = await get_db()
    await db.set_user_gender(user_id, gender)
    await send_welcome_message(query.message.chat.id, update.effective_user.first_name, context.bot)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📖 *Подробная инструкция*\n\n"
        "**👤 Одиночные фото**\n"
        "1. Нажми «📤 Загрузить фото» и отправь 2–5 своих селфи.\n"
        "2. Нажми «🖼️ Стили» и выбери стиль.\n"
        "3. Выбери модель:\n"
        "   • 🚀 Gemini (базовое) – 38₽ / 1 жетон\n"
        "   • 💎 GPT Image High (премиум) – 76₽ / 2 жетона\n"
        "   • 🍌 Nano Banana Pro (премиум-портрет) – 75₽ / 2 жетона\n"
        "4. Оплати или используй жетоны.\n\n"
        "**👫 Парные фото**\n"
        "1. Нажми «👫 Парные фото» в главном меню.\n"
        "2. Загрузи фото мужчины, затем фото женщины.\n"
        "3. Выбери стиль.\n"
        "4. Оплати 75₽ или используй 2 жетона.\n\n"
        "**🎬 Видео**\n"
        "1. Нажми «🎬 Создать видео».\n"
        "2. Введи описание.\n"
        "3. Оплати 280₽ или используй 8 жетонов.\n\n"
        "**💎 Жетоны**\n"
        "• 20 жетонов = 700₽ (команда /buy20).\n"
        "• Баланс можно посмотреть по кнопке «💎 Мои жетоны».\n\n"
        "Если возникли вопросы, пишите support@example.com."
    )
    await update.message.reply_text(help_text, parse_mode='Markdown', reply_markup=get_main_menu_keyboard())

async def handle_main_menu_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "📤 Загрузить фото":
        from handlers.upload import upload_command
        await upload_command(update, context)
    elif text == "💳 Купить генерацию":
        from handlers.robokassa import buy_command
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
        await show_main_menu(update, context)
    elif text == "👫 Парные фото":
        from handlers.couple import couple_start
        await couple_start(update, context)
    elif text == "💎 Мои жетоны":
        from handlers.robokassa import my_tokens_command
        await my_tokens_command(update, context)
    elif text == "✍️ Свой промпт":
        from handlers.custom_prompt import custom_prompt_start
        await custom_prompt_start(update, context)
    elif text == "🎬 Создать видео":
        from handlers.video import video_start
        await video_start(update, context)

# Секретная команда /getlink (оставьте как есть)
WAITING_MEDIA = 1
AUTHORIZED_USERS = Config.ADMIN_IDS

async def secret_get_link_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in AUTHORIZED_USERS:
        await update.message.reply_text("Команда не найдена.")
        return ConversationHandler.END
    await update.message.reply_text("🔒 Отправьте фото, видео или GIF.")
    return WAITING_MEDIA

async def secret_get_link_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in AUTHORIZED_USERS:
        return ConversationHandler.END
    file_id = update.message.photo[-1].file_id
    file = await context.bot.get_file(file_id)
    file_url = f"https://api.telegram.org/file/bot{context.bot.token}/{file.file_path}"
    await update.message.reply_text(f"✅ File ID:\n`{file_id}`\n\n🔗 Ссылка:\n`{file_url}`", parse_mode='Markdown')
    return ConversationHandler.END

async def secret_get_link_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in AUTHORIZED_USERS:
        return ConversationHandler.END
    file_id = update.message.video.file_id
    file = await context.bot.get_file(file_id)
    file_url = f"https://api.telegram.org/file/bot{context.bot.token}/{file.file_path}"
    await update.message.reply_text(f"✅ File ID:\n`{file_id}`\n\n🔗 Ссылка:\n`{file_url}`", parse_mode='Markdown')
    return ConversationHandler.END

async def secret_get_link_animation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in AUTHORIZED_USERS:
        return ConversationHandler.END
    file_id = update.message.animation.file_id
    file = await context.bot.get_file(file_id)
    file_url = f"https://api.telegram.org/file/bot{context.bot.token}/{file.file_path}"
    await update.message.reply_text(f"✅ File ID:\n`{file_id}`\n\n🔗 Ссылка:\n`{file_url}`", parse_mode='Markdown')
    return ConversationHandler.END

async def secret_get_link_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отменено.")
    return ConversationHandler.END

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
    per_user=True, per_chat=True
)

# Экспорт
start_handler = CommandHandler("start", start_command)
help_handler = CommandHandler("help", help_command)