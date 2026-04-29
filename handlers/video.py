import uuid
import logging
import os
from decimal import Decimal

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, filters, CallbackQueryHandler

from config import Config
from handlers.menu import get_main_menu_keyboard
from database.db import get_db
from services.aitunnel_service import AITunnelService
from utils.helpers import send_video_or_fallback

logger = logging.getLogger(__name__)

PHOTO, PROMPT, MODEL_SELECT, CONFIRM = range(4)
MAX_PHOTOS = 3

VIDEO_MODELS = {
    "sora2pro": {
        "name": "🎬 Sora 2 Pro (премиум)",
        "price_rub": 280,
        "price_tokens": 8,
        "duration": 4,
        "size": "1280x720",
        "model_api": "sora-2-pro"
    },
    "seedance": {
        "name": "⚡ Seedance 1.5 Pro (эконом)",
        "price_rub": 50,
        "price_tokens": 2,
        "duration": 10,
        "size": "1080x1440",
        "model_api": "seedance-1-5-pro"
    }
}

async def video_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['video_photos'] = []
    await update.message.reply_text(
        f"🎬 *Создание видео из фото*\n\n"
        f"Загрузите до {MAX_PHOTOS} селфи (можно одно).\n"
        f"После каждого фото будет появляться кнопка «Готово», чтобы завершить загрузку досрочно.\n\n"
        f"Отправьте фото:",
        parse_mode='Markdown'
    )
    return PHOTO

async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    count = len(photos)

    if count >= MAX_PHOTOS:
        await update.message.reply_text(f"✅ Загружено максимальное количество фото ({MAX_PHOTOS}). Теперь введите описание видео.")
        return await ask_prompt(update, context)
    else:
        keyboard = [[InlineKeyboardButton("✅ Готово", callback_data="video_done")]]
        await update.message.reply_text(
            f"✅ Фото сохранено (загружено {count}/{MAX_PHOTOS}).\n"
            f"Можете отправить ещё фото или нажать кнопку «Готово».",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return PHOTO

async def done_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    photos = context.user_data.get('video_photos', [])
    if not photos:
        await query.edit_message_text("❌ Нет загруженных фото. Начните заново.")
        return ConversationHandler.END
    await query.edit_message_text("✅ Переходим к описанию видео.")
    return await ask_prompt_from_callback(query, context)

async def ask_prompt_from_callback(query, context):
    await query.message.reply_text(
        "✍️ *Введите описание видео*\n\n"
        "Опишите, что должно происходить на видео. Например:\n"
        "*«человек поворачивает голову и улыбается»*\n"
        "*«медленно приближается камера, фон меняется на космический»*",
        parse_mode='Markdown'
    )
    return PROMPT

async def ask_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✍️ *Введите описание видео*\n\n"
        "Опишите, что должно происходить на видео. Например:\n"
        "*«человек поворачивает голову и улыбается»*\n"
        "*«медленно приближается камера, фон меняется на космический»*",
        parse_mode='Markdown'
    )
    return PROMPT

