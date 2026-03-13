import uuid
import logging
import os
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from config import Config
from handlers.menu import get_main_menu_keyboard
from database.db import get_db
from services.aitunnel_service import AITunnelService
from utils.helpers import send_video_or_fallback

logger = logging.getLogger(__name__)

# Состояния диалога
PHOTO, PROMPT, MODEL_SELECT, CONFIRM = range(4)

# Цена и стоимость в жетонах для видео
VIDEO_PRICE = 110
VIDEO_TOKEN_COST = 3

# Модели для видео (пока одна)
VIDEO_MODELS = {
    "sora2pro": "🎬 Sora 2 Pro (Image-to-Video, 1280x720)"
}

async def video_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало диалога: просим загрузить фото (селфи)."""
    user_id = update.effective_user.id
    context.user_data['video_photos'] = []
    await update.message.reply_text(
        "🎬 *Создание видео из фото*\n\n"
        "Сначала загрузите одно или несколько селфи (до 5).\n"
        "Чем лучше качество фото, тем лучше получится видео.\n\n"
        "Отправьте фото:",
        parse_mode='Markdown'
    )
    return PHOTO

async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка загруженных фото."""
    if not update.message.photo:
        await update.message.reply_text("Пожалуйста, отправьте фото.")
        return PHOTO

    user_id = update.effective_user.id
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)

    user_dir = os.path.join(Config.UPLOAD_DIR, str(user_id))
    os.makedirs(user_dir, exist_ok=True)

    file_path = os.path.join(user_dir, f"video_photo_{uuid.uuid4().hex[:8]}.jpg")
    await file.download_to_drive(file_path)
    logger.info(f"Сохранено фото для видео: {file_path}")

    photos = context.user_data.setdefault('video_photos', [])
    photos.append(file_path)

    if len(photos) >= Config.MAX_PHOTOS:
        await update.message.reply_text(
            f"✅ Загружено максимальное количество фото ({Config.MAX_PHOTOS}). Теперь введите описание видео."
        )
        return await ask_prompt(update, context)
    else:
        await update.message.reply_text(
            f"✅ Фото сохранено (загружено {len(photos)}/{Config.MAX_PHOTOS}).\n"
            "Можете отправить ещё фото или введите /done, чтобы перейти к описанию."
        )
        return PHOTO

async def done_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Пользователь закончил загружать фото (команда /done)."""
    photos = context.user_data.get('video_photos', [])
    if not photos:
        await update.message.reply_text("❌ Вы не загрузили ни одного фото. Операция отменена.")
        return ConversationHandler.END
    return await ask_prompt(update, context)

async def ask_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запрашиваем текстовый промпт после загрузки фото."""
    await update.message.reply_text(
        "✍️ *Введите описание видео*\n\n"
        "Опишите, что должно происходить на видео. Например:\n"
        "*«человек поворачивает голову и улыбается»*\n"
        "*«медленно приближается камера, фон меняется на космический»*",
        parse_mode='Markdown'
    )
    return PROMPT

