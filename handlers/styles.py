from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler
from config import Config
from handlers.menu import get_main_menu_keyboard
from database.db import get_db
import logging
import aiohttp

logger = logging.getLogger(__name__)

async def show_styles_menu(target, context=None):
    """Универсальная функция показа меню стилей"""
    keyboard = []
    for key, style in Config.STYLES.items():
        keyboard.append([
            InlineKeyboardButton(
                f"{style['name']} (1 фото)",
                callback_data=f"select_style_{key}"
            )
        ])

    if isinstance(target, int):  # если передан user_id
        if context is None:
            return
        await context.bot.send_message(
            chat_id=target,
            text="🎨 *Выбери стиль фотосессии:*\n\n"
                 "Нажми на кнопку с нужным стилем:",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:  # если передан message
        await target.reply_text(
            "🎨 *Выбери стиль фотосессии:*\n\n"
            "Нажми на кнопку с нужным стилем:",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def styles_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /styles"""
    if not update.message or not update.effective_user:
        return
    await show_styles_menu(update.message)

async def show_styles_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает меню стилей при нажатии на inline-кнопку"""
    query = update.callback_query
    if query is None:
        return
    await query.answer()
    await show_styles_menu(query.message)

async def download_image(url, save_path):
    """Скачивает изображение по URL"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    with open(save_path, 'wb') as f:
                        f.write(await response.read())
                    return save_path
    except Exception as e:
        logger.error(f"Ошибка скачивания изображения: {e}")
    return None

async def style_selected_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик выбора стиля – сохраняет стиль и предлагает оплатить."""
    query = update.callback_query
    if query is None or query.data is None:
        return
    await query.answer()

    style_key = query.data.replace("select_style_", "")
    style = Config.STYLES.get(style_key)

    if not style:
        await query.edit_message_text("❌ Неизвестный стиль.")
        return

    user_id = update.effective_user.id
    db = await get_db()

    # Проверяем количество фото
    photo_count = await db.get_user_photo_count(user_id)
    if photo_count < Config.MIN_PHOTOS:
        await query.edit_message_text(
            f"⚠️ Нужно минимум {Config.MIN_PHOTOS} фото. Сейчас: {photo_count}\n\n"
            f"Нажми «📤 Загрузить фото» в главном меню."
        )
        return

    # Сохраняем выбранный стиль в БД
    await db.set_user_selected_style(user_id, style_key)

    await query.edit_message_text(
        f"✅ Стиль «{style['name']}» выбран.\n\n"
        f"Теперь нажми «💳 Купить генерацию», чтобы оплатить и получить фото.",
        parse_mode='Markdown'
    )
    # Возвращаем главное меню с кнопками
    await context.bot.send_message(
        chat_id=user_id,
        text="👇 *Главное меню*:",
        parse_mode='Markdown',
        reply_markup=get_main_menu_keyboard()
    )

# Обработчики
styles_handler = CommandHandler("styles", styles_command)
show_styles_cb = CallbackQueryHandler(show_styles_callback, pattern="^show_styles$")
style_selected_cb = CallbackQueryHandler(style_selected_callback, pattern="^select_style_")