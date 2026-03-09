from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ConversationHandler
from database.db import get_db
from handlers.menu import get_main_menu_keyboard
from config import Config
import logging
import json

logger = logging.getLogger(__name__)

# ⚠️ ВАШ FILE_ID ДЛЯ ПРИВЕТСТВИЯ (можно менять на любой)
WELCOME_MEDIA_FILE_ID = "AgACAgIAAxkBAAIJrWmu461-3ELaxHLdZcKU79anbT35AAIEFWsbBDJ4SUnNG0WVV7UPAQADAgADeQADOgQ"

async def send_welcome_message(chat_id: int, first_name: str, bot: Bot):
    """Отправляет приветственное медиа (фото/видео/GIF) с подписью и главным меню."""
    welcome_text = (
        f"🎨 *Привет, {first_name}!*\n\n"
        f"Добро пожаловать в *AI Фотосессия Бот*! 📸\n\n"
        f"Вот что я умею:\n\n"
        f"👤 *Одиночные фото*\n"
        f"• Загрузи 2–5 своих селфи и выбери стиль\n"
        f"• Gemini (базовое) – 38₽\n"
        f"• GPT Image High (премиум) – 76₽\n\n"
        f"👫 *Парные фото*\n"
        f"• Загрузи фото мужчины и женщины, выбери стиль\n"
        f"• Стоимость: 40₽ или 1 жетон\n\n"
        f"💎 *Жетоны*\n"
        f"• Пакет 20 жетонов – 700₽\n"
        f"• Gemini = 1 жетон, GPT Image = 2 жетона, Парные фото = 1 жетон\n\n"
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

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args and context.args[0].startswith("payment_"):
        # Обычная генерация (уже работает)
        label = context.args[0].replace("payment_", "")
        user_id = update.effective_user.id
        db = await get_db()
        from handlers.payment import generate_paid_photo
        await generate_paid_photo(user_id, context.bot, db, context, label=label)
        return

    elif context.args and context.args[0].startswith("couple_"):
        # Парная генерация после оплаты
        label = context.args[0].replace("couple_", "")
        user_id = update.effective_user.id
        db = await get_db()

        # Проверяем, не обработан ли уже заказ
        if await db.is_order_processed(label):
            await update.message.reply_text(
                "✅ Ваше парное фото уже было сгенерировано.",
                reply_markup=get_main_menu_keyboard()
            )
            return

        # Помечаем заказ как обработанный
        await db.mark_order_processed(label)

        # Получаем данные заказа (пути к фото и выбранный стиль)
        # Для этого нужно расширить таблицу orders полем data (JSON)
        # Пример запроса: SELECT data FROM orders WHERE label = ?
        # Здесь предполагаем, что такая функция есть в db.py
        order_data = await db.get_order_data(label)
        if not order_data:
            # Если данных нет (старая версия) – просим начать диалог заново
            await update.message.reply_text(
                "✅ Оплата получена! Теперь нажмите «👫 Парные фото» в главном меню и пройдите шаги заново. Ваше фото будет создано без повторной оплаты.",
                reply_markup=get_main_menu_keyboard()
            )
            return

        # Извлекаем пути к фото и стиль
        male_photo = order_data.get('male_photo')
        female_photo = order_data.get('female_photo')
        style_key = order_data.get('style')

        if not male_photo or not female_photo or not style_key:
            await update.message.reply_text(
                "❌ Ошибка: неполные данные заказа. Попробуйте начать заново.",
                reply_markup=get_main_menu_keyboard()
            )
            return

        # Генерируем парное фото
        from services.aitunnel_service import AITunnelService
        from handlers.couple import COUPLE_PROMPTS  # словарь промптов
        aitunnel = AITunnelService()
        prompt = COUPLE_PROMPTS.get(style_key, "A romantic couple, photorealistic, 8k")
        results = await aitunnel.generate_couple_photo(
            male_photo_path=male_photo,
            female_photo_path=female_photo,
            prompt=prompt,
            num_images=1
        )

        if results:
            await update.message.reply_text("✅ Ваше парное фото готово!")
            for img_data in results:
                from utils.helpers import send_photo_or_fallback
                await send_photo_or_fallback(context.bot, user_id, img_data)
        else:
            await update.message.reply_text("❌ Не удалось сгенерировать фото. Попробуйте позже.")

        # Очищаем временные файлы
        import os
        for path in [male_photo, female_photo]:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except:
                pass

        await context.bot.send_message(
            chat_id=user_id,
            text="👇 *Главное меню*:",
            parse_mode='Markdown',
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
        "📖 *Подробная инструкция*\n\n"
        "**👤 Одиночные фото**\n"
        "1. Нажми «📤 Загрузить фото» и отправь 2–5 своих селфи.\n"
        "2. Нажми «🖼️ Стили» и выбери стиль.\n"
        "3. Выбери модель: Gemini (базовое, 38₽) или GPT Image High (премиум, 76₽).\n"
        "4. Оплати или используй жетон (если есть).\n\n"
        "**👫 Парные фото**\n"
        "1. Нажми «👫 Парные фото» в главном меню.\n"
        "2. Загрузи фото мужчины, затем фото женщины.\n"
        "3. Выбери стиль (пляж, свадьба, ужин и др.).\n"
        "4. Оплати 40₽ или используй 1 жетон.\n\n"
        "**💎 Жетоны**\n"
        "• 20 жетонов = 700₽ (команда /buy20).\n"
        "• Тратятся так: Gemini = 1 жетон, GPT Image = 2 жетона, Парные фото = 1 жетон.\n"
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
        await start_command(update, context)
    elif text == "👫 Парные фото":
        from handlers.couple import couple_start
        await couple_start(update, context)

# ================== СЕКРЕТНАЯ КОМАНДА ДЛЯ ПОЛУЧЕНИЯ FILE_ID ==================
WAITING_MEDIA = 1
AUTHORIZED_USERS = [955206480]  # ваш user_id

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