import uuid
import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from config import Config
from handlers.menu import get_main_menu_keyboard
from database.db import get_db
from services.aitunnel_service import AITunnelService
from utils.helpers import send_photo_or_fallback

logger = logging.getLogger(__name__)

# Состояния диалога
PHOTO_MALE, PHOTO_FEMALE, STYLE_SELECT, CONFIRM = range(4)

# Цена парной генерации (можно вынести в config)
COUPLE_PRICE = 40
# Стоимость в жетонах
COUPLE_TOKEN_COST = 1

# Стили для пар
COUPLE_STYLES = {
    "couple_beach": "🏖️ Романтический пляж",
    "couple_wedding": "💒 Свадебное фото",
    "couple_dinner": "🕯️ Романтический ужин",
    "couple_city": "🌃 Вечерний город",
    "couple_forest": "🌲 Лесная прогулка",
}

# Промпты для пар (можно вынести в config, но для простоты оставим здесь)
COUPLE_PROMPTS = {
    "couple_beach": "A romantic couple on a beach at sunset, holding hands, photorealistic, 8k, faces clearly visible",
    "couple_wedding": "A wedding couple in a garden, bride in white dress, groom in tuxedo, photorealistic, 8k, faces clearly visible",
    "couple_dinner": "A couple having a romantic dinner in a cozy restaurant, candlelight, photorealistic, 8k, faces clearly visible",
    "couple_city": "A couple in love standing on a rooftop at night, city lights background, cinematic, photorealistic, 8k, faces clearly visible",
    "couple_forest": "A couple walking in a sunlit forest, holding hands, warm lighting, photorealistic, 8k, faces clearly visible",
}

async def couple_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало парной генерации – отправляем инструкцию и просим фото мужчины."""
    user_id = update.effective_user.id
    context.user_data['couple_photos'] = []  # здесь будем хранить пути к фото

    await update.message.reply_text(
        "👫 *Парная генерация*\n\n"
        "Сначала загрузи фото *мужчины* (чёткое селфи).\n"
        "После этого я попрошу фото женщины.\n\n"
        "Для отмены введите /cancel",
        parse_mode='Markdown'
    )
    return PHOTO_MALE

async def photo_male_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка фото мужчины."""
    if not update.message.photo:
        await update.message.reply_text("Пожалуйста, отправьте фото.")
        return PHOTO_MALE

    user_id = update.effective_user.id
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)

    user_dir = os.path.join(Config.UPLOAD_DIR, str(user_id))
    os.makedirs(user_dir, exist_ok=True)

    file_path = os.path.join(user_dir, f"couple_male_{uuid.uuid4().hex[:8]}.jpg")
    await file.download_to_drive(file_path)
    logger.info(f"Сохранено фото мужчины для парной генерации: {file_path}")

    context.user_data.setdefault('couple_photos', []).append(file_path)

    await update.message.reply_text("✅ Фото мужчины сохранено. Теперь отправьте фото *женщины*.")
    return PHOTO_FEMALE

