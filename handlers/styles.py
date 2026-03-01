from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler
from config import Config
from handlers.menu import get_main_menu_keyboard
from services.aitunnel_service import AITunnelService
import logging
import asyncio
import base64
import re
import aiohttp
import os

logger = logging.getLogger(__name__)
aitunnel_service = AITunnelService()

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
    if not update.message:
        return
    await show_styles_menu(update.message)

async def show_styles_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает меню стилей при нажатии на inline-кнопку"""
    query = update.callback_query
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
    """Обработчик выбора стиля из inline-кнопок"""
    query = update.callback_query
    await query.answer()

    style_key = query.data.replace("select_style_", "")
    style = Config.STYLES.get(style_key)

    if not style:
        await query.edit_message_text("❌ Неизвестный стиль.")
        return

    # Получаем фото пользователя
    db = context.bot_data['db']
    user_id = update.effective_user.id
    
    # Проверяем количество фото
    photo_count = await db.get_user_photo_count(user_id)
    if photo_count < Config.MIN_PHOTOS:
        await query.edit_message_text(
            f"⚠️ Нужно минимум {Config.MIN_PHOTOS} фото. Сейчас: {photo_count}\n\n"
            f"Нажми «📤 Загрузить фото» в главном меню."
        )
        await context.bot.send_message(
            chat_id=user_id,
            text="Главное меню:",
            reply_markup=get_main_menu_keyboard()
        )
        return
    
    # Получаем пути к фото
    photo_paths = await db.get_user_photos(user_id, "input")
    
    if not photo_paths:
        await query.edit_message_text("❌ Ошибка получения фото.")
        await context.bot.send_message(
            chat_id=user_id,
            text="Главное меню:",
            reply_markup=get_main_menu_keyboard()
        )
        return

    # Сообщаем о начале генерации
    await query.edit_message_text(
        f"🚀 *Генерация запущена!*\n\n"
        f"Стиль: {style['name']}\n"
        f"Используется {len(photo_paths)} фото\n\n"
        f"⏳ Подожди 1-2 минуты...",
        parse_mode='Markdown'
    )

    try:
        # Вызываем AI Tunnel для генерации
        logger.info(f"Запуск генерации для пользователя {user_id}, стиль {style_key}")
        
        results = await aitunnel_service.generate_photos(
            user_photo_paths=photo_paths,
            style_key=style_key,
            num_images=1
        )
        
        logger.info(f"Результаты генерации: {results}")
        
        if results and len(results) > 0:
            # Сначала отправляем текстовое сообщение
            await context.bot.send_message(
                chat_id=user_id,
                text=f"✅ *Готово!*\n\n"
                     f"Вот твое фото в стиле {style['name']}:",
                parse_mode='Markdown'
            )
            
            # Отправляем каждое фото с обработкой ошибок
            for i, image_data in enumerate(results):
                try:
                    if image_data.startswith('data:image'):
                        # Если это base64 data URL
                        base64_str = re.sub('^data:image/.+;base64,', '', image_data)
                        image_bytes = base64.b64decode(base64_str)
                        
                        # Пробуем отправить фото
                        await context.bot.send_photo(
                            chat_id=user_id,
                            photo=image_bytes,
                            caption=f"✨ *{style['name']}*",
                            parse_mode='Markdown'
                        )
                        logger.info(f"Фото #{i+1} отправлено из base64")
                        
                    elif image_data.startswith('http'):
                        # Если это URL
                        await context.bot.send_photo(
                            chat_id=user_id,
                            photo=image_data,
                            caption=f"✨ *{style['name']}*",
                            parse_mode='Markdown'
                        )
                        logger.info(f"Фото #{i+1} отправлено по URL")
                    else:
                        # Если это просто текст
                        await context.bot.send_message(
                            chat_id=user_id,
                            text=f"🖼️ {image_data}"
                        )
                except Exception as e:
                    logger.error(f"Ошибка отправки фото: {e}")
                    # Если фото не отправилось, отправляем ссылку
                    if image_data.startswith('http'):
                        await context.bot.send_message(
                            chat_id=user_id,
                            text=f"🖼️ [Ссылка на фото #{i+1}]({image_data})",
                            parse_mode='Markdown'
                        )
        else:
            await context.bot.send_message(
                chat_id=user_id,
                text="❌ Не удалось сгенерировать фото. Попробуй позже."
            )

    except Exception as e:
        logger.error(f"Ошибка генерации: {e}", exc_info=True)
        await context.bot.send_message(
            chat_id=user_id,
            text=f"❌ Ошибка при генерации: {str(e)[:100]}..."
        )

    # Возвращаем главное меню в любом случае (это не вызовет timeout)
    await context.bot.send_message(
        chat_id=user_id,
        text="👇 *Главное меню*:",
        parse_mode='Markdown',
        reply_markup=get_main_menu_keyboard()
    )

styles_handler = CommandHandler("styles", styles_command)
show_styles_cb = CallbackQueryHandler(show_styles_callback, pattern="^show_styles$")
style_selected_cb = CallbackQueryHandler(style_selected_callback, pattern="^select_style_")