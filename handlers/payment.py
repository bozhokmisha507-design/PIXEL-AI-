import uuid
import logging
import base64
import re
from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler
from yoomoney import Quickpay, Client
from config import Config
from handlers.menu import get_main_menu_keyboard
from services.aitunnel_service import AITunnelService
from database.db import get_db
from utils.helpers import send_photo_or_fallback

logger = logging.getLogger(__name__)

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
        quickpay = Quickpay(
            receiver=Config.YOOMONEY_WALLET,
            quickpay_form="shop",
            targets="Оплата генерации фото в PIXEL AI",
            paymentType="AC",
            sum=amount,
            label=label,
            successURL=f"https://t.me/bma3_bot?start=payment_{label}"
        )
        payment_url = quickpay.redirected_url
    except Exception as e:
        logger.error(f"Ошибка создания ссылки на оплату для user {user_id}: {e}", exc_info=True)
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
        quickpay = Quickpay(
            receiver=Config.YOOMONEY_WALLET,
            quickpay_form="shop",
            targets="Пакет 20 генераций в PIXEL AI",
            paymentType="AC",
            sum=amount,
            label=label,
            successURL=f"https://t.me/bma3_bot?start=tokens_{label}"
        )
        payment_url = quickpay.redirected_url
    except Exception as e:
        logger.error(f"Ошибка создания ссылки для пакета: {e}")
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
        quickpay = Quickpay(
            receiver=Config.YOOMONEY_WALLET,
            quickpay_form="shop",
            targets="Пакет 20 генераций в PIXEL AI",
            paymentType="AC",
            sum=amount,
            label=label,
            successURL=f"https://t.me/bma3_bot?start=tokens_{label}"
        )
        payment_url = quickpay.redirected_url
    except Exception as e:
        logger.error(f"Ошибка создания ссылки для пакета: {e}")
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
    """Команда для администратора: начисляет жетоны пользователю."""
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

# ---------- Фоновая проверка платежей (без преждевременной отметки processed) ----------
async def check_payments_job(context: ContextTypes.DEFAULT_TYPE):
    access_token = Config.YOOMONEY_ACCESS_TOKEN
    if not access_token:
        logger.error("YOOMONEY_ACCESS_TOKEN не задан")
        return

    db = await get_db()
    unprocessed = await db.get_unprocessed_orders()
    if not unprocessed:
        return

    client = Client(access_token)
    for order in unprocessed:
        label = order['label']
        user_id = order['user_id']

        try:
            history = client.operation_history(label=label)
            for operation in history.operations:
                if operation.status == 'success' and operation.label == label:
                    # НЕ помечаем обработанным здесь – это сделает generate_paid_photo после успеха
                    logger.info(f"Платёж подтверждён для label {label}, запускаем генерацию")

                    if label.startswith("tokens20_"):
                        await db.add_tokens(user_id, 20)
                        await context.bot.send_message(
                            chat_id=user_id,
                            text="✅ Вам начислено 20 жетонов! Используйте их при генерации."
                        )
                    elif label.startswith("couple_"):
                        order_data = await db.get_order_data(label)
                        if order_data:
                            from handlers.couple import generate_couple_photo_from_data
                            await generate_couple_photo_from_data(user_id, context.bot, db, order_data)
                        else:
                            logger.error(f"Нет данных для заказа {label}")
                            await context.bot.send_message(
                                chat_id=user_id,
                                text="✅ Оплата получена, но произошла ошибка при загрузке данных. Пожалуйста, начните заново с кнопки «👫 Парные фото»."
                            )
                    else:
                        await generate_paid_photo(
                            user_id,
                            context.bot,
                            db,
                            context,
                            label=label
                        )
                    break
        except Exception as e:
            logger.error(f"Ошибка при проверке заказа {label}: {e}")

