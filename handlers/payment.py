import uuid
import logging
import base64
import re
from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler
from yoomoney import Quickpay, Client
from config import Config
from handlers.menu import get_main_menu_keyboard
from services.aitunnel_service import AITunnelService
from database.db import get_db
from utils.helpers import send_photo_or_fallback

logger = logging.getLogger(__name__)

# ---------- Команда /buy ----------
async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # Определяем выбранную модель и цену
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

# ---------- Фоновая проверка платежей ----------
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
                    logger.info(f"Платёж подтверждён (фоновый) для user {user_id}, label {label}")
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

# ---------- Обработка вебхука ----------
async def handle_yoomoney_notification(data: dict, bot: Bot, db):
    logger.info(f"Обработка уведомления от ЮMoney: {data}")
    label = data.get('label')
    status = data.get('status')
    if not label or status != 'success':
        logger.warning(f"Уведомление не является успешным или нет label: {data}")
        return
    try:
        user_id = int(label.split('_')[1])
    except (IndexError, ValueError):
        logger.error(f"Не удалось извлечь user_id из label: {label}")
        return
    await generate_paid_photo(user_id, bot, db, context=None, label=label)

# ---------- Генерация фото ----------
async def generate_paid_photo(user_id: int, bot: Bot, db, context=None, label=None):
    try:
        if label:
            if not await db.try_mark_order_processed(label):
                logger.info(f"Заказ {label} уже обработан, пропускаем генерацию для user {user_id}")
                return
            logger.info(f"Заказ {label} зарезервирован для генерации для user {user_id}")

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
                text="❌ Не найдены ваши фото. Сначала загрузите их через /upload."
            )
            return

        gender = await db.get_user_gender(user_id)

        # 🔥 Безопасное получение выбранной модели
        selected_model = 'gemini'
        if context is not None and context.user_data is not None:
            selected_model = context.user_data.get('selected_model', 'gemini')

        if selected_model == 'gemini':
            service = AITunnelService()
            logger.info(f"Generating with Gemini for user {user_id}")
        else:
            service = AITunnelService(model_type="gpt", quality="high", size="1024x1024")
            logger.info(f"Generating with GPT Image High for user {user_id}")

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
        else:
            await bot.send_message(
                chat_id=user_id,
                text="❌ Не удалось сгенерировать фото. Попробуйте позже."
            )

        # Очищаем user_data, если есть
        if context is not None and context.user_data is not None:
            context.user_data.pop('selected_style', None)
            context.user_data.pop('selected_model', None)

        await bot.send_message(
            chat_id=user_id,
            text="👇 *Главное меню*:",
            parse_mode='Markdown',
            reply_markup=get_main_menu_keyboard()
        )

    except Exception as e:
        logger.error(f"Критическая ошибка в generate_paid_photo для user {user_id}: {e}", exc_info=True)
        await bot.send_message(
            chat_id=user_id,
            text="❌ Произошла внутренняя ошибка. Мы уже работаем над её исправлением."
        )

buy_handler = CommandHandler("buy", buy_command)