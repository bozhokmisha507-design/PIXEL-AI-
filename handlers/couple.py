import uuid
import logging
import os
import json
import aiohttp
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from config import Config
from handlers.menu import get_main_menu_keyboard
from database.db import get_db
from services.aitunnel_service import AITunnelService
from utils.helpers import send_photo_or_fallback

logger = logging.getLogger(__name__)

# Состояния диалога
PHOTO_MALE, PHOTO_FEMALE, STYLE_SELECT, CONFIRM = range(4)

# Стили для пар
COUPLE_STYLES = {
    "couple_beach": "🏖️ Романтический пляж",
    "couple_wedding": "💒 Свадебное фото",
    "couple_dinner": "🕯️ Романтический ужин",
    "couple_city": "🌃 Вечерний город",
    "couple_forest": "🌲 Лесная прогулка",
}

# Промпты для пар
COUPLE_PROMPTS = {
    "couple_beach": "A romantic close-up portrait of a couple on a beach at sunset, holding hands, embracing, photorealistic, 8k, highly detailed faces, exact facial features as in reference images, faces clearly visible, sharp focus on faces, medium shot, warm sunset lighting",
    "couple_wedding": "A romantic close-up wedding portrait of a couple in a garden, bride in elegant white dress, groom in classic tuxedo, photorealistic, 8k, highly detailed faces, exact facial features as in reference images, faces clearly visible, sharp focus on faces, soft romantic lighting, shallow depth of field, professional wedding photography style",
    "couple_dinner": "A romantic close-up portrait of a couple having a romantic dinner in a cozy restaurant, candlelight, photorealistic, 8k, highly detailed faces, exact facial features as in reference images, faces clearly visible, sharp focus on faces, warm intimate lighting, professional photography style",
    "couple_city": "A romantic close-up portrait of a couple in love standing on a rooftop at night, city lights background, cinematic, photorealistic, 8k, highly detailed faces, exact facial features as in reference images, faces clearly visible, sharp focus on faces, medium shot, professional night photography style",
    "couple_forest": "A romantic close-up portrait of a couple walking in a sunlit forest, holding hands, warm lighting, photorealistic, 8k, highly detailed faces, exact facial features as in reference images, faces clearly visible, sharp focus on faces, medium shot, professional nature photography style, sun rays filtering through trees",
}

async def couple_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    context.user_data['couple_photos'] = []
    await update.message.reply_text(
        "👫 *Парная генерация*\n\n"
        "Сначала загрузи фото **мужчины** (чёткое селфи).\n"
        "После этого я попрошу фото **женщины**.\n\n"
        "Для отмены введите /cancel",
        parse_mode='Markdown'
    )
    return PHOTO_MALE

async def photo_male_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text("Пожалуйста, отправьте фото.")
        return PHOTO_MALE
    user_id = update.effective_user.id
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    user_dir = os.path.join(Config.UPLOAD_DIR, str(user_id))
    os.makedirs(user_dir, exist_ok=True)
    file_path = os.path.join(user_dir, f"couple_male_{uuid.uuid4().hex[:8]}.jpg")
    await file.download_to_drive(file_path)
    logger.info(f"Сохранено фото мужчины: {file_path}")
    context.user_data.setdefault('couple_photos', []).append(file_path)
    await update.message.reply_text("✅ Фото **мужчины** сохранено. Теперь отправьте фото **женщины**.")
    return PHOTO_FEMALE

