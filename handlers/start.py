from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ConversationHandler
from database.db import get_db
from handlers.menu import get_main_menu_keyboard
from config import Config
import logging
import json
import asyncio

logger = logging.getLogger(__name__)

# ⚠️ ВАШ FILE_ID ДЛЯ ПРИВЕТСТВИЯ (можно менять на любой)
WELCOME_MEDIA_FILE_ID = "BAACAgIAAxkBAAINK2m2ovEkC-IgPrVDWBdZEP3xnt2bAALjlQAC5UGxSQOUHY4Gm49-OgQ"

async def send_welcome_message(chat_id: int, first_name: str, bot: Bot):
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
        f"• Sora 2 Pro – 280₽ / 8 жетона\n\n"
        f"💎 *Жетоны*\n"
        f"• Пакет 20 жетонов – 700₽\n"
        f"• Gemini = 1 жетон, GPT Image / Nano Banana = 2 жетона\n"
        f"• Видео = 8 жетона\n\n"
        f"👇 Жми на кнопки ниже и пробуй!"
    )

    try:
        file = await bot.get_file(WELCOME_MEDIA_FILE_ID)
        file_path = file.file_path
        if file_path:
            ext = file_path.split('.')[-1].lower() if '.' in file_path else ''
            if ext in ['jpg', 'jpeg', 'png', 'webp']:
                await bot.send_photo(chat_id, photo=WELCOME_MEDIA_FILE_ID, caption=welcome_text, parse_mode='Markdown', reply_markup=get_main_menu_keyboard())
            elif ext in ['mp4', 'mov', 'avi', 'mkv']:
                await bot.send_video(chat_id, video=WELCOME_MEDIA_FILE_ID, caption=welcome_text, parse_mode='Markdown', reply_markup=get_main_menu_keyboard())
            elif ext in ['gif']:
                await bot.send_animation(chat_id, animation=WELCOME_MEDIA_FILE_ID, caption=welcome_text, parse_mode='Markdown', reply_markup=get_main_menu_keyboard())
            else:
                await bot.send_photo(chat_id, photo=WELCOME_MEDIA_FILE_ID, caption=welcome_text, parse_mode='Markdown', reply_markup=get_main_menu_keyboard())
        else:
            await bot.send_photo(chat_id, photo=WELCOME_MEDIA_FILE_ID, caption=welcome_text, parse_mode='Markdown', reply_markup=get_main_menu_keyboard())
    except Exception as e:
        logger.error(f"Ошибка отправки медиа: {e}")
        await bot.send_message(chat_id, text=welcome_text, parse_mode='Markdown', reply_markup=get_main_menu_keyboard())

