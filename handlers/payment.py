import uuid
import logging
import base64
import re
import os
from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler
from yoomoney import Quickpay, Client
from config import Config
from handlers.menu import get_main_menu_keyboard
from services.aitunnel_service import AITunnelService
from database.db import get_db

logger = logging.getLogger(__name__)
aitunnel_service = AITunnelService()

# ---------- Команда /buy ----------
async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /buy – создаёт ссылку на оплату с уведомлением."""
    user_id = update.effective_user.id
    label = f"order_{user_id}_{uuid.uuid4().hex[:8]}"
    amount = Config.PRICE_PER_GENERATION

    # Сохраняем заказ в БД
    db = await get_db()
    await db.create_order(user_id, label, amount)

    

    quickpay = Quickpay(
        receiver=Config.YOOMONEY_WALLET,
        quickpay_form="shop",
        targets="Оплата генерации фото в PIXEL AI",
        paymentType="AC",  # оплата картой
        sum=amount,
        label=label,
        
    )
    payment_url = quickpay.redirected_url

    await update.message.reply_text(
        f"✨ Стоимость генерации: {amount} руб.\n\n"
        f"Ссылка для оплаты:\n{payment_url}\n\n"
        "После успешной оплаты фото придёт автоматически (обычно в течение минуты).",
        disable_web_page_preview=True,
        reply_markup=get_main_menu_keyboard()
    )

# ---------- Фоновая проверка платежей (запасной вариант) ----------
async def check_payments_job(context: ContextTypes.DEFAULT_TYPE):
    """Фоновая задача: проверяет неоплаченные заказы через API ЮMoney."""
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
                    # Помечаем заказ как обработанный
                    await db.mark_order_processed(label)
                    logger.info(f"Платёж подтверждён (фоновый) для user {user_id}, label {label}")

                    # Запускаем генерацию фото
                    await generate_paid_photo(
                        user_id,
                        context.bot,
                        db,
                        context  # передаём context для доступа к user_data (опционально)
                    )
                    break
        except Exception as e:
            logger.error(f"Ошибка при проверке заказа {label}: {e}")

# ---------- Функция для обработки уведомления от ЮMoney (вебхук) ----------
async def handle_yoomoney_notification(data: dict, bot: Bot, db):
    """
    Вызывается из вебхук-сервера при получении уведомления от ЮMoney.
    """
    logger.info(f"Обработка уведомления от ЮMoney: {data}")

    label = data.get('label')
    status = data.get('status')  # обычно 'success'

    if not label or status != 'success':
        logger.warning(f"Уведомление не является успешным или нет label: {data}")
        return

    # Помечаем заказ как оплаченный
    await db.mark_order_processed(label)

    # Извлекаем user_id из label (формат order_123456_abc)
    try:
        user_id = int(label.split('_')[1])
    except (IndexError, ValueError):
        logger.error(f"Не удалось извлечь user_id из label: {label}")
        return

    # Запускаем генерацию фото (context отсутствует)
    await generate_paid_photo(user_id, bot, db, context=None)

# ---------- Генерация фото после успешной оплаты ----------
async def generate_paid_photo(user_id: int, bot: Bot, db, context=None):
    """
    Генерирует фото после подтверждения оплаты.
    Если context передан, пытается взять стиль из user_data,
    иначе (при вебхуке) берёт стиль из БД.
    """
    # 1. Получаем выбранный стиль
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
        # Показываем меню стилей
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

    # 2. Получаем фото пользователя
    photo_paths = await db.get_user_photos(user_id, "input")
    if not photo_paths:
        await bot.send_message(
            chat_id=user_id,
            text="❌ Не найдены ваши фото. Сначала загрузите их через /upload."
        )
        return

    # 3. Получаем пол
    gender = await db.get_user_gender(user_id)

    # 4. Генерация
    aitunnel = AITunnelService()
    try:
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
            # Отправляем фото
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
    except Exception as e:
        logger.error(f"Ошибка генерации после оплаты: {e}", exc_info=True)
        await bot.send_message(
            chat_id=user_id,
            text="❌ Произошла ошибка при генерации. Мы уже работаем над этим."
        )

    # 5. Очищаем сохранённый стиль (если он был в user_data)
    if context and 'selected_style' in context.user_data:
        context.user_data.pop('selected_style')

    # 6. Возвращаем главное меню
    await bot.send_message(
        chat_id=user_id,
        text="👇 *Главное меню*:",
        parse_mode='Markdown',
        reply_markup=get_main_menu_keyboard()
    )

# ---------- Экспортируемые обработчики ----------
buy_handler = CommandHandler("buy", buy_command)