async def prompt_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получаем промпт и показываем выбор модели."""
    if not update.message.text:
        await update.message.reply_text("Пожалуйста, введите текстовое описание.")
        return PROMPT

    prompt = update.message.text.strip()
    context.user_data['video_prompt'] = prompt

    # Показываем выбор модели
    keyboard = []
    for key, name in VIDEO_MODELS.items():
        keyboard.append([InlineKeyboardButton(name, callback_data=f"video_model_{key}")])
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="video_cancel")])

    await update.message.reply_text(
        "🎬 Выберите модель для генерации видео:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return MODEL_SELECT

async def model_selected_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора модели – показываем варианты оплаты."""
    query = update.callback_query
    await query.answer()

    model_key = query.data.replace("video_model_", "")
    context.user_data['video_model'] = model_key

    user_id = query.from_user.id
    db = await get_db()
    tokens = await db.get_user_tokens(user_id)

    price = VIDEO_PRICE
    token_cost = VIDEO_TOKEN_COST

    keyboard = []
    if tokens >= token_cost:
        keyboard.append([InlineKeyboardButton(
            f"💎 Использовать жетоны ({token_cost} шт., у вас {tokens})",
            callback_data="video_pay_tokens"
        )])
    keyboard.append([InlineKeyboardButton(
        f"💳 Оплатить {price}₽",
        callback_data="video_pay_money"
    )])
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="video_cancel")])

    model_name = VIDEO_MODELS.get(model_key, model_key)
    await query.edit_message_text(
        f"✅ Выбрана модель: {model_name}\n\n"
        f"Стоимость: {price}₽ или {token_cost} жетона.\n\n"
        "Как хотите оплатить?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CONFIRM

async def pay_with_tokens_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Оплата жетонами."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    db = await get_db()

    if not await db.use_tokens(user_id, VIDEO_TOKEN_COST):
        await query.edit_message_text("❌ Недостаточно жетонов.")
        return ConversationHandler.END

    await query.edit_message_text("⏳ Генерация видео с использованием жетонов...")
    await generate_video(user_id, context.bot, db, context)
    return ConversationHandler.END

async def pay_with_money_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Оплата деньгами – создаём заказ и ссылку."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    label = f"video_{user_id}_{uuid.uuid4().hex[:8]}"
    amount = VIDEO_PRICE

    # Сохраняем данные заказа (промпт, модель, пути к фото)
    data = {
        'prompt': context.user_data['video_prompt'],
        'model': context.user_data['video_model'],
        'photos': context.user_data.get('video_photos', [])
    }

    db = await get_db()
    await db.create_order(user_id, label, amount, data=data)

    try:
        from yoomoney import Quickpay
        quickpay = Quickpay(
            receiver=Config.YOOMONEY_WALLET,
            quickpay_form="shop",
            targets="Генерация видео в PIXEL AI (Image-to-Video)",
            paymentType="AC",
            sum=amount,
            label=label,
            successURL=f"https://t.me/bma3_bot?start={label}"
        )
        payment_url = quickpay.redirected_url
    except Exception as e:
        logger.error(f"Ошибка создания ссылки для видео: {e}")
        await query.edit_message_text("❌ Не удалось создать ссылку. Попробуйте позже.")
        return ConversationHandler.END

    keyboard = [[InlineKeyboardButton(f"💳 Оплатить {amount}₽", url=payment_url)]]
    await query.edit_message_text(
        "✨ Для завершения оплаты нажмите кнопку ниже. После оплаты видео придёт автоматически.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ConversationHandler.END

async def cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена операции."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("❌ Операция отменена.")
    # Очищаем временные фото
    if 'video_photos' in context.user_data:
        for path in context.user_data['video_photos']:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except:
                pass
        del context.user_data['video_photos']
    return ConversationHandler.END

async def generate_video(user_id: int, bot: Bot, db, context=None):
    """Генерация видео после оплаты жетонами (данные из user_data)."""
    try:
        prompt = context.user_data.get('video_prompt')
        model_key = context.user_data.get('video_model', 'sora2pro')
        photo_paths = context.user_data.get('video_photos', [])
        if not prompt:
            await bot.send_message(user_id, "❌ Не найден промпт для генерации.")
            return
        if not photo_paths:
            await bot.send_message(user_id, "❌ Не найдены исходные фото.")
            return

        aitunnel = AITunnelService()
        # Используем Image-to-Video метод
        video_data = await aitunnel.generate_video_sora_i2v(
            image_paths=photo_paths,
            prompt=prompt,
            size="1280x720",
            duration=5
        )

        if video_data:
            await bot.send_message(user_id, "✅ Ваше видео готово!")
            await send_video_or_fallback(bot, user_id, video_data)
        else:
            await bot.send_message(user_id, "❌ Не удалось сгенерировать видео. Попробуйте позже.")

        # Очищаем временные фото
        for path in photo_paths:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except:
                pass
        context.user_data.pop('video_prompt', None)
        context.user_data.pop('video_photos', None)

        await bot.send_message(
            chat_id=user_id,
            text="👇 *Главное меню*:",
            parse_mode='Markdown',
            reply_markup=get_main_menu_keyboard()
        )
    except Exception as e:
        logger.error(f"Ошибка генерации видео: {e}", exc_info=True)
        await bot.send_message(user_id, "❌ Произошла ошибка. Мы уже работаем над её исправлением.")

async def generate_video_from_data(user_id: int, bot: Bot, db, data: dict):
    """Генерация видео по данным из БД (используется после денежной оплаты)."""
    try:
        prompt = data.get('prompt')
        model_key = data.get('model', 'sora2pro')
        photo_paths = data.get('photos', [])

        if not prompt:
            logger.error(f"Нет промпта в данных заказа: {data}")
            await bot.send_message(user_id, "❌ Ошибка: неполные данные заказа.")
            return
        if not photo_paths:
            await bot.send_message(user_id, "❌ Не найдены исходные фото.")
            return

        aitunnel = AITunnelService()
        video_data = await aitunnel.generate_video_sora_i2v(
            image_paths=photo_paths,
            prompt=prompt,
            size="1280x720",
            duration=5
        )

        if video_data:
            await bot.send_message(user_id, "✅ Ваше видео готово!")
            await send_video_or_fallback(bot, user_id, video_data)
        else:
            await bot.send_message(user_id, "❌ Не удалось сгенерировать видео. Попробуйте позже.")

        # Очищаем временные фото
        for path in photo_paths:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except:
                pass

        await bot.send_message(
            chat_id=user_id,
            text="👇 *Главное меню*:",
            parse_mode='Markdown',
            reply_markup=get_main_menu_keyboard()
        )
    except Exception as e:
        logger.error(f"Ошибка генерации видео из данных: {e}", exc_info=True)
        await bot.send_message(user_id, "❌ Произошла ошибка. Мы уже работаем над её исправлением.")

# ConversationHandler
video_conv = ConversationHandler(
    entry_points=[MessageHandler(filters.Text("🎬 Создать видео"), video_start)],
    states={
        PHOTO: [
            MessageHandler(filters.PHOTO, photo_handler),
            CommandHandler("done", done_photo)
        ],
        PROMPT: [MessageHandler(filters.TEXT & ~filters.COMMAND, prompt_handler)],
        MODEL_SELECT: [CallbackQueryHandler(model_selected_callback, pattern="^video_model_")],
        CONFIRM: [
            CallbackQueryHandler(pay_with_tokens_callback, pattern="^video_pay_tokens$"),
            CallbackQueryHandler(pay_with_money_callback, pattern="^video_pay_money$"),
            CallbackQueryHandler(cancel_callback, pattern="^video_cancel$"),
        ],
    },
    fallbacks=[CommandHandler("cancel", cancel_callback)],
    per_user=True,
    per_chat=True,
    name="video_conversation"
)