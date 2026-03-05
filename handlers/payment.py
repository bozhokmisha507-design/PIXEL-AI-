import uuid
import logging
import base64
import re
from telegram import Update, Bot
from telegram.ext import ContextTypes, CommandHandler
from yoomoney import Quickpay, Client
from config import Config
from handlers.menu import get_main_menu_keyboard
from services.aitunnel_service import AITunnelService
from database.db import get_db

logger = logging.getLogger(__name__)
aitunnel_service = AITunnelService()

# ---------- Команда /buy ----------
async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /buy – создаёт ссылку на оплату с successURL, содержащим label."""
    user_id = update.effective_user.id
    label = f"order_{user_id}_{uuid.uuid4().hex[:8]}"
    amount = Config.PRICE_PER_GENERATION

    db = await get_db()
    await db.create_order(user_id, label, amount)

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

    await update.message.reply_text(
        f"✨ Стоимость генерации: {amount} руб.\n\n"
        f"Ссылка для оплаты:\n{payment_url}\n\n"
        "После успешной оплаты фото придёт автоматически (обычно в течение минуты).",
        disable_web_page_preview=True,
        reply_markup=get_main_menu_keyboard()
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
    """Генерирует фото после подтверждения оплаты. Гарантирует, что заказ будет обработан только один раз."""
    try:
        # Если передан label, пытаемся атомарно пометить заказ как обработанный
        if label:
            if not await db.try_mark_order_processed(label):
                logger.info(f"Заказ {label} уже обработан, пропускаем генерацию")
                return
            logger.info(f"Заказ {label} зарезервирован для генерации")

        # --- Получение стиля ---
        style_key = None
        if context and 'selected_style' in context.user_data:
            style_key = context.user_data['selected_style']
        else:
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

        # --- Получение фото ---
        photo_paths = await db.get_user_photos(user_id, "input")
        if not photo_paths:
            await bot.send_message(
                chat_id=user_id,
                text="❌ Не найдены ваши фото. Сначала загрузите их через /upload."
            )
            return

        gender = await db.get_user_gender(user_id)
        aitunnel = AITunnelService()

        # Генерация
        results = await aitunnel.generate_photos(
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
                try:
                    if image_data.startswith('data:image'):
                        base64_str = re.sub('^data:image/.+;base64,', '', image_data)
                        image_bytes = base64.b64decode(base64_str)
                        await bot.send_photo(chat_id=user_id, photo=image_bytes)
                    elif image_data.startswith('http'):
                        await bot.send_photo(chat_id=user_id, photo=image_data)
                    else:
                        await bot.send_message(chat_id=user_id, text=image_data)
                except Exception as e:
                    logger.error(f"Ошибка отправки фото: {e}")
        else:
            await bot.send_message(
                chat_id=user_id,
                text="❌ Не удалось сгенерировать фото. Попробуйте позже."
            )

        # Очищаем выбранный стиль из user_data (если есть)
        if context and 'selected_style' in context.user_data:
            context.user_data.pop('selected_style')

        # Возвращаем главное меню
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

# ---------- Экспортируемый обработчик ----------
buy_handler = CommandHandler("buy", buy_command)