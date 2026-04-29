import uuid
import logging
from decimal import Decimal
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

# ---------- Команда /buy (одиночная генерация) ----------
async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    selected_model = context.user_data.get('selected_model', 'gemini')
    style_key = context.user_data.get('selected_style')
    if not style_key:
        await update.message.reply_text(
            "❌ Сначала выберите стиль через меню «🖼️ Стили».",
            reply_markup=get_main_menu_keyboard()
        )
        return

    if selected_model == 'gpt':
        amount = Config.PRICE_PREMIUM
    elif selected_model == 'nanobanana':
        amount = Config.PRICE_NANOBANANA
    else:
        amount = Config.PRICE_PER_GENERATION

    label = f"single_{user_id}_{uuid.uuid4().hex[:8]}"
    order_data = {
        'selected_model': selected_model,
        'style_key': style_key,
        'user_id': user_id
    }

    db = await get_db()
    await db.create_order(user_id, label, amount, data=order_data)

    try:
        payment = Payment.create({
            "amount": {"value": str(amount), "currency": "RUB"},
            "capture": True,
            "confirmation": {
                "type": "redirect",
                "return_url": f"https://t.me/bma3_bot?start=payment_{label}"
            },
            "description": f"Оплата генерации фото в PIXEL AI",
            "metadata": {"label": label, "user_id": user_id}
        }, uuid.uuid4())
        payment_id = payment.id
        await db.update_order_payment_id(label, payment_id)
        payment_url = payment.confirmation.confirmation_url
    except Exception as e:
        logger.error(f"Ошибка создания платежа для user {user_id}: {e}", exc_info=True)
        await update.message.reply_text(
            "❌ Не удалось создать ссылку на оплату. Попробуйте позже.",
            reply_markup=get_main_menu_keyboard()
        )
        return

    keyboard = [[InlineKeyboardButton("💳 Оплатить", url=payment_url)]]
    await update.message.reply_text(
        f"✨ Стоимость генерации: {amount} руб.\n\n👇 Нажмите кнопку ниже для оплаты:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ---------- Команда /buy20 (пакет жетонов) ----------
async def buy_tokens_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    label = f"tokens20_{user_id}_{uuid.uuid4().hex[:8]}"
    amount = Config.PRICE_20_TOKENS

    db = await get_db()
    await db.create_order(user_id, label, amount, data={'token_pack': 20})

    try:
        payment = Payment.create({
            "amount": {"value": str(amount), "currency": "RUB"},
            "capture": True,
            "confirmation": {
                "type": "redirect",
                "return_url": f"https://t.me/bma3_bot?start=tokens_{label}"
            },
            "description": f"Пакет 20 жетонов в PIXEL AI",
            "metadata": {"label": label, "user_id": user_id}
        }, uuid.uuid4())
        payment_id = payment.id
        await db.update_order_payment_id(label, payment_id)
        payment_url = payment.confirmation.confirmation_url
    except Exception as e:
        logger.error(f"Ошибка создания платежа для пакета: {e}")
        await update.message.reply_text(
            "❌ Не удалось создать ссылку.",
            reply_markup=get_main_menu_keyboard()
        )
        return

    keyboard = [[InlineKeyboardButton(f"💳 Оплатить {amount}₽", url=payment_url)]]
    await update.message.reply_text(
        f"✨ Купи пакет из 20 жетонов!\nСтоимость пакета: {amount}₽",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ---------- Универсальная функция для покупки жетонов (через callback) ----------
async def send_tokens_purchase_message(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    label = f"tokens20_{user_id}_{uuid.uuid4().hex[:8]}"
    amount = Config.PRICE_20_TOKENS
    db = await get_db()
    await db.create_order(user_id, label, amount, data={'token_pack': 20})

    try:
        payment = Payment.create({
            "amount": {"value": str(amount), "currency": "RUB"},
            "capture": True,
            "confirmation": {
                "type": "redirect",
                "return_url": f"https://t.me/bma3_bot?start=tokens_{label}"
            },
            "description": f"Пакет 20 жетонов в PIXEL AI",
            "metadata": {"label": label, "user_id": user_id}
        }, uuid.uuid4())
        payment_id = payment.id
        await db.update_order_payment_id(label, payment_id)
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
        text=f"✨ Купи пакет из 20 жетонов!\nСтоимость пакета: {amount}₽",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ---------- Callback для inline-кнопки "💎 Купить жетоны" ----------
async def buy_tokens_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    await send_tokens_purchase_message(user_id, context)

# ---------- Показать баланс жетонов ----------
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
        "• Видео Sora 2 Pro = 8 жетонов"
    )
    keyboard = [[InlineKeyboardButton("💎 Купить 20 жетонов за 700₽", callback_data="buy_tokens")]]
    await update.message.reply_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))

