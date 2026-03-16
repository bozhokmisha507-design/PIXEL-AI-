import uuid
import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from config import Config
from handlers.menu import get_main_menu_keyboard, MAIN_MENU_BUTTONS   # ← добавили импорт кнопок
from database.db import get_db
from services.aitunnel_service import AITunnelService
from utils.helpers import send_photo_or_fallback

logger = logging.getLogger(__name__)

# Состояния диалога
GET_PROMPT, CONFIRM = range(2)

# Стоимость в жетонах (только GPT)
TOKEN_COST = 2
PRICE = Config.PRICE_PREMIUM  # 76 руб

async def custom_prompt_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало диалога: проверяем наличие фото и не запущен ли уже диалог."""
    # Защита от повторного запуска
    if context.user_data.get('in_custom_prompt'):
        await update.message.reply_text(
            "⚠️ Вы уже начали диалог создания кастомного промпта. Пожалуйста, завершите его или введите /cancel.",
            reply_markup=get_main_menu_keyboard()
        )
        return ConversationHandler.END

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

    # Помечаем, что диалог активен
    context.user_data['in_custom_prompt'] = True

    await update.message.reply_text(
        "✍️ *Введите ваш промпт* — описание того, что вы хотите получить на фото.\n\n"
        "Например: *«я в костюме супергероя на фоне небоскрёбов, ночное освещение»*\n\n"
        "Используется модель GPT Image High (премиум-качество).",
        parse_mode='Markdown'
    )
    return GET_PROMPT

async def get_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сохраняем промпт и переходим к выбору способа оплаты."""
    text = update.message.text.strip()
    
    # Используем импортированный список кнопок главного меню
    if text in MAIN_MENU_BUTTONS:
        await update.message.reply_text(
            "❌ Вы нажали кнопку меню. Пожалуйста, введите текстовое описание того, что хотите получить на фото.",
            parse_mode='Markdown'
        )
        return GET_PROMPT

    if not text:
        await update.message.reply_text("❌ Промпт не может быть пустым. Попробуйте снова.")
        return GET_PROMPT

    context.user_data['custom_prompt'] = text
    logger.info(f"Пользователь {update.effective_user.id} ввёл промпт: {text[:50]}...")

    user_id = update.effective_user.id
    db = await get_db()
    tokens = await db.get_user_tokens(user_id)

    keyboard = []
    if tokens >= TOKEN_COST:
        keyboard.append([InlineKeyboardButton(
            f"💎 Использовать жетоны ({TOKEN_COST} шт., у вас {tokens})",
            callback_data="custom_pay_tokens"
        )])
    keyboard.append([InlineKeyboardButton(
        f"💳 Оплатить {PRICE}₽",
        callback_data="custom_pay_money"
    )])
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="custom_cancel")])

    await update.message.reply_text(
        f"✅ Промпт сохранён.\n\n"
        f"Модель: GPT Image High\n"
        f"Стоимость: {PRICE}₽ или {TOKEN_COST} жетона.\n\n"
        f"👇 **Теперь выберите способ оплаты, нажав одну из кнопок ниже.**",
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

    if not await db.use_tokens(user_id, TOKEN_COST):
        await query.edit_message_text("❌ Недостаточно жетонов.")
        # Снимаем флаг активности диалога
        context.user_data.pop('in_custom_prompt', None)
        return ConversationHandler.END

    # Сохраняем информацию об оплате для возможного возврата
    context.user_data['custom_paid_with_tokens'] = True
    context.user_data['custom_token_cost'] = TOKEN_COST

    await query.edit_message_text("⏳ Генерация с использованием жетонов...")
    await generate_custom_photo(user_id, context.bot, db, context)
    # Флаг будет снят внутри generate_custom_photo при успехе или ошибке
    return ConversationHandler.END

async def pay_with_money_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Оплата деньгами – создаём заказ."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    label = f"custom_{user_id}_{uuid.uuid4().hex[:8]}"
    amount = PRICE

    # Сохраняем данные заказа (модель всегда GPT)
    data = {
        'prompt': context.user_data['custom_prompt'],
        'model': 'gpt'
    }

    db = await get_db()
    await db.create_order(user_id, label, amount, data=data)

    try:
        from yoomoney import Quickpay
        quickpay = Quickpay(
            receiver=Config.YOOMONEY_WALLET,
            quickpay_form="shop",
            targets="Кастомная генерация фото в PIXEL AI (GPT)",
            paymentType="AC",
            sum=amount,
            label=label,
            successURL=f"https://t.me/bma3_bot?start={label}"
        )
        payment_url = quickpay.redirected_url
    except Exception as e:
        logger.error(f"Ошибка создания ссылки: {e}")
        await query.edit_message_text("❌ Не удалось создать ссылку. Попробуйте позже.")
        # Снимаем флаг активности диалога
        context.user_data.pop('in_custom_prompt', None)
        return ConversationHandler.END

    keyboard = [[InlineKeyboardButton(f"💳 Оплатить {amount}₽", url=payment_url)]]
    await query.edit_message_text(
        "✨ Для завершения оплаты нажмите кнопку ниже. После оплаты фото придёт автоматически.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    # Диалог завершён, флаг снимаем
    context.user_data.pop('in_custom_prompt', None)
    return ConversationHandler.END

async def cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена диалога."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("❌ Операция отменена.")
    # Снимаем флаг активности диалога
    context.user_data.pop('in_custom_prompt', None)
    return ConversationHandler.END

async def generate_custom_photo(user_id: int, bot, db, context):
    """Генерация по кастомному промпту после оплаты жетонами (всегда GPT)."""
    try:
        prompt = context.user_data.get('custom_prompt')
        if not prompt:
            await bot.send_message(user_id, "❌ Промпт не найден.")
            context.user_data.pop('in_custom_prompt', None)
            return

        photo_paths = await db.get_user_photos(user_id, "input")
        if not photo_paths:
            await bot.send_message(user_id, "❌ Не найдены ваши фото. Загрузите их через меню.")
            context.user_data.pop('in_custom_prompt', None)
            return

        gender = await db.get_user_gender(user_id)

        # Адаптируем промпт с учётом пола
        if gender == 'male':
            full_prompt = f"Photo of this man. {prompt}"
        elif gender == 'female':
            full_prompt = f"Photo of this woman. {prompt}"
        else:
            full_prompt = f"Photo of this person. {prompt}"

        # Добавляем инструкцию горизонтального формата
        full_prompt += " Landscape orientation, horizontal composition, aspect ratio 16:9, wide format."

        # Всегда используем GPT
        service = AITunnelService(model_type="gpt", quality="high", size="1536x1024")
        logger.info(f"Custom generation with GPT for user {user_id}")

        results = await service.generate_custom_photo(
            user_photo_paths=photo_paths,
            prompt=full_prompt,
            num_images=1
        )

        if results:
            await bot.send_message(user_id, "✅ Ваше фото готово!")
            await send_photo_or_fallback(bot, user_id, results[0])
        else:
            await bot.send_message(user_id, "❌ Не удалось сгенерировать фото. Попробуйте позже.")
            if context.user_data.get('custom_paid_with_tokens'):
                token_cost = context.user_data.get('custom_token_cost', TOKEN_COST)
                await db.add_tokens(user_id, token_cost)
                await bot.send_message(user_id, f"💎 Вам возвращено {token_cost} жетонов.")
            context.user_data.pop('in_custom_prompt', None)
            return

        # Очищаем временные данные
        context.user_data.pop('custom_prompt', None)
        context.user_data.pop('custom_paid_with_tokens', None)
        context.user_data.pop('custom_token_cost', None)
        context.user_data.pop('in_custom_prompt', None)

        await bot.send_message(
            chat_id=user_id,
            text="👇 *Главное меню*:",
            parse_mode='Markdown',
            reply_markup=get_main_menu_keyboard()
        )
    except Exception as e:
        logger.error(f"Ошибка генерации кастомного фото: {e}", exc_info=True)
        await bot.send_message(user_id, "❌ Произошла ошибка. Мы уже работаем над её исправлением.")
        if context and context.user_data.get('custom_paid_with_tokens'):
            token_cost = context.user_data.get('custom_token_cost', TOKEN_COST)
            await db.add_tokens(user_id, token_cost)
            await bot.send_message(user_id, f"💎 Вам возвращено {token_cost} жетонов.")
        context.user_data.pop('in_custom_prompt', None)

# ConversationHandler
custom_prompt_conv = ConversationHandler(
    entry_points=[MessageHandler(filters.Text("✍️ Свой промпт"), custom_prompt_start)],
    states={
        GET_PROMPT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_prompt)],
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