# ---------- Обработка вебхука (без преждевременной отметки processed) ----------
async def handle_yoomoney_notification(data: dict, bot: Bot, db):
    logger.info(f"Обработка уведомления от ЮMoney: {data}")
    label = data.get('label')
    status = data.get('status')
    if not label or status != 'success':
        logger.warning(f"Уведомление не является успешным или нет label: {data}")
        return

    # НЕ помечаем обработанным здесь – это сделает generate_paid_photo после успеха

    if label.startswith("tokens20_"):
        try:
            user_id = int(label.split('_')[1])
            await db.add_tokens(user_id, 20)
            await bot.send_message(
                chat_id=user_id,
                text="✅ Вам начислено 20 жетонов! Используйте их при генерации."
            )
        except Exception as e:
            logger.error(f"Ошибка начисления жетонов: {e}")
    elif label.startswith("couple_"):
        try:
            user_id = int(label.split('_')[1])
            order_data = await db.get_order_data(label)
            if order_data:
                from handlers.couple import generate_couple_photo_from_data
                await generate_couple_photo_from_data(user_id, bot, db, order_data)
            else:
                logger.error(f"Нет данных для заказа {label}")
                await bot.send_message(
                    chat_id=user_id,
                    text="✅ Оплата получена, но произошла ошибка при загрузке данных. Пожалуйста, начните заново с кнопки «👫 Парные фото»."
                )
        except Exception as e:
            logger.error(f"Ошибка при обработке парной оплаты: {e}")
    else:
        try:
            user_id = int(label.split('_')[1])
            await generate_paid_photo(user_id, bot, db, context=None, label=label)
        except Exception as e:
            logger.error(f"Ошибка генерации: {e}")

# ---------- Генерация фото (вариант А: отмечаем processed только после успеха) ----------
async def generate_paid_photo(user_id: int, bot: Bot, db, context=None, label=None):
    """
    Генерация фото после оплаты.
    Отмечает заказ обработанным ТОЛЬКО после успешной генерации и отправки.
    """
    try:
        # 1. Если есть label – проверяем, не обработан ли уже заказ (чтобы не дублировать)
        if label:
            if await db.is_order_processed(label):
                logger.info(f"Заказ {label} уже обработан, пропускаем генерацию для user {user_id}")
                return
            logger.info(f"Начинаем генерацию для заказа {label}, user {user_id}")

        # 2. Получаем выбранный стиль
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

        # 3. Фото пользователя
        photo_paths = await db.get_user_photos(user_id, "input")
        if not photo_paths:
            await bot.send_message(
                chat_id=user_id,
                text="❌ Не найдены ваши фото. Сначала загрузите их через «📤 Загрузить фото»."
            )
            return

        # 4. Пол и модель
        gender = await db.get_user_gender(user_id)
        selected_model = 'gemini'
        if context is not None and context.user_data is not None:
            selected_model = context.user_data.get('selected_model', 'gemini')

        # 5. Выбираем сервис
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

        # 6. Генерация
        results = await service.generate_photos(
            user_photo_paths=photo_paths,
            style_key=style_key,
            num_images=1,
            gender=gender
        )

        # 7. Обработка результата
        if results:
            await bot.send_message(
                chat_id=user_id,
                text=f"✅ Оплата получена! Ваше фото в стиле {style['name']}:"
            )
            for image_data in results:
                await send_photo_or_fallback(bot, user_id, image_data)

            # Успех – помечаем заказ обработанным (если есть label)
            if label:
                await db.mark_order_processed(label)
                logger.info(f"Заказ {label} успешно выполнен, помечен как processed")

            # Очищаем временные данные
            if context is not None and context.user_data is not None:
                context.user_data.pop('selected_style', None)
                context.user_data.pop('selected_model', None)

            # Возвращаем главное меню
            await bot.send_message(
                chat_id=user_id,
                text="👇 *Главное меню*:",
                parse_mode='Markdown',
                reply_markup=get_main_menu_keyboard()
            )
        else:
            # Генерация не дала результатов – заказ остаётся pending
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
        # Заказ НЕ помечаем обработанным – можно будет повторить

# ---------- Экспорт обработчиков ----------
buy_handler = CommandHandler("buy", buy_command)
buy_tokens_handler = CommandHandler("buy20", buy_tokens_command)
buy_tokens_callback_handler = CallbackQueryHandler(buy_tokens_callback, pattern="^buy_tokens$")
add_tokens_handler = CommandHandler("add_tokens", add_tokens_command)