# ---------- Генерация фото после оплаты (для одиночных фото) ----------
async def generate_paid_photo(user_id: int, bot: Bot, db, context=None, label=None, order_data=None):
    try:
        if label:
            if await db.is_order_processed(label):
                logger.info(f"Заказ {label} уже обработан, пропускаем")
                return
            if order_data is None:
                order_data = await db.get_order_data(label)
            logger.info(f"Генерация для заказа {label}, user {user_id}")

        selected_model = 'gemini'
        style_key = None
        if order_data:
            selected_model = order_data.get('selected_model', 'gemini')
            style_key = order_data.get('style_key')
        elif context and context.user_data:
            selected_model = context.user_data.get('selected_model', 'gemini')
            style_key = context.user_data.get('selected_style')

        if not style_key:
            style_key = await db.get_user_selected_style(user_id)
            if not style_key:
                await bot.send_message(
                    user_id,
                    text="❌ Стиль не был выбран. Пожалуйста, сначала выберите стиль через меню «🖼️ Стили»."
                )
                from handlers.styles import show_styles_menu
                await show_styles_menu(user_id, context)
                return

        style = Config.STYLES.get(style_key)
        if not style:
            await bot.send_message(user_id, "❌ Выбранный стиль не найден.")
            return

        photo_paths = await db.get_user_photos(user_id, "input")
        if not photo_paths:
            await bot.send_message(user_id, "❌ Не найдены ваши фото. Загрузите их через «📤 Загрузить фото».")
            return

        gender = await db.get_user_gender(user_id)

        if selected_model == 'gemini':
            service = AITunnelService()
        elif selected_model == 'gpt':
            service = AITunnelService(model_type="gpt", quality="high", size="1536x1024")
        elif selected_model == 'nanobanana':
            service = AITunnelService(model_type="nanobanana")
        else:
            await bot.send_message(user_id, "❌ Неизвестная модель генерации.")
            return

        results = await service.generate_photos(
            user_photo_paths=photo_paths,
            style_key=style_key,
            num_images=1,
            gender=gender
        )

        if results:
            await bot.send_message(user_id, f"✅ Оплата получена! Ваше фото в стиле {style['name']}:")
            for image_data in results:
                await send_photo_or_fallback(bot, user_id, image_data)

            if label:
                await db.mark_order_processed(label)

            if context and context.user_data:
                context.user_data.pop('selected_style', None)
                context.user_data.pop('selected_model', None)

            await bot.send_message(
                user_id,
                text="👇 *Главное меню*:",
                parse_mode='Markdown',
                reply_markup=get_main_menu_keyboard()
            )
        else:
            logger.error(f"Генерация не удалась для user {user_id}, заказ {label}")
            await bot.send_message(
                user_id,
                text="❌ Не удалось сгенерировать фото. Попробуйте позже. Если деньги списаны, они вернутся автоматически."
            )
            return
    except Exception as e:
        logger.error(f"Ошибка в generate_paid_photo: {e}", exc_info=True)
        await bot.send_message(
            user_id,
            text="❌ Внутренняя ошибка. Мы уже работаем над исправлением."
        )
        raise

