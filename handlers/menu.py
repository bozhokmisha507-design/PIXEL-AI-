from telegram import ReplyKeyboardMarkup, KeyboardButton, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters
from database.db import get_db
from config import Config
import logging

logger = logging.getLogger(__name__)

def get_main_menu_keyboard():
    """Главное меню с двумя колонками: левая колонка, правая колонка."""
    buttons = [
        [KeyboardButton("📤 Загрузить фото"), KeyboardButton("👫 Парные фото")],
        [KeyboardButton("🖼️ Стили"), KeyboardButton("💎 Мои жетоны")],
        [KeyboardButton("💳 Купить генерацию"), KeyboardButton("🏠 Главное меню")],
        [KeyboardButton("🗑 Очистить селфи"), KeyboardButton("❓ Помощь")]
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📌 *Главное меню*\n\nВыберите действие:",
        parse_mode='Markdown',
        reply_markup=get_main_menu_keyboard()
    )

async def tokens_info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    db = await get_db()
    tokens = await db.get_user_tokens(user_id)

    text = (
        f"💎 *Ваши жетоны*: {tokens}\n\n"
        "**Как тратить жетоны:**\n"
        "• Gemini (базовое) = 1 жетон\n"
        "• GPT Image High (премиум) = 2 жетона\n"
        "• Парные фото = 1 жетон\n\n"
        "**Купить пакет 20 жетонов:** /buy20"
    )
    keyboard = [[InlineKeyboardButton("💎 Купить жетоны", callback_data="buy_tokens")]]
    await update.message.reply_text(
        text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    # Возвращаем главное меню (чтобы пользователь мог продолжить)
    await context.bot.send_message(
        chat_id=user_id,
        text="👇 *Главное меню*:",
        parse_mode='Markdown',
        reply_markup=get_main_menu_keyboard()
    )

menu_handler = CommandHandler("menu", menu_command)
tokens_handler = MessageHandler(filters.Text("💎 Мои жетоны"), tokens_info_command)