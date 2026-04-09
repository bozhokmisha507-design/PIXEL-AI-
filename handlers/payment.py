import uuid
import logging
from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler
from yookassa import Configuration, Payment
from config import Config
from handlers.menu import get_main_menu_keyboard
from services.aitunnel_service import AITunnelService
from database.db import get_db
from utils.helpers import send_photo_or_fallback

logger = logging.getLogger(__name__)

# ---------- Настройка ЮKassa ----------
Configuration.account_id = Config.YKASSA_SHOP_ID
Configuration.secret_key = Config.YKASSA_SECRET_KEY

# ---------- Команда /buy (обычная генерация) ----------
async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    selected_model = 'gemini'
    if context.user_data is not None:
        selected_model = context.user_data.get('selected_model', 'gemini')
    amount = Config.PRICE_PREMIUM if selected_model == 'gpt' else Config.PRICE_PER_GENERATION

    label = f"order_{user_id}_{uuid.uuid4().hex[:8]}"

    db = await get_db()
    await db.create_order(user_id, label, amount)

    try:
        payment = Payment.create({
            "amount": {"value": str(amount), "currency": "RUB"},
            "capture": True,   # <-- добавлено для автоматического списания
            "confirmation": {
                "type": "redirect",
                "return_url": f"https://t.me/bma3_bot?start=payment_{label}"
            },
            "description": f"Оплата генерации фото в PIXEL AI",
            "metadata": {"label": label, "user_id": user_id}
        }, uuid.uuid4())
        payment_url = payment.confirmation.confirmation_url
    except Exception as e:
        logger.error(f"Ошибка создания платежа для user {user_id}: {e}", exc_info=True)
        await update.message.reply_text(
            "❌ Не удалось создать ссылку на оплату. Попробуйте позже.",
            reply_markup=get_main_menu_keyboard()
        )
        return

    keyboard = [[InlineKeyboardButton("💳 Оплатить", url=payment_url)]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"✨ Стоимость генерации: {amount} руб.\n\n"
        f"👇 Нажми кнопку ниже для оплаты:",
        reply_markup=reply_markup
    )

# ---------- Команда /buy20 (пакет 20 жетонов) ----------
async def buy_tokens_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    label = f"tokens20_{user_id}_{uuid.uuid4().hex[:8]}"
    amount = Config.PRICE_20_TOKENS

    db = await get_db()
    await db.create_order(user_id, label, amount)

    try:
        payment = Payment.create({
            "amount": {"value": str(amount), "currency": "RUB"},
            "capture": True,   # <-- добавлено для автоматического списания
            "confirmation": {
                "type": "redirect",
                "return_url": f"https://t.me/bma3_bot?start=tokens_{label}"
            },
            "description": f"Пакет 20 жетонов в PIXEL AI",
            "metadata": {"label": label, "user_id": user_id}
        }, uuid.uuid4())
        payment_url = payment.confirmation.confirmation_url
    except Exception as e:
        logger.error(f"Ошибка создания платежа для пакета: {e}")
        await update.message.reply_text(
            "❌ Не удалось создать ссылку.",
            reply_markup=get_main_menu_keyboard()
        )
        return

    keyboard = [[InlineKeyboardButton(f"💳 Оплатить {amount}₽", url=payment_url)]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "✨ Купи пакет из 20 жетонов!\n"
        "Gemini = 1 жетон, GPT Image High = 2 жетона.\n"
        f"Стоимость пакета: {amount}₽",
        reply_markup=reply_markup
    )