# ===== НОВАЯ ФУНКЦИЯ: показать главное меню без запроса пола =====
async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Просто показывает главное меню, без проверки пола."""
    user = update.effective_user
    first_name = user.first_name
    await send_welcome_message(update.effective_chat.id, first_name, context.bot)

# ===== Функция для показа баланса жетонов =====
async def my_tokens_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    db = await get_db()
    tokens = await db.get_user_tokens(user_id)

    text = (
        f"💎 *Ваш баланс жетонов:* {tokens}\n\n"
        "• Gemini = 1 жетон\n"
        "• GPT Image High = 2 жетона\n"
        "• Nano Banana Pro = 2 жетона\n"
        "• Парные фото = 2 жетона\n"
        "• Видео Sora = 8 жетона"
    )
    keyboard = [[InlineKeyboardButton("💎 Купить 20 жетонов за 700₽", callback_data="buy_tokens")]]
    await update.message.reply_text(
        text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ===== Фоновая задача для парного фото =====
async def generate_couple_in_background(user_id: int, bot: Bot, db, label: str):
    try:
        await asyncio.sleep(2)
        order_data = await db.get_order_data(label)
        if not order_data:
            logger.warning(f"⚠️ Нет данных для заказа {label}, пропускаем фоновую генерацию")
            return
        from handlers.couple import generate_couple_photo_from_data
        await generate_couple_photo_from_data(user_id, bot, db, order_data)
    except Exception as e:
        logger.error(f"❌ Ошибка в фоновой генерации: {e}", exc_info=True)

# ===== Фоновая задача для кастомной генерации =====
async def generate_custom_in_background(user_id: int, bot: Bot, db, data: dict):
    try:
        from services.aitunnel_service import AITunnelService
        from utils.helpers import send_photo_or_fallback
        prompt = data.get('prompt')
        model = data.get('model', 'gemini')
        if not prompt:
            logger.error("Нет промпта в данных заказа")
            await bot.send_message(user_id, "❌ Не удалось найти промпт для генерации.")
            return
        photo_paths = await db.get_user_photos(user_id, "input")
        if not photo_paths:
            await bot.send_message(user_id, "❌ Не найдены ваши фото. Загрузите их через меню.")
            return
        gender = await db.get_user_gender(user_id)
        if gender == 'male':
            full_prompt = f"Photo of this man. {prompt}"
        elif gender == 'female':
            full_prompt = f"Photo of this woman. {prompt}"
        else:
            full_prompt = f"Photo of this person. {prompt}"
        full_prompt += " Landscape orientation, horizontal composition, aspect ratio 16:9, wide format."
        if model == 'gemini':
            service = AITunnelService()
        else:
            service = AITunnelService(model_type="gpt", quality="high", size="1024x1024")
        results = await service.generate_custom_photo(
            user_photo_paths=photo_paths,
            prompt=full_prompt,
            num_images=1
        )
        if results:
            await bot.send_message(user_id, "✅ Ваше фото готово!")
            for image_data in results:
                await send_photo_or_fallback(bot, user_id, image_data)
        else:
            await bot.send_message(user_id, "❌ Не удалось сгенерировать фото. Попробуйте позже.")
        await bot.send_message(
            chat_id=user_id,
            text="👇 *Главное меню*:",
            parse_mode='Markdown',
            reply_markup=get_main_menu_keyboard()
        )
    except Exception as e:
        logger.error(f"❌ Ошибка в фоновой кастомной генерации: {e}", exc_info=True)
        await bot.send_message(
            user_id,
            "❌ Произошла ошибка при генерации. Мы уже работаем над её исправлением."
        )

# ===== Фоновая задача для видео =====
async def generate_video_in_background(user_id: int, bot: Bot, db, label: str):
    """Генерирует видео в фоне по данным заказа."""
    try:
        await asyncio.sleep(2)
        order_data = await db.get_order_data(label)
        if not order_data:
            logger.warning(f"⚠️ Нет данных для заказа {label}, пропускаем фоновую генерацию видео")
            return
        from handlers.video import generate_video_from_data
        await generate_video_from_data(user_id, bot, db, order_data)
    except Exception as e:
        logger.error(f"❌ Ошибка в фоновой генерации видео: {e}", exc_info=True)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args and context.args[0].startswith("payment_"):
        label = context.args[0].replace("payment_", "")
        user_id = update.effective_user.id
        db = await get_db()
        from handlers.payment import generate_paid_photo
        await generate_paid_photo(user_id, context.bot, db, context, label=label)
        return

    elif context.args and context.args[0].startswith("couple_"):
        label = context.args[0].replace("couple_", "")
        user_id = update.effective_user.id
        db = await get_db()
        if await db.is_order_processed(label):
            await update.message.reply_text(
                "✅ Ваше парное фото уже было сгенерировано. Проверьте предыдущие сообщения.",
                reply_markup=get_main_menu_keyboard()
            )
            return
        order_data = await db.get_order_data(label)
        if order_data:
            await update.message.reply_text(
                "✅ Оплата получена! ⏳ *Начинаю генерацию вашего парного фото...*\n\n"
                "Это займёт примерно 20–30 секунд. Пожалуйста, подождите.",
                parse_mode='Markdown',
                reply_markup=get_main_menu_keyboard()
            )
            asyncio.create_task(
                generate_couple_in_background(user_id, context.bot, db, label)
            )
            return
        else:
            await update.message.reply_text(
                "✅ Оплата получена!",
                reply_markup=get_main_menu_keyboard()
            )
            return

    elif context.args and context.args[0].startswith("custom_"):
        label = context.args[0].replace("custom_", "")
        user_id = update.effective_user.id
        db = await get_db()
        if await db.is_order_processed(label):
            await update.message.reply_text(
                "✅ Ваше фото уже было сгенерировано. Проверьте предыдущие сообщения.",
                reply_markup=get_main_menu_keyboard()
            )
            return
        order_data = await db.get_order_data(label)
        if order_data:
            await update.message.reply_text(
                "✅ Оплата получена! ⏳ *Начинаю генерацию по вашему промпту...*\n\n"
                "Это займёт примерно 20–30 секунд. Пожалуйста, подождите.",
                parse_mode='Markdown',
                reply_markup=get_main_menu_keyboard()
            )
            asyncio.create_task(
                generate_custom_in_background(user_id, context.bot, db, order_data)
            )
            return
        else:
            await update.message.reply_text(
                "✅ Оплата получена!",
                reply_markup=get_main_menu_keyboard()
            )
            return

    # НОВАЯ ВЕТКА ДЛЯ ВИДЕО
    elif context.args and context.args[0].startswith("video_"):
        label = context.args[0].replace("video_", "")
        user_id = update.effective_user.id
        db = await get_db()

        if await db.is_order_processed(label):
            await update.message.reply_text(
                "✅ Ваше видео уже было сгенерировано. Проверьте предыдущие сообщения.",
                reply_markup=get_main_menu_keyboard()
            )
            return

        order_data = await db.get_order_data(label)
        if order_data:
            await update.message.reply_text(
                "✅ Оплата получена! ⏳ *Начинаю генерацию видео...*\n\n"
                "Это может занять до 2 минут. Пожалуйста, подождите.",
                parse_mode='Markdown',
                reply_markup=get_main_menu_keyboard()
            )
            asyncio.create_task(
                generate_video_in_background(user_id, context.bot, db, label)
            )
            return
        else:
            await update.message.reply_text(
                "✅ Оплата получена!",
                reply_markup=get_main_menu_keyboard()
            )
            return

    # Обычный запуск /start (без аргументов)
    if not update.message or not update.effective_user:
        return

    user = update.effective_user
    user_id = user.id
    first_name = user.first_name
    db = await get_db()
    await db.get_or_create_user(user_id, user.username, first_name)

    # Всегда показываем выбор пола
    keyboard = [
        [InlineKeyboardButton("🤵🏼‍♂️ Мужской", callback_data="set_gender_male")],
        [InlineKeyboardButton("🤵🏼‍♀️ Женский", callback_data="set_gender_female")]
    ]
    await update.message.reply_text(
        "Пожалуйста, укажите ваш пол, чтобы мы могли подбирать стили правильно:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return

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
        "3. Выбери стиль (пляж, свадьба, ужин и др.).\n"
        "4. Оплати 75₽ или используй 2 жетона.\n"
        "   *Генерация на Nano Banana Pro — лучшее качество для двух лиц*\n\n"
        "**🎬 Видео**\n"
        "1. Нажми «🎬 Создать видео» в главном меню.\n"
        "2. Введи текстовое описание видео.\n"
        "3. Оплати 280₽ или используй 8 жетона.\n"
        "4. Подожди 1–2 минуты, видео придёт автоматически.\n\n"
        "**💎 Жетоны**\n"
        "• 20 жетонов = 700₽ (команда /buy20).\n"
        "• Тратятся так:\n"
        "  - Gemini = 1 жетон\n"
        "  - GPT Image High = 2 жетона\n"
        "  - Nano Banana Pro = 2 жетона\n"
        "  - Парные фото = 2 жетона\n"
        "  - Видео = 3 жетона\n"
        "• Баланс можно посмотреть по кнопке «💎 Мои жетоны».\n\n"
        "**❓ Другие команды**\n"
        "• /start – главное меню\n"
        "• /help – эта инструкция\n"
        "• /buy20 – купить 20 жетонов\n"
        "• /styles – все доступные стили\n\n"
        "Если возникли вопросы, пишите super.mike.4@ya.ru."
    )
    await update.message.reply_text(
        help_text,
        parse_mode='Markdown',
        reply_markup=get_main_menu_keyboard()
    )

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
        # Вместо start_command используем show_main_menu (без запроса пола)
        await show_main_menu(update, context)
    elif text == "👫 Парные фото":
        from handlers.couple import couple_start
        await couple_start(update, context)
    elif text == "💎 Мои жетоны":
        await my_tokens_command(update, context)
    elif text == "✍️ Свой промпт":
        from handlers.custom_prompt import custom_prompt_start
        await custom_prompt_start(update, context)
    elif text == "🎬 Создать видео":
        from handlers.video import video_start
        await video_start(update, context)

# ================== СЕКРЕТНАЯ КОМАНДА ==================
WAITING_MEDIA = 1
AUTHORIZED_USERS = [955206480, 5063386675]

async def secret_get_link_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    await update.message.reply_text("Операция отменена.")
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
    per_user=True,
    per_chat=True
)

# ================== ЭКСПОРТ ОБРАБОТЧИКОВ ==================
start_handler = CommandHandler("start", start_command)
help_handler = CommandHandler("help", help_command)