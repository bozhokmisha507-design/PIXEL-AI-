import hashlib
import logging
import uuid
from decimal import Decimal
from urllib.parse import urlencode

from aiohttp import web
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from config import Config
from database.db import get_db
from handlers.menu import get_main_menu_keyboard
from services.aitunnel_service import AITunnelService
from utils.helpers import send_photo_or_fallback

logger = logging.getLogger(__name__)

MERCHANT_LOGIN = Config.ROBOKASSA_LOGIN
PASSWORD_1 = Config.ROBOKASSA_PASSWORD_1
PASSWORD_2 = Config.ROBOKASSA_PASSWORD_2
IS_TEST = Config.ROBOKASSA_TEST_MODE  # 0 - рабочий режим

ROBOKASSA_URL = "https://merchant.roboxchange.com/Index.aspx"

def generate_signature(out_sum: str, inv_id: str, password: str) -> str:
    """MD5 подпись для Robokassa."""
    signature_str = f"{MERCHANT_LOGIN}:{out_sum}:{inv_id}:{password}"
    return hashlib.md5(signature_str.encode()).hexdigest()

def get_payment_link(amount: Decimal, inv_id: str, description: str) -> str:
    """Ссылка на оплату (рабочий режим)."""
    params = {
        "MrchLogin": MERCHANT_LOGIN,
        "OutSum": str(amount),
        "InvId": inv_id,
        "Desc": description,
        "SignatureValue": generate_signature(str(amount), inv_id, PASSWORD_1),
        "Culture": "ru",
    }
    return f"{ROBOKASSA_URL}?{urlencode(params)}"