# ---------- Универсальная функция отправки сообщения для покупки жетонов ----------
async def send_tokens_purchase_message(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    label = f"tokens20_{user_id}_{uuid.uuid4().hex[:8]}"
    amount = Config.PRICE_20_TOKENS
    db = await get_db()
    await db.create_order(user_id, label, amount)

    try:
        payment = Payment.create({
            "amount": {"value": str(amount), "currency": "RUB"},
            "capture": True,   # <-- добавлено для автоматического списания
            "confirmation": {
                "type": "redirect",
                "return_url": f"https://t.me/bma3_bot?start=tokens_{label}"
            },
            "description": f"Пакет 20 жетонов в PIXEL AI",
            "metadata": {"label": label, "user_id": user_id}
        }, uuid.uuid4())
        payment_url = payment.confirmation.confirmation_url
    except Exception as e:
        logger.error(f"Ошибка создания платежа для пакета: {e}")
        await context.bot.send_message(
            chat_id=user_id,
            text="❌ Не удалось создать ссылку.",
            reply_markup=get_main_menu_keyboard()
        )
        return

    keyboard = [[InlineKeyboardButton(f"💳 Оплатить {amount}₽", url=payment_url)]]
    await context.bot.send_message(
        chat_id=user_id,
        text="✨ Купи пакет из 20 жетонов!\n"
             "Gemini = 1 жетон, GPT Image High = 2 жетона.\n"
             f"Стоимость пакета: {amount}₽",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ---------- Callback для inline-кнопки "💎 Купить жетоны" ----------
async def buy_tokens_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    await send_tokens_purchase_message(user_id, context)

# ---------- Административная команда начисления жетонов ----------
async def add_tokens_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in Config.ADMIN_IDS:
        await update.message.reply_text("❌ У вас нет прав для этой команды.")
        return

    args = context.args
    if len(args) != 2:
        await update.message.reply_text(
            "❌ Использование: /add_tokens <user_id> <количество>\n"
            "Пример: /add_tokens 123456789 10"
        )
        return

    try:
        user_id = int(args[0])
        amount = int(args[1])
    except ValueError:
        await update.message.reply_text("❌ Неверные аргументы. user_id и количество должны быть числами.")
        return

    db = await get_db()
    await db.add_tokens(user_id, amount)
    await update.message.reply_text(f"✅ Пользователю {user_id} начислено {amount} жетонов.")

# ---------- Обработка вебхука ЮKassa ----------
async def process_yookassa_webhook(data: dict, bot: Bot, db):
    """Вызывается из webhook_server.py при получении уведомления от ЮKassa."""
    logger.info(f"Обработка уведомления от ЮKassa: {data}")
    event = data.get('event')
    if event != 'payment.succeeded':
        logger.info(f"Игнорируем событие {event}")
        return

    payment = data.get('object')
    if not payment:
        logger.warning("Нет объекта payment в уведомлении")
        return

    metadata = payment.get('metadata', {})
    label = metadata.get('label')
    if not label:
        logger.warning("Нет label в метаданных платежа")
        return

    if await db.is_order_processed(label):
        logger.info(f"Заказ {label} уже обработан, пропускаем")
        return

    user_id = int(metadata.get('user_id', 0))
    if not user_id:
        parts = label.split('_')
        if len(parts) > 1:
            try:
                user_id = int(parts[1])
            except:
                pass

    if not user_id:
        logger.error(f"Не удалось определить user_id для label {label}")
        return

    if label.startswith("tokens20_"):
        await db.add_tokens(user_id, 20)
        await bot.send_message(
            chat_id=user_id,
            text="✅ Вам начислено 20 жетонов! Используйте их при генерации."
        )
        await db.mark_order_processed(label)
    elif label.startswith("couple_"):
        order_data = await db.get_order_data(label)
        if order_data:
            from handlers.couple import generate_couple_photo_from_data
            await generate_couple_photo_from_data(user_id, bot, db, order_data)
            await db.mark_order_processed(label)
        else:
            logger.error(f"Нет данных для заказа {label}")
            await bot.send_message(
                chat_id=user_id,
                text="✅ Оплата получена, но произошла ошибка при загрузке данных. Пожалуйста, начните заново с кнопки «👫 Парные фото»."
            )
    elif label.startswith("custom_"):
        order_data = await db.get_order_data(label)
        if order_data:
            from handlers.custom_prompt import generate_custom_photo_from_data
            await generate_custom_photo_from_data(user_id, bot, db, order_data)
            await db.mark_order_processed(label)
        else:
            logger.error(f"Нет данных для заказа {label}")
            await bot.send_message(
                chat_id=user_id,
                text="✅ Оплата получена, но произошла ошибка. Начните заново с кнопки «✍️ Свой промпт»."
            )
    else:
        await generate_paid_photo(user_id, bot, db, context=None, label=label)

# ---------- Генерация фото (вариант А: отмечаем processed только после успеха) ----------
async def generate_paid_photo(user_id: int, bot: Bot, db, context=None, label=None):
    try:
        if label:
            if await db.is_order_processed(label):
                logger.info(f"Заказ {label} уже обработан, пропускаем генерацию для user {user_id}")
                return
            logger.info(f"Начинаем генерацию для заказа {label}, user {user_id}")

        style_key = await db.get_user_selected_style(user_id)
        if not style_key:
            await bot.send_message(
                chat_id=user_id,
                text="❌ Стиль не был выбран. Пожалуйста, сначала выберите стиль через меню «🖼️ Стили»."
            )
            from handlers.styles import show_styles_menu
            await show_styles_menu(user_id, context)
            return

        style = Config.STYLES.get(style_key)
        if not style:
            await bot.send_message(
                chat_id=user_id,
                text="❌ Выбранный стиль не найден. Попробуйте выбрать стиль заново."
            )
            return

        photo_paths = await db.get_user_photos(user_id, "input")
        if not photo_paths:
            await bot.send_message(
                chat_id=user_id,
                text="❌ Не найдены ваши фото. Сначала загрузите их через «📤 Загрузить фото»."
            )
            return

        gender = await db.get_user_gender(user_id)
        selected_model = 'gemini'
        if context is not None and context.user_data is not None:
            selected_model = context.user_data.get('selected_model', 'gemini')

        if selected_model == 'gemini':
            service = AITunnelService()
            logger.info(f"Generating with Gemini for user {user_id}")
        elif selected_model == 'gpt':
            service = AITunnelService(model_type="gpt", quality="high", size="1536x1024")
            logger.info(f"Generating with GPT Image High for user {user_id}")
        elif selected_model == 'nanobanana':
            service = AITunnelService(model_type="nanobanana")
            logger.info(f"Generating with Nano Banana Pro for user {user_id}")
        else:
            await bot.send_message(
                chat_id=user_id,
                text="❌ Неизвестная модель генерации."
            )
            return

        results = await service.generate_photos(
            user_photo_paths=photo_paths,
            style_key=style_key,
            num_images=1,
            gender=gender
        )

        if results:
            await bot.send_message(
                chat_id=user_id,
                text=f"✅ Оплата получена! Ваше фото в стиле {style['name']}:"
            )
            for image_data in results:
                await send_photo_or_fallback(bot, user_id, image_data)

            if label:
                await db.mark_order_processed(label)
                logger.info(f"Заказ {label} успешно выполнен, помечен как processed")

            if context is not None and context.user_data is not None:
                context.user_data.pop('selected_style', None)
                context.user_data.pop('selected_model', None)

            await bot.send_message(
                chat_id=user_id,
                text="👇 *Главное меню*:",
                parse_mode='Markdown',
                reply_markup=get_main_menu_keyboard()
            )
        else:
            logger.error(f"Генерация не дала результатов для user {user_id}, заказ {label} остаётся pending")
            await bot.send_message(
                chat_id=user_id,
                text="❌ Не удалось сгенерировать фото. Пожалуйста, попробуйте позже. "
                     "Если средства были списаны, они вернутся автоматически или обратитесь в поддержку."
            )
    except Exception as e:
        logger.error(f"Критическая ошибка в generate_paid_photo для user {user_id}: {e}", exc_info=True)
        await bot.send_message(
            chat_id=user_id,
            text="❌ Произошла внутренняя ошибка. Мы уже работаем над её исправлением.\n"
                 "Если средства были списаны, они вернутся автоматически."
        )

# ---------- Экспорт обработчиков ----------
buy_handler = CommandHandler("buy", buy_command)
buy_tokens_handler = CommandHandler("buy20", buy_tokens_command)
buy_tokens_callback_handler = CallbackQueryHandler(buy_tokens_callback, pattern="^buy_tokens$")
add_tokens_handler = CommandHandler("add_tokens", add_tokens_command)