# ---------- Обработка вебхука ЮKassa ----------
async def process_yookassa_webhook(data: dict, bot: Bot, db):
    logger.info(f"Получено уведомление от ЮKassa: {data}")
    event = data.get('event')
    if event != 'payment.succeeded':
        logger.info(f"Игнорируем событие {event}")
        return

    payment = data.get('object')
    if not payment:
        logger.warning("Нет объекта payment")
        return

    metadata = payment.get('metadata', {})
    label = metadata.get('label')
    if not label:
        logger.warning("Нет label в метаданных")
        return

    if await db.is_order_processed(label):
        logger.info(f"Заказ {label} уже обработан, пропускаем")
        return

    user_id = metadata.get('user_id')
    if not user_id:
        parts = label.split('_')
        if len(parts) > 1 and parts[1].isdigit():
            user_id = int(parts[1])
    if not user_id:
        logger.error(f"Не удалось определить user_id для {label}")
        return

    # ---------- Обработка разных типов заказов ----------
    if label.startswith("tokens20_"):
        await db.add_tokens(user_id, 20)
        await bot.send_message(user_id, "✅ Вам начислено 20 жетонов! Используйте их при генерации.")
        await db.mark_order_processed(label)

    elif label.startswith("couple_"):
        order_data = await db.get_order_data(label)
        if order_data:
            try:
                from handlers.couple import generate_couple_photo_from_data
                await generate_couple_photo_from_data(user_id, bot, db, order_data)
            except Exception as e:
                logger.error(f"Ошибка генерации парного фото {label}: {e}", exc_info=True)
                await db.add_tokens(user_id, Config.COUPLE_TOKEN_COST)
                await bot.send_message(
                    user_id,
                    f"⚠️ Произошла техническая ошибка при генерации парного фото. Вам начислено {Config.COUPLE_TOKEN_COST} жетонов. Вы можете повторить попытку."
                )
            finally:
                await db.mark_order_processed(label)
        else:
            logger.error(f"Нет данных для заказа {label}")

    elif label.startswith("custom_"):
        order_data = await db.get_order_data(label)
        if order_data:
            try:
                from handlers.custom_prompt import generate_custom_photo_from_data
                await generate_custom_photo_from_data(user_id, bot, db, order_data)
            except Exception as e:
                logger.error(f"Ошибка генерации кастомного фото {label}: {e}", exc_info=True)
                tokens = Config.TOKEN_COST_GPT
                await db.add_tokens(user_id, tokens)
                await bot.send_message(
                    user_id,
                    f"⚠️ Произошла техническая ошибка при генерации. Вам начислено {tokens} жетонов."
                )
            finally:
                await db.mark_order_processed(label)
        else:
            logger.error(f"Нет данных для заказа {label}")

    elif label.startswith("video_"):
        order_data = await db.get_order_data(label)
        if order_data:
            try:
                from handlers.video import generate_video_from_data
                await generate_video_from_data(user_id, bot, db, order_data)
            except Exception as e:
                logger.error(f"Ошибка генерации видео {label}: {e}", exc_info=True)
                token_cost = 8  # Sora 2 Pro стоит 8 жетонов
                await db.add_tokens(user_id, token_cost)
                await bot.send_message(
                    user_id,
                    f"⚠️ Ошибка генерации видео. Вам начислено {token_cost} жетонов. Попробуйте позже."
                )
            finally:
                await db.mark_order_processed(label)
        else:
            logger.error(f"Нет данных для заказа {label}")

    else:  # одиночные фото (single_...)
        order_data = await db.get_order_data(label)
        if not order_data:
            logger.error(f"Нет данных для заказа {label}")
            return
        try:
            await generate_paid_photo(user_id, bot, db, label=label, order_data=order_data)
        except Exception as e:
            logger.error(f"Ошибка генерации одиночного фото {label}: {e}", exc_info=True)
            selected_model = order_data.get('selected_model', 'gemini')
            if selected_model == 'gemini':
                tokens = Config.TOKEN_COST_GEMINI
            elif selected_model == 'gpt':
                tokens = Config.TOKEN_COST_GPT
            else:
                tokens = Config.TOKEN_COST_NANOBANANA
            await db.add_tokens(user_id, tokens)
            await bot.send_message(
                user_id,
                f"⚠️ Произошла техническая ошибка. Вам начислено {tokens} жетонов. Вы можете повторить попытку позже."
            )
            await db.mark_order_processed(label)

    logger.info(f"Обработка платежа {label} завершена")

# ---------- Экспорт обработчиков ----------
buy_handler = CommandHandler("buy", buy_command)
buy_tokens_handler = CommandHandler("buy20", buy_tokens_command)
buy_tokens_callback_handler = CallbackQueryHandler(buy_tokens_callback, pattern="^buy_tokens$")