# ---------- Команда /buy (обычная генерация) ----------
async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    selected_model = 'gemini'
    if context.user_data is not None:
        selected_model = context.user_data.get('selected_model', 'gemini')
    amount = Decimal(str(Config.PRICE_PREMIUM if selected_model == 'gpt' else Config.PRICE_PER_GENERATION))
    inv_id = f"order_{user_id}_{uuid.uuid4().hex[:8]}"
    description = "Оплата генерации фото в PIXEL AI"

    db = await get_db()
    await db.create_order(user_id, inv_id, float(amount))

    payment_url = get_payment_link(amount, inv_id, description)
    keyboard = [[InlineKeyboardButton("💳 Оплатить", url=payment_url)]]
    await update.message.reply_text(
        f"✨ Стоимость генерации: {amount} руб.\n\n👇 Нажмите кнопку ниже для оплаты:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ---------- Команда /buy20 (пакет жетонов) ----------
async def buy_tokens_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    amount = Decimal(str(Config.PRICE_20_TOKENS))
    inv_id = f"tokens20_{user_id}_{uuid.uuid4().hex[:8]}"
    description = "Пакет 20 жетонов"

    db = await get_db()
    await db.create_order(user_id, inv_id, float(amount))

    payment_url = get_payment_link(amount, inv_id, description)
    keyboard = [[InlineKeyboardButton(f"💳 Оплатить {amount}₽", url=payment_url)]]
    await update.message.reply_text(
        f"✨ Купи пакет из 20 жетонов!\nСтоимость пакета: {amount}₽",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ---------- Callback для inline-кнопки "💎 Купить жетоны" ----------
async def buy_tokens_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    amount = Decimal(str(Config.PRICE_20_TOKENS))
    inv_id = f"tokens20_{user_id}_{uuid.uuid4().hex[:8]}"
    description = "Пакет 20 жетонов"

    db = await get_db()
    await db.create_order(user_id, inv_id, float(amount))

    payment_url = get_payment_link(amount, inv_id, description)
    keyboard = [[InlineKeyboardButton(f"💳 Оплатить {amount}₽", url=payment_url)]]
    await query.edit_message_text(
        f"✨ Купи пакет из 20 жетонов!\nСтоимость пакета: {amount}₽",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ---------- Административная команда начисления жетонов ----------
async def add_tokens_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in Config.ADMIN_IDS:
        await update.message.reply_text("❌ У вас нет прав для этой команды.")
        return
    args = context.args
    if len(args) != 2:
        await update.message.reply_text("❌ Использование: /add_tokens <user_id> <количество>")
        return
    try:
        user_id = int(args[0])
        amount = int(args[1])
    except ValueError:
        await update.message.reply_text("❌ Неверные аргументы.")
        return
    db = await get_db()
    await db.add_tokens(user_id, amount)
    await update.message.reply_text(f"✅ Пользователю {user_id} начислено {amount} жетонов.")

# ---------- Генерация фото (скопируйте из вашего старого payment.py) ----------
async def generate_paid_photo(user_id: int, bot: Bot, db, context=None, label=None):
    """Генерация фото после оплаты. (ваша существующая логика)"""
    try:
        if label:
            if await db.is_order_processed(label):
                logger.info(f"Заказ {label} уже обработан, пропускаем генерацию для user {user_id}")
                return
            logger.info(f"Начинаем генерацию для заказа {label}, user {user_id}")

        style_key = await db.get_user_selected_style(user_id)
        if not style_key:
            await bot.send_message(user_id, "❌ Стиль не выбран.")
            from handlers.styles import show_styles_menu
            await show_styles_menu(user_id, context)
            return

        style = Config.STYLES.get(style_key)
        if not style:
            await bot.send_message(user_id, "❌ Стиль не найден.")
            return

        photo_paths = await db.get_user_photos(user_id, "input")
        if not photo_paths:
            await bot.send_message(user_id, "❌ Нет фото. Загрузите через меню.")
            return

        gender = await db.get_user_gender(user_id)
        selected_model = 'gemini'
        if context and context.user_data:
            selected_model = context.user_data.get('selected_model', 'gemini')

        if selected_model == 'gemini':
            service = AITunnelService()
        elif selected_model == 'gpt':
            service = AITunnelService(model_type="gpt", quality="high", size="1536x1024")
        elif selected_model == 'nanobanana':
            service = AITunnelService(model_type="nanobanana")
        else:
            await bot.send_message(user_id, "❌ Неизвестная модель.")
            return

        results = await service.generate_photos(photo_paths, style_key, 1, gender)

        if results:
            await bot.send_message(user_id, f"✅ Ваше фото в стиле {style['name']}:")
            for img in results:
                await send_photo_or_fallback(bot, user_id, img)
            if label:
                await db.mark_order_processed(label)
            if context and context.user_data:
                context.user_data.pop('selected_style', None)
                context.user_data.pop('selected_model', None)
            await bot.send_message(user_id, "👇 *Главное меню*:", parse_mode='Markdown', reply_markup=get_main_menu_keyboard())
        else:
            logger.error(f"Генерация не дала результатов для user {user_id}")
            await bot.send_message(user_id, "❌ Не удалось сгенерировать фото.")
    except Exception as e:
        logger.error(f"Ошибка generate_paid_photo: {e}", exc_info=True)
        await bot.send_message(user_id, "❌ Внутренняя ошибка.")

# ---------- Обработка вебхука от Robokassa (ResultURL) ----------
async def robokassa_result_handler(request):
    data = await request.post()
    logger.info(f"ResultURL от Robokassa: {data}")

    inv_id = data.get("InvId")
    out_sum = data.get("OutSum")
    signature = data.get("SignatureValue")

    if not inv_id or not out_sum or not signature:
        return web.Response(text="ERROR: missing params")

    expected_sig = generate_signature(out_sum, inv_id, PASSWORD_2)
    if signature.lower() != expected_sig.lower():
        logger.warning(f"Неверная подпись для заказа {inv_id}")
        return web.Response(text=f"ERROR: bad signature for {inv_id}")

    db = await get_db()
    if await db.is_order_processed(inv_id):
        return web.Response(text=f"OK{inv_id}")

    await db.mark_order_processed(inv_id)

    if inv_id.startswith("tokens20_"):
        user_id = int(inv_id.split('_')[1])
        await db.add_tokens(user_id, 20)
        bot = request.app["bot"]
        await bot.send_message(user_id, "✅ Вам начислено 20 жетонов!")
    elif inv_id.startswith("couple_"):
        # здесь обработка парных фото, если есть
        pass
    elif inv_id.startswith("custom_"):
        # обработка кастомного промпта
        pass
    else:
        user_id = int(inv_id.split('_')[1])
        bot = request.app["bot"]
        await generate_paid_photo(user_id, bot, db, context=None, label=inv_id)

    return web.Response(text=f"OK{inv_id}")

async def robokassa_success_handler(request):
    logger.info(f"SuccessURL: {request.query}")
    return web.Response(text="Платёж успешно завершён! Можете закрыть страницу.")

async def robokassa_fail_handler(request):
    logger.info(f"FailURL: {request.query}")
    return web.Response(text="Платёж не удался. Попробуйте позже.")