from telegram import ReplyKeyboardMarkup, KeyboardButton, Update
from telegram.ext import ContextTypes, CommandHandler

def get_main_menu_keyboard():
    """Возвращает главное меню с кнопками"""
    buttons = [
        [KeyboardButton("📤 Загрузить фото"), KeyboardButton("📸 Генерировать")],
        [KeyboardButton("🖼️ Стили"), KeyboardButton("❓ Помощь")],
        [KeyboardButton("🗑 Очистить селфи"), KeyboardButton("🏠 Главное меню")]  # Добавлена кнопка очистки
    ]
    return ReplyKeyboardMarkup(
        buttons,
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Выберите действие..."
    )

async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /menu"""
    await update.message.reply_text(
        "📌 *Главное меню*\n\nВыберите действие:",
        parse_mode='Markdown',
        reply_markup=get_main_menu_keyboard()
    )

menu_handler = CommandHandler("menu", menu_command)