from telegram import ReplyKeyboardMarkup, KeyboardButton, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters
from database.db import get_db
from config import Config
import logging
import uuid

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
        f"💎 *Ваш баланс жетонов:* {tokens}\n\n"
        "• Gemini = 1 жетон\n"
        "• GPT Image High = 2 жетона\n"
        "• Парные фото = 1 жетон"
    )
    
    # ✅ СОЗДАЁМ ИНЛАЙН-КЛАВИАТУРУ
    keyboard = [
        [InlineKeyboardButton("💎 Купить 20 жетонов за 700₽", callback_data="buy_tokens")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # ✅ ОТПРАВЛЯЕМ СООБЩЕНИЕ С КЛАВИАТУРОЙ
    await update.message.reply_text(
        text,
        parse_mode='Markdown',
        reply_markup=reply_markup  # ← ЭТО САМОЕ ГЛАВНОЕ!
    )

# Экспорт обработчиков
menu_handler = CommandHandler("menu", menu_command)
tokens_handler = MessageHandler(filters.Text("💎 Мои жетоны"), tokens_info_command)