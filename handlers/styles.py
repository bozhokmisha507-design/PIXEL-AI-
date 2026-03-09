from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler
from config import Config
from handlers.menu import get_main_menu_keyboard
from database.db import get_db
from services.aitunnel_service import AITunnelService
from utils.helpers import send_photo_or_fallback
import logging
import aiohttp

logger = logging.getLogger(__name__)

async def show_styles_menu(target, context=None):
    keyboard = []
    for key, style in Config.STYLES.items():
        keyboard.append([
            InlineKeyboardButton(
                f"{style['name']} (1 фото)",
                callback_data=f"select_style_{key}"
            )
        ])

    if isinstance(target, int):
        if context is None:
            return
        await context.bot.send_message(
            chat_id=target,
            text="🎨 *Выбери стиль фотосессии:*\n\n"
                 "Нажми на кнопку с нужным стилем:",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await target.reply_text(
            "🎨 *Выбери стиль фотосессии:*\n\n"
            "Нажми на кнопку с нужным стилем:",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def styles_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user:
        return
    await show_styles_menu(update.message)

async def show_styles_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is None:
        return
    await query.answer()
    await show_styles_menu(query.message)

async def download_image(url, save_path):
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
    query = update.callback_query
    if query is None or query.data is None:
        return
    await query.answer()

    user_id = update.effective_user.id
    logger.info(f"🔥 style_selected_callback вызван для user {user_id} с data: {query.data}")

    style_key = query.data.replace("select_style_", "")
    style = Config.STYLES.get(style_key)

    if not style:
        await query.edit_message_text("❌ Неизвестный стиль.")
        return

    db = await get_db()

    photo_count = await db.get_user_photo_count(user_id)
    if photo_count < Config.MIN_PHOTOS:
        await query.edit_message_text(
            f"⚠️ Нужно минимум {Config.MIN_PHOTOS} фото. Сейчас: {photo_count}\n\n"
            f"Нажми «📤 Загрузить фото» в главном меню."
        )
        return

    await db.set_user_selected_style(user_id, style_key)
    context.user_data['selected_style'] = style_key
    logger.info(f"✅ Стиль {style_key} сохранён для user {user_id}")

    # Предлагаем выбор модели/качества
    keyboard = [
        [InlineKeyboardButton("🚀 Gemini (базовое) – 38₽", callback_data="select_model_gemini")],
        [InlineKeyboardButton("💎 GPT Image High (премиум) – 76₽", callback_data="select_model_gpt")]
    ]
    await query.edit_message_text(
        f"✅ Стиль «{style['name']}» выбран.\n\n"
        "Теперь выберите качество генерации:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def model_selected_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is None or query.data is None:
        return
    await query.answer()

    user_id = update.effective_user.id
    choice = query.data.replace("select_model_", "")
    context.user_data['selected_model'] = choice

    db = await get_db()
    tokens = await db.get_user_tokens(user_id)

    price = Config.PRICE_PER_GENERATION if choice == "gemini" else Config.PRICE_PREMIUM
    model_name = "Gemini" if choice == "gemini" else "GPT Image High"

    token_cost = Config.TOKEN_COST_GEMINI if choice == "gemini" else Config.TOKEN_COST_GPT

    # Формируем клавиатуру
    keyboard = []
    if tokens >= token_cost:
        keyboard.append([InlineKeyboardButton(
            f"💎 Использовать жетоны ({token_cost} шт., у вас {tokens})",
            callback_data="use_token"
        )])
    keyboard.append([InlineKeyboardButton(f"💳 Купить за {price}₽", callback_data="buy_generation")])

    await query.edit_message_text(
        f"✅ Выбрано качество: {model_name}\n"
        f"Цена: {price}₽ или {token_cost} жетон(ов).\n\n"
        "Как хотите получить фото?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def use_token_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is None:
        return
    await query.answer()

    user_id = update.effective_user.id
    db = await get_db()

    style_key = context.user_data.get('selected_style')
    model_choice = context.user_data.get('selected_model', 'gemini')
    if not style_key:
        await query.edit_message_text("❌ Сначала выберите стиль.")
        return

    token_cost = Config.TOKEN_COST_GEMINI if model_choice == "gemini" else Config.TOKEN_COST_GPT

    if not await db.use_tokens(user_id, token_cost):
        await query.edit_message_text("❌ Недостаточно жетонов.")
        return

    await query.edit_message_text("⏳ Генерация с использованием жетонов...")

    await generate_photo_with_tokens(user_id, context.bot, db, context, style_key, model_choice)

async def generate_photo_with_tokens(user_id: int, bot: Bot, db, context, style_key: str, model_choice: str):
    try:
        style = Config.STYLES.get(style_key)
        if not style:
            await bot.send_message(chat_id=user_id, text="❌ Стиль не найден.")
            return

        photo_paths = await db.get_user_photos(user_id, "input")
        if not photo_paths:
            await bot.send_message(
                chat_id=user_id,
                text="❌ Не найдены ваши фото. Сначала загрузите их через /upload."
            )
            return

        gender = await db.get_user_gender(user_id)

        if model_choice == 'gemini':
            service = AITunnelService()
            logger.info(f"Generating with Gemini (tokens) for user {user_id}")
        else:
            service = AITunnelService(model_type="gpt", quality="high", size="1024x1024")
            logger.info(f"Generating with GPT (tokens) for user {user_id}")

        results = await service.generate_photos(
            user_photo_paths=photo_paths,
            style_key=style_key,
            num_images=1,
            gender=gender
        )

        if results:
            await bot.send_message(
                chat_id=user_id,
                text=f"✅ Ваше фото в стиле {style['name']} (использован жетон):"
            )
            for image_data in results:
                await send_photo_or_fallback(bot, user_id, image_data)
        else:
            await bot.send_message(
                chat_id=user_id,
                text="❌ Не удалось сгенерировать фото."
            )

        await bot.send_message(
            chat_id=user_id,
            text="👇 *Главное меню*:",
            parse_mode='Markdown',
            reply_markup=get_main_menu_keyboard()
        )
    except Exception as e:
        logger.error(f"Ошибка генерации по жетону для user {user_id}: {e}", exc_info=True)
        await bot.send_message(
            chat_id=user_id,
            text="❌ Произошла ошибка при генерации. Попробуйте позже."
        )

async def buy_generation_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "Нажмите «💳 Купить генерацию» в главном меню для оплаты."
    )
    await context.bot.send_message(
        chat_id=update.effective_user.id,
        text="👇 *Главное меню*:",
        parse_mode='Markdown',
        reply_markup=get_main_menu_keyboard()
    )

# Обработчики
styles_handler = CommandHandler("styles", styles_command)
show_styles_cb = CallbackQueryHandler(show_styles_callback, pattern="^show_styles$")
style_selected_cb = CallbackQueryHandler(style_selected_callback, pattern="^select_style_")
model_selected_cb = CallbackQueryHandler(model_selected_callback, pattern="^select_model_")
use_token_cb = CallbackQueryHandler(use_token_callback, pattern="^use_token$")
buy_generation_cb = CallbackQueryHandler(buy_generation_callback, pattern="^buy_generation$")