from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, ConversationHandler, MessageHandler, filters
from database.db import get_db
from config import ADMIN_IDS  # мы создадим этот список в config.py
import logging

logger = logging.getLogger(__name__)

# Состояния диалога
ASK_USER_ID, ASK_AMOUNT = range(2)

async def add_tokens_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("⛔ У вас нет прав на эту команду.")
        return ConversationHandler.END

    await update.message.reply_text(
        "🔹 Введите **user_id** пользователя, которому хотите начислить жетоны:\n"
        "(можно узнать через @userinfobot)",
        parse_mode='Markdown'
    )
    return ASK_USER_ID

async def ask_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    try:
        target_user_id = int(text)
    except ValueError:
        await update.message.reply_text("❌ Ошибка: введите число (user_id).")
        return ASK_USER_ID

    context.user_data['target_user_id'] = target_user_id
    await update.message.reply_text(
        "🔹 Введите **количество жетонов** для начисления:"
    )
    return ASK_AMOUNT

async def ask_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    try:
        amount = int(text)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Введите положительное число.")
        return ASK_AMOUNT

    target_user_id = context.user_data['target_user_id']
    db = await get_db()
    await db.add_tokens(target_user_id, amount)

    # Сообщение админу
    await update.message.reply_text(
        f"✅ Начислено **{amount}** жетонов пользователю `{target_user_id}`.",
        parse_mode='Markdown'
    )

    # Уведомление пользователя (если бот может ему написать)
    try:
        await context.bot.send_message(
            chat_id=target_user_id,
            text=f"🎁 Вам начислено **{amount}** жетонов! Спасибо, что пользуетесь ботом.",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.warning(f"Не удалось уведомить пользователя {target_user_id}: {e}")
        await update.message.reply_text(
            f"⚠️ Жетоны начислены, но не удалось уведомить пользователя (возможно, он не запускал бота)."
        )

    context.user_data.clear()
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Операция отменена.")
    return ConversationHandler.END

# ConversationHandler
add_tokens_conv = ConversationHandler(
    entry_points=[CommandHandler("add_tokens", add_tokens_start)],
    states={
        ASK_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_user_id)],
        ASK_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_amount)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    per_user=True,
    per_chat=True,
    name="add_tokens_conversation"
)