async def photo_female_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text("Пожалуйста, отправьте фото.")
        return PHOTO_FEMALE
    user_id = update.effective_user.id
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    user_dir = os.path.join(Config.UPLOAD_DIR, str(user_id))
    os.makedirs(user_dir, exist_ok=True)
    file_path = os.path.join(user_dir, f"couple_female_{uuid.uuid4().hex[:8]}.jpg")
    await file.download_to_drive(file_path)
    logger.info(f"Сохранено фото женщины: {file_path}")
    context.user_data['couple_photos'].append(file_path)

    keyboard = []
    for key, name in COUPLE_STYLES.items():
        keyboard.append([InlineKeyboardButton(name, callback_data=f"couple_style_{key}")])
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="couple_cancel")])
    await update.message.reply_text(
        "🎨 *Выберите стиль для вашего парного фото:*",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return STYLE_SELECT

async def style_selected_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    style_key = query.data.replace("couple_style_", "")
    context.user_data['couple_style'] = style_key

    user_id = query.from_user.id
    db = await get_db()
    tokens = await db.get_user_tokens(user_id)

    price = Config.COUPLE_PRICE
    token_cost = Config.COUPLE_TOKEN_COST

    keyboard = []
    if tokens >= token_cost:
        keyboard.append([InlineKeyboardButton(
            f"💎 Использовать жетоны ({token_cost} шт., у вас {tokens})",
            callback_data="couple_pay_tokens"
        )])
    keyboard.append([InlineKeyboardButton(
        f"💳 Оплатить {price}₽",
        callback_data="couple_pay_money"
    )])
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="couple_cancel")])

    await query.edit_message_text(
        f"✅ Выбран стиль: {COUPLE_STYLES.get(style_key, style_key)}\n\n"
        f"Парные фото генерируются на премиум-модели *Nano Banana Pro* для идеального сохранения лиц.\n\n"
        f"Как хотите получить фото?",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CONFIRM

async def pay_with_tokens_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    db = await get_db()
    token_cost = Config.COUPLE_TOKEN_COST

    if not await db.use_tokens(user_id, token_cost):
        await query.edit_message_text("❌ Недостаточно жетонов.")
        return ConversationHandler.END

    # Сохраняем информацию об оплате жетонами для возможного возврата
    context.user_data['couple_paid_with_tokens'] = True
    context.user_data['couple_token_cost'] = token_cost

    await query.edit_message_text("⏳ Генерация парного фото с использованием жетонов...")
    await generate_couple_photo(user_id, context.bot, db, context)
    return ConversationHandler.END

async def pay_with_money_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    label = f"couple_{user_id}_{uuid.uuid4().hex[:8]}"
    amount = Config.COUPLE_PRICE

    data = {
        'male_photo': context.user_data['couple_photos'][0],
        'female_photo': context.user_data['couple_photos'][1],
        'style': context.user_data['couple_style']
    }
    db = await get_db()
    await db.create_order(user_id, label, amount, data=data)

    try:
        from yoomoney import Quickpay
        quickpay = Quickpay(
            receiver=Config.YOOMONEY_WALLET,
            quickpay_form="shop",
            targets="Парная генерация фото в PIXEL AI (Nano Banana Pro)",
            paymentType="AC",
            sum=amount,
            label=label,
            successURL=f"https://t.me/bma3_bot?start={label}"
        )
        payment_url = quickpay.redirected_url
    except Exception as e:
        logger.error(f"Ошибка создания ссылки: {e}")
        await query.edit_message_text("❌ Не удалось создать ссылку. Попробуйте позже.")
        return ConversationHandler.END

    keyboard = [[InlineKeyboardButton(f"💳 Оплатить {amount}₽", url=payment_url)]]
    await query.edit_message_text(
        "✨ Для завершения оплаты нажмите кнопку ниже. После оплаты фото придёт автоматически.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ConversationHandler.END

async def cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("❌ Операция отменена.")
    if 'couple_photos' in context.user_data:
        for path in context.user_data['couple_photos']:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except:
                pass
        del context.user_data['couple_photos']
    return ConversationHandler.END

async def generate_couple_photo(user_id: int, bot: Bot, db, context=None):
    """Генерация парного фото с повторными попытками при временных ошибках."""
    if context is None:
        logger.error("generate_couple_photo вызван без контекста")
        await bot.send_message(user_id, "❌ Внутренняя ошибка, повторите попытку.")
        return

    try:
        photo_paths = context.user_data.get('couple_photos', [])
        if len(photo_paths) != 2:
            await bot.send_message(user_id, "❌ Ошибка: не найдены оба фото.")
            return
        style_key = context.user_data.get('couple_style')
        if not style_key:
            await bot.send_message(user_id, "❌ Стиль не выбран.")
            return

        prompt = COUPLE_PROMPTS.get(style_key, "A romantic couple, photorealistic, 8k, faces clearly visible")
        aitunnel = AITunnelService()

        max_retries = 3
        results = None
        for attempt in range(max_retries):
            try:
                results = await aitunnel.generate_couple_photo_nanobanana(
                    male_photo_path=photo_paths[0],
                    female_photo_path=photo_paths[1],
                    prompt=prompt,
                    resolution="2K"
                )
                break  # успех – выходим из цикла
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                logger.error(f"Попытка {attempt+1} генерации не удалась: {e}")
                if attempt == max_retries - 1:
                    raise  # последняя попытка – пробрасываем для общей обработки
                await asyncio.sleep(2)

        if results:
            await bot.send_message(user_id, "✅ Ваше парное фото готово!")
            # Отправляем только первый элемент, чтобы избежать дублей
            await send_photo_or_fallback(bot, user_id, results[0])
        else:
            await bot.send_message(user_id, "❌ Не удалось сгенерировать фото. Попробуйте позже.")
            # Возврат жетонов, если оплачивали жетонами
            if context.user_data.get('couple_paid_with_tokens'):
                token_cost = context.user_data.get('couple_token_cost', Config.COUPLE_TOKEN_COST)
                await db.add_tokens(user_id, token_cost)
                await bot.send_message(user_id, f"💎 Вам возвращено {token_cost} жетонов.")
            return

        # Удаление временных файлов
        for path in photo_paths:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except:
                pass
        context.user_data.pop('couple_photos', None)
        context.user_data.pop('couple_paid_with_tokens', None)
        context.user_data.pop('couple_token_cost', None)

        await bot.send_message(
            chat_id=user_id,
            text="👇 *Главное меню*:",
            parse_mode='Markdown',
            reply_markup=get_main_menu_keyboard()
        )
    except Exception as e:
        logger.error(f"Ошибка генерации: {e}", exc_info=True)
        await bot.send_message(user_id, "❌ Произошла ошибка. Мы уже работаем над её исправлением.")
        # Возврат жетонов при любой ошибке, если оплачивали жетонами
        if context and context.user_data.get('couple_paid_with_tokens'):
            token_cost = context.user_data.get('couple_token_cost', Config.COUPLE_TOKEN_COST)
            await db.add_tokens(user_id, token_cost)
            await bot.send_message(user_id, f"💎 Вам возвращено {token_cost} жетонов.")

async def generate_couple_photo_from_data(user_id: int, bot: Bot, db, data: dict):
    """Генерация парного фото по данным из заказа (оплата деньгами) с повторными попытками."""
    try:
        male_photo = data.get('male_photo')
        female_photo = data.get('female_photo')
        style_key = data.get('style')
        if not male_photo or not female_photo or not style_key:
            logger.error(f"Неполные данные: {data}")
            await bot.send_message(user_id, "❌ Ошибка: неполные данные заказа.")
            return
        if not os.path.exists(male_photo) or not os.path.exists(female_photo):
            await bot.send_message(user_id, "❌ Исходные фото не найдены. Попробуйте начать заново.")
            return

        prompt = COUPLE_PROMPTS.get(style_key, "A romantic couple, photorealistic, 8k, faces clearly visible")
        aitunnel = AITunnelService()

        max_retries = 3
        results = None
        for attempt in range(max_retries):
            try:
                results = await aitunnel.generate_couple_photo_nanobanana(
                    male_photo_path=male_photo,
                    female_photo_path=female_photo,
                    prompt=prompt,
                    resolution="2K"
                )
                break
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                logger.error(f"Попытка {attempt+1} генерации не удалась: {e}")
                if attempt == max_retries - 1:
                    raise
                await asyncio.sleep(2)

        if results:
            await bot.send_message(user_id, "✅ Ваше парное фото готово!")
            # Отправляем только первый элемент
            await send_photo_or_fallback(bot, user_id, results[0])
        else:
            await bot.send_message(user_id, "❌ Не удалось сгенерировать фото. Попробуйте позже.")
            return

        # Удаление исходных фото
        for path in [male_photo, female_photo]:
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
        logger.error(f"Ошибка: {e}", exc_info=True)
        await bot.send_message(user_id, "❌ Произошла ошибка. Мы уже работаем над её исправлением.")

# ConversationHandler
couple_conv = ConversationHandler(
    entry_points=[MessageHandler(filters.Text("👫 Парные фото"), couple_start)],
    states={
        PHOTO_MALE: [MessageHandler(filters.PHOTO, photo_male_handler)],
        PHOTO_FEMALE: [MessageHandler(filters.PHOTO, photo_female_handler)],
        STYLE_SELECT: [CallbackQueryHandler(style_selected_callback, pattern="^couple_style_")],
        CONFIRM: [
            CallbackQueryHandler(pay_with_tokens_callback, pattern="^couple_pay_tokens$"),
            CallbackQueryHandler(pay_with_money_callback, pattern="^couple_pay_money$"),
            CallbackQueryHandler(cancel_callback, pattern="^couple_cancel$"),
        ],
    },
    fallbacks=[CommandHandler("cancel", cancel_callback)],
    per_user=True,
    per_chat=True,
    name="couple_conversation"
)