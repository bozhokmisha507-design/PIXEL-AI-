from telegram import ReplyKeyboardMarkup, KeyboardButton, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters
from database.db import get_db
from config import Config
import logging
import uuid

logger = logging.getLogger(__name__)

def get_main_menu_keyboard():
    buttons = [
        [KeyboardButton("📤 Загрузить фото"), KeyboardButton("👫 Парные фото")],
        [KeyboardButton("🖼️ Стили"), KeyboardButton("💎 Мои жетоны")],
        [KeyboardButton("💳 Купить генерацию"), KeyboardButton("❓ Помощь")],
        [KeyboardButton("🗑 Очистить селфи"), KeyboardButton("🏠 Главное меню")],
        [KeyboardButton("✍️ Свой промпт"), KeyboardButton("🎬 Создать видео")],
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
        f"💎 *Ваш баланс жетонов:* {tokens}\n\n"
        "• Gemini = 1 жетон\n"
        "• GPT Image High = 2 жетона\n"
        "• Nano Banana Pro = 2 жетона\n"
        "• Парные фото = 2 жетона\n"
        "• Видео Sora = 3 жетона"
    )
    keyboard = [[InlineKeyboardButton("💎 Купить 20 жетонов за 700₽", callback_data="buy_tokens")]]
    await update.message.reply_text(
        text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# Экспорт
menu_handler = CommandHandler("menu", menu_command)
tokens_handler = MessageHandler(filters.Text("💎 Мои жетоны"), tokens_info_command)