async def prompt_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.text:
        await update.message.reply_text("Пожалуйста, введите текстовое описание.")
        return PROMPT

    prompt = update.message.text.strip()
    context.user_data['video_prompt'] = prompt

    keyboard = []
    for key, info in VIDEO_MODELS.items():
        keyboard.append([InlineKeyboardButton(
            f"{info['name']} – {info['price_rub']}₽ / {info['price_tokens']} жет.",
            callback_data=f"video_model_{key}"
        )])
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="video_cancel")])

    await update.message.reply_text(
        "🎬 Выберите модель для генерации видео:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return MODEL_SELECT

async def model_selected_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    model_key = query.data.replace("video_model_", "")
    context.user_data['video_model'] = model_key

    user_id = query.from_user.id
    db = await get_db()
    tokens = await db.get_user_tokens(user_id)

    info = VIDEO_MODELS[model_key]
    price = info['price_rub']
    token_cost = info['price_tokens']

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

    await query.edit_message_text(
        f"✅ Выбрана модель: {info['name']}\n\n"
        f"Стоимость: {price}₽ или {token_cost} жетона.\n\n"
        "Как хотите оплатить?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CONFIRM

async def pay_with_tokens_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    db = await get_db()
    model_key = context.user_data.get('video_model')
    if not model_key or model_key not in VIDEO_MODELS:
        await query.edit_message_text("❌ Модель не выбрана. Начните заново.")
        return ConversationHandler.END
    token_cost = VIDEO_MODELS[model_key]['price_tokens']

    if not await db.use_tokens(user_id, token_cost):
        await query.edit_message_text("❌ Недостаточно жетонов.")
        return ConversationHandler.END

    context.user_data['video_paid_with_tokens'] = True
    context.user_data['video_token_cost'] = token_cost

    await query.edit_message_text("⏳ Генерация видео с использованием жетонов...")
    await generate_video(user_id, context.bot, db, context)
    return ConversationHandler.END

async def pay_with_money_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    model_key = context.user_data.get('video_model')
    if not model_key or model_key not in VIDEO_MODELS:
        await query.edit_message_text("❌ Модель не выбрана. Начните заново.")
        return ConversationHandler.END

    info = VIDEO_MODELS[model_key]
    amount = info['price_rub']
    label = f"video_{user_id}_{uuid.uuid4().hex[:8]}"

    data = {
        'prompt': context.user_data['video_prompt'],
        'model': model_key,
        'model_api': info['model_api'],
        'duration': info['duration'],
        'size': info['size'],
        'photos': context.user_data.get('video_photos', [])
    }

    db = await get_db()
    await db.create_order(user_id, label, amount, data=data)

    try:
        from yookassa import Payment
        payment = Payment.create({
            "amount": {"value": str(amount), "currency": "RUB"},
            "capture": True,
            "confirmation": {
                "type": "redirect",
                "return_url": f"https://t.me/bma3_bot?start=payment_{label}"
            },
            "description": f"Генерация видео в PIXEL AI ({info['name']})",
            "metadata": {"label": label, "user_id": user_id}
        }, uuid.uuid4())
        payment_url = payment.confirmation.confirmation_url
        await db.update_order_payment_id(label, payment.id)
    except Exception as e:
        logger.error(f"Ошибка создания платежа для видео: {e}")
        await query.edit_message_text("❌ Не удалось создать ссылку. Попробуйте позже.")
        return ConversationHandler.END

    keyboard = [[InlineKeyboardButton(f"💳 Оплатить {amount}₽", url=payment_url)]]
    await query.edit_message_text(
        "✨ Для завершения оплаты нажмите кнопку ниже. После оплаты видео придёт автоматически.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ConversationHandler.END

async def cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("❌ Операция отменена.")
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
    try:
        prompt = context.user_data.get('video_prompt')
        model_key = context.user_data.get('video_model')
        photo_paths = context.user_data.get('video_photos', [])
        if not prompt or not photo_paths or not model_key:
            await bot.send_message(user_id, "❌ Не найдены промпт или фото.")
            return

        info = VIDEO_MODELS[model_key]
        aitunnel = AITunnelService()
        # Используем универсальный метод (см. обновление aitunnel_service.py ниже)
        video_data = await aitunnel.generate_video_generic(
            model=info['model_api'],
            image_paths=photo_paths,
            prompt=prompt,
            size=info['size'],
            duration=info['duration']
        )

        if video_data:
            await bot.send_message(user_id, "✅ Ваше видео готово!")
            await send_video_or_fallback(bot, user_id, video_data)
        else:
            await bot.send_message(user_id, "❌ Не удалось сгенерировать видео. Попробуйте позже.")
            if context.user_data.get('video_paid_with_tokens'):
                token_cost = context.user_data.get('video_token_cost', info['price_tokens'])
                await db.add_tokens(user_id, token_cost)
                await bot.send_message(user_id, f"💎 Вам возвращено {token_cost} жетонов.")
            return

        for path in photo_paths:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except:
                pass
        context.user_data.pop('video_prompt', None)
        context.user_data.pop('video_photos', None)
        context.user_data.pop('video_model', None)

        await bot.send_message(
            chat_id=user_id,
            text="👇 *Главное меню*:",
            parse_mode='Markdown',
            reply_markup=get_main_menu_keyboard()
        )
    except Exception as e:
        logger.error(f"Ошибка генерации видео: {e}", exc_info=True)
        await bot.send_message(user_id, "❌ Произошла ошибка. Мы уже работаем над её исправлением.")
        if context and context.user_data.get('video_paid_with_tokens'):
            token_cost = context.user_data.get('video_token_cost')
            if token_cost:
                await db.add_tokens(user_id, token_cost)
                await bot.send_message(user_id, f"💎 Вам возвращено {token_cost} жетонов.")
        raise

async def generate_video_from_data(user_id: int, bot: Bot, db, data: dict):
    try:
        prompt = data.get('prompt')
        model_api = data.get('model_api')
        duration = data.get('duration', 4)
        size = data.get('size', '1280x720')
        photo_paths = data.get('photos', [])
        if not prompt or not photo_paths or not model_api:
            logger.error(f"Неполные данные: {data}")
            await bot.send_message(user_id, "❌ Ошибка: неполные данные заказа.")
            return

        aitunnel = AITunnelService()
        video_data = await aitunnel.generate_video_generic(
            model=model_api,
            image_paths=photo_paths,
            prompt=prompt,
            size=size,
            duration=duration
        )

        if video_data:
            await bot.send_message(user_id, "✅ Ваше видео готово!")
            await send_video_or_fallback(bot, user_id, video_data)
        else:
            await bot.send_message(user_id, "❌ Не удалось сгенерировать видео. Попробуйте позже.")
            return

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
        raise

video_conv = ConversationHandler(
    entry_points=[MessageHandler(filters.Text("🎬 Создать видео"), video_start)],
    states={
        PHOTO: [
            MessageHandler(filters.PHOTO, photo_handler),
            CallbackQueryHandler(done_callback, pattern="^video_done$")
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