async def photo_female_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка фото женщины."""
    if not update.message.photo:
        await update.message.reply_text("Пожалуйста, отправьте фото.")
        return PHOTO_FEMALE

    user_id = update.effective_user.id
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)

    user_dir = os.path.join(Config.UPLOAD_DIR, str(user_id))
    os.makedirs(user_dir, exist_ok=True)

    file_path = os.path.join(user_dir, f"couple_female_{uuid.uuid4().hex[:8]}.jpg")
    await file.download_to_drive(file_path)
    logger.info(f"Сохранено фото женщины для парной генерации: {file_path}")

    context.user_data['couple_photos'].append(file_path)

    # Показываем выбор стиля для пары
    keyboard = []
    for key, name in COUPLE_STYLES.items():
        keyboard.append([InlineKeyboardButton(name, callback_data=f"couple_style_{key}")])
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="couple_cancel")])

    await update.message.reply_text(
        "🎨 *Выберите стиль для вашего парного фото:*",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return STYLE_SELECT

async def style_selected_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора стиля – показываем варианты оплаты/жетонов."""
    query = update.callback_query
    await query.answer()

    style_key = query.data.replace("couple_style_", "")
    context.user_data['couple_style'] = style_key

    user_id = query.from_user.id
    db = await get_db()
    tokens = await db.get_user_tokens(user_id)

    # Формируем клавиатуру
    keyboard = []
    if tokens >= COUPLE_TOKEN_COST:
        keyboard.append([InlineKeyboardButton(f"💎 Использовать жетон (1 шт., у вас {tokens})", callback_data="couple_pay_tokens")])
    keyboard.append([InlineKeyboardButton(f"💳 Оплатить {COUPLE_PRICE}₽", callback_data="couple_pay_money")])
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="couple_cancel")])

    await query.edit_message_text(
        f"✅ Выбран стиль: {COUPLE_STYLES.get(style_key, style_key)}\n\n"
        f"Как хотите получить фото?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CONFIRM

async def pay_with_tokens_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Оплата жетонами."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    db = await get_db()

    if not await db.use_tokens(user_id, COUPLE_TOKEN_COST):
        await query.edit_message_text("❌ Недостаточно жетонов.")
        return ConversationHandler.END

    await query.edit_message_text("⏳ Генерация парного фото с использованием жетонов...")
    await generate_couple_photo(user_id, context.bot, db, context)
    return ConversationHandler.END

async def pay_with_money_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Оплата деньгами – создаём ссылку на оплату."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    label = f"couple_{user_id}_{uuid.uuid4().hex[:8]}"
    amount = COUPLE_PRICE

    db = await get_db()
    await db.create_order(user_id, label, amount)

    try:
        from yoomoney import Quickpay
        quickpay = Quickpay(
            receiver=Config.YOOMONEY_WALLET,
            quickpay_form="shop",
            targets="Парная генерация фото в PIXEL AI",
            paymentType="AC",
            sum=amount,
            label=label,
            successURL=f"https://t.me/bma3_bot?start=couple_{label}"
        )
        payment_url = quickpay.redirected_url
    except Exception as e:
        logger.error(f"Ошибка создания ссылки для парной генерации: {e}")
        await query.edit_message_text("❌ Не удалось создать ссылку. Попробуйте позже.")
        return ConversationHandler.END

    keyboard = [[InlineKeyboardButton(f"💳 Оплатить {amount}₽", url=payment_url)]]
    await query.edit_message_text(
        "✨ Для завершения оплаты нажмите кнопку ниже. После оплаты фото придёт автоматически.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    # Диалог завершаем, генерация будет по вебхуку/фоновой проверке
    return ConversationHandler.END

async def cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена операции."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("❌ Операция отменена.")
    # Очищаем временные файлы
    if 'couple_photos' in context.user_data:
        for path in context.user_data['couple_photos']:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except:
                pass
        del context.user_data['couple_photos']
    return ConversationHandler.END

async def generate_couple_photo(user_id: int, bot: Bot, db, context):
    """Генерация парного фото после оплаты (или использования жетонов)."""
    try:
        photo_paths = context.user_data.get('couple_photos', [])
        if len(photo_paths) != 2:
            await bot.send_message(user_id, "❌ Ошибка: не найдены оба фото.")
            return

        style_key = context.user_data.get('couple_style')
        if not style_key:
            await bot.send_message(user_id, "❌ Стиль не выбран.")
            return

        prompt = COUPLE_PROMPTS.get(style_key, "A romantic couple, photorealistic, 8k, faces clearly visible")

        # Используем AITunnelService с двумя референсами (требует доработки сервиса)
        aitunnel = AITunnelService()
        # Предполагаем, что у сервиса есть метод generate_couple_photo (см. изменения в aitunnel_service.py)
        results = await aitunnel.generate_couple_photo(
            male_photo_path=photo_paths[0],
            female_photo_path=photo_paths[1],
            prompt=prompt,
            num_images=1
        )

        if results:
            await bot.send_message(user_id, "✅ Ваше парное фото готово!")
            for image_data in results:
                await send_photo_or_fallback(bot, user_id, image_data)
        else:
            await bot.send_message(user_id, "❌ Не удалось сгенерировать фото. Попробуйте позже.")

        # Очищаем временные файлы
        for path in photo_paths:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except:
                pass
        del context.user_data['couple_photos']

        await bot.send_message(
            chat_id=user_id,
            text="👇 *Главное меню*:",
            parse_mode='Markdown',
            reply_markup=get_main_menu_keyboard()
        )
    except Exception as e:
        logger.error(f"Ошибка генерации парного фото: {e}", exc_info=True)
        await bot.send_message(user_id, "❌ Произошла ошибка. Мы уже работаем над её исправлением.")

# ConversationHandler
couple_conv = ConversationHandler(
    entry_points=[MessageHandler(filters.Text("👫 Парные фото"), couple_start)],
    states={
        PHOTO_MALE: [MessageHandler(filters.PHOTO, photo_male_handler)],
        PHOTO_FEMALE: [MessageHandler(filters.PHOTO, photo_female_handler)],
        STYLE_SELECT: [CallbackQueryHandler(style_selected_callback, pattern="^couple_style_")],
        CONFIRM: [
            CallbackQueryHandler(pay_with_tokens_callback, pattern="^couple_pay_tokens$"),
            CallbackQueryHandler(pay_with_money_callback, pattern="^couple_pay_money$"),
            CallbackQueryHandler(cancel_callback, pattern="^couple_cancel$"),
        ],
    },
    fallbacks=[CommandHandler("cancel", cancel_callback)],
    per_user=True,
    per_chat=True,
    name="couple_conversation"
)