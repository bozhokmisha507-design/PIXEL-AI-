from telegram import ReplyKeyboardMarkup, KeyboardButton, Update
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters
from database.db import get_db
import logging

logger = logging.getLogger(__name__)

def get_main_menu_keyboard():
    buttons = [
        [KeyboardButton("📤 Загрузить фото"), KeyboardButton("💳 Купить генерацию")],
        [KeyboardButton("🖼️ Стили"), KeyboardButton("❓ Помощь")],
        [KeyboardButton("💎 Мои жетоны"), KeyboardButton("🗑 Очистить селфи")],
        [KeyboardButton("🏠 Главное меню")]
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
    await update.message.reply_text(
        f"💎 *Ваши жетоны*: {tokens}\n\n"
        "Gemini = 1 жетон\n"
        "GPT Image High = 2 жетона\n\n"
        "Купить ещё: /buy20",
        parse_mode='Markdown',
        reply_markup=get_main_menu_keyboard()
    )

menu_handler = CommandHandler("menu", menu_command)
tokens_handler = MessageHandler(filters.Text("💎 Мои жетоны"), tokens_info_command)