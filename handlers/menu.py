from telegram import ReplyKeyboardMarkup, KeyboardButton, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters
from database.db import get_db
from config import Config
import logging
import uuid  # ✅ ДОБАВЛЕНО!

logger = logging.getLogger(__name__)

def get_main_menu_keyboard():
    """Главное меню с двумя колонками."""
    buttons = [
        [KeyboardButton("📤 Загрузить фото"), KeyboardButton("👫 Парные фото")],
        [KeyboardButton("🖼️ Стили"), KeyboardButton("💎 Мои жетоны")],
        [KeyboardButton("💳 Купить генерацию"), KeyboardButton("🏠 Главное меню")],
        [KeyboardButton("🗑 Очистить селфи"), KeyboardButton("❓ Помощь")]
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает главное меню."""
    await update.message.reply_text(
        "📌 *Главное меню*\n\nВыберите действие:",
        parse_mode='Markdown',
        reply_markup=get_main_menu_keyboard()
    )

async def tokens_info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает баланс жетонов и предлагает купить ещё."""
    user_id = update.effective_user.id
    db = await get_db()
    tokens = await db.get_user_tokens(user_id)

    text = (
        f"💎 *Ваши жетоны*: {tokens}\n\n"
        "**Как тратить жетоны:**\n"
        "• Gemini (базовое) = 1 жетон\n"
        "• GPT Image High (премиум) = 2 жетона\n"
        "• Парные фото = 1 жетон\n\n"
        "**Купить пакет 20 жетонов:**"
    )
    
    # Инлайн-кнопка для покупки
    keyboard = [[InlineKeyboardButton("💎 Купить 20 жетонов за 700₽", callback_data="buy_tokens")]]
    
    # Отправляем сообщение с инлайн-кнопкой
    await update.message.reply_text(
        text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def buy_tokens_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает нажатие на кнопку покупки жетонов."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    label = f"tokens20_{user_id}_{uuid.uuid4().hex[:8]}"
    amount = Config.PRICE_20_TOKENS

    db = await get_db()
    await db.create_order(user_id, label, amount)

    try:
        from yoomoney import Quickpay
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
        await query.edit_message_text("❌ Не удалось создать ссылку.")
        return

    # Заменяем сообщение на ссылку для оплаты
    keyboard = [[InlineKeyboardButton(f"💳 Оплатить {amount}₽", url=payment_url)]]
    await query.edit_message_text(
        "✨ Для покупки жетонов нажмите кнопку ниже:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# Экспорт обработчиков
menu_handler = CommandHandler("menu", menu_command)
tokens_handler = MessageHandler(filters.Text("💎 Мои жетоны"), tokens_info_command)