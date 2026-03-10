import uuid
import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from config import Config
from handlers.menu import get_main_menu_keyboard
from database.db import get_db
from services.aitunnel_service import AITunnelService
from utils.helpers import send_photo_or_fallback

logger = logging.getLogger(__name__)

# Состояния диалога
CHECK_PHOTOS, GET_PROMPT, SELECT_MODEL, CONFIRM = range(4)

# Стоимость в жетонах
TOKEN_COST_GEMINI = 1
TOKEN_COST_GPT = 2

async def custom_prompt_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало диалога: проверяем наличие фото."""
    user_id = update.effective_user.id
    db = await get_db()
    photo_count = await db.get_user_photo_count(user_id)

    if photo_count < Config.MIN_PHOTOS:
        await update.message.reply_text(
            f"❌ Для генерации нужно минимум {Config.MIN_PHOTOS} фото.\n"
            f"Сначала загрузите фото через кнопку «📤 Загрузить фото».",
            reply_markup=get_main_menu_keyboard()
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "✍️ *Введите ваш промпт* — описание того, что вы хотите получить на фото.\n\n"
        "Например: *«я в костюме супергероя на фоне небоскрёбов, ночное освещение»*\n\n"
        "Вы можете использовать любые фразы на русском или английском.",
        parse_mode='Markdown'
    )
    return GET_PROMPT

async def get_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сохраняем промпт и переходим к выбору модели."""
    prompt = update.message.text.strip()
    if not prompt:
        await update.message.reply_text("❌ Промпт не может быть пустым. Попробуйте снова.")
        return GET_PROMPT

    context.user_data['custom_prompt'] = prompt
    logger.info(f"Пользователь {update.effective_user.id} ввёл промпт: {prompt[:50]}...")

    # Клавиатура выбора модели
    keyboard = [
        [InlineKeyboardButton("🚀 Gemini (базовое) – 38₽ / 1 жетон", callback_data="custom_model_gemini")],
        [InlineKeyboardButton("💎 GPT Image High (премиум) – 76₽ / 2 жетона", callback_data="custom_model_gpt")]
    ]
    await update.message.reply_text(
        "🎛 *Выберите модель генерации:*",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECT_MODEL

async def model_selected_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора модели -> показываем варианты оплаты."""
    query = update.callback_query
    await query.answer()

    model_choice = query.data.replace("custom_model_", "")
    context.user_data['custom_model'] = model_choice

    user_id = query.from_user.id
    db = await get_db()
    tokens = await db.get_user_tokens(user_id)

    price = Config.PRICE_PER_GENERATION if model_choice == "gemini" else Config.PRICE_PREMIUM
    token_cost = TOKEN_COST_GEMINI if model_choice == "gemini" else TOKEN_COST_GPT
    model_name = "Gemini" if model_choice == "gemini" else "GPT Image High"

    keyboard = []
    if tokens >= token_cost:
        keyboard.append([InlineKeyboardButton(
            f"💎 Использовать жетоны ({token_cost} шт., у вас {tokens})",
            callback_data="custom_pay_tokens"
        )])
    keyboard.append([InlineKeyboardButton(f"💳 Оплатить {price}₽", callback_data="custom_pay_money")])
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="custom_cancel")])

    await query.edit_message_text(
        f"✅ Выбрана модель: {model_name}\n"
        f"Цена: {price}₽ или {token_cost} жетон(ов).\n\n"
        f"Ваш промпт:\n_{context.user_data['custom_prompt'][:100]}..._\n\n"
        f"Как хотите получить фото?",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CONFIRM

async def pay_with_tokens_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Оплата жетонами."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    db = await get_db()

    model_choice = context.user_data.get('custom_model', 'gemini')
    token_cost = TOKEN_COST_GEMINI if model_choice == "gemini" else TOKEN_COST_GPT

    if not await db.use_tokens(user_id, token_cost):
        await query.edit_message_text("❌ Недостаточно жетонов.")
        return ConversationHandler.END

    await query.edit_message_text("⏳ Генерация с использованием жетонов...")
    await generate_custom_photo(user_id, context.bot, db, context)
    return ConversationHandler.END

async def pay_with_money_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Оплата деньгами – создаём заказ."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    label = f"custom_{user_id}_{uuid.uuid4().hex[:8]}"
    model_choice = context.user_data.get('custom_model', 'gemini')
    amount = Config.PRICE_PER_GENERATION if model_choice == "gemini" else Config.PRICE_PREMIUM

    # Сохраняем данные заказа
    data = {
        'prompt': context.user_data['custom_prompt'],
        'model': model_choice
    }

    db = await get_db()
    await db.create_order(user_id, label, amount, data=data)

    try:
        from yoomoney import Quickpay
        quickpay = Quickpay(
            receiver=Config.YOOMONEY_WALLET,
            quickpay_form="shop",
            targets="Кастомная генерация фото в PIXEL AI",
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
    """Отмена диалога."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("❌ Операция отменена.")
    return ConversationHandler.END

async def generate_custom_photo(user_id: int, bot, db, context):
    """Генерация по кастомному промпту после оплаты жетонами."""
    try:
        prompt = context.user_data.get('custom_prompt')
        model_choice = context.user_data.get('custom_model', 'gemini')
        if not prompt:
            await bot.send_message(user_id, "❌ Промпт не найден.")
            return

        photo_paths = await db.get_user_photos(user_id, "input")
        if not photo_paths:
            await bot.send_message(user_id, "❌ Не найдены ваши фото. Загрузите их через меню.")
            return

        gender = await db.get_user_gender(user_id)

        # Адаптируем промпт с учётом пола
        if gender == 'male':
            full_prompt = f"Photo of this man. {prompt}"
        elif gender == 'female':
            full_prompt = f"Photo of this woman. {prompt}"
        else:
            full_prompt = f"Photo of this person. {prompt}"

        # Добавляем инструкцию горизонтального формата для обеих моделей
        full_prompt += " Landscape orientation, horizontal composition, aspect ratio 16:9, wide format."

        if model_choice == 'gemini':
            service = AITunnelService()
            logger.info(f"Custom generation with Gemini for user {user_id}")
        else:
            # ✅ ИСПРАВЛЕНО: размер 1536x1024 (горизонтальный)
            service = AITunnelService(model_type="gpt", quality="high", size="1536x1024")
            logger.info(f"Custom generation with GPT for user {user_id}")

        results = await service.generate_custom_photo(
            user_photo_paths=photo_paths,
            prompt=full_prompt,
            num_images=1
        )

        if results:
            await bot.send_message(user_id, "✅ Ваше фото готово!")
            for image_data in results:
                await send_photo_or_fallback(bot, user_id, image_data)
        else:
            await bot.send_message(user_id, "❌ Не удалось сгенерировать фото. Попробуйте позже.")

        await bot.send_message(
            chat_id=user_id,
            text="👇 *Главное меню*:",
            parse_mode='Markdown',
            reply_markup=get_main_menu_keyboard()
        )
    except Exception as e:
        logger.error(f"Ошибка генерации кастомного фото: {e}", exc_info=True)
        await bot.send_message(user_id, "❌ Произошла ошибка. Мы уже работаем над её исправлением.")

# ConversationHandler
custom_prompt_conv = ConversationHandler(
    entry_points=[MessageHandler(filters.Text("✍️ Свой промпт"), custom_prompt_start)],
    states={
        GET_PROMPT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_prompt)],
        SELECT_MODEL: [CallbackQueryHandler(model_selected_callback, pattern="^custom_model_")],
        CONFIRM: [
            CallbackQueryHandler(pay_with_tokens_callback, pattern="^custom_pay_tokens$"),
            CallbackQueryHandler(pay_with_money_callback, pattern="^custom_pay_money$"),
            CallbackQueryHandler(cancel_callback, pattern="^custom_cancel$"),
        ],
    },
    fallbacks=[CommandHandler("cancel", cancel_callback)],
    per_user=True,
    per_chat=True,
    name="custom_prompt_conversation"
)