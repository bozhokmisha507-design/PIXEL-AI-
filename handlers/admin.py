from telegram import Update, ParseMode
from telegram.ext import ContextTypes, CommandHandler, ConversationHandler, MessageHandler, filters
from database.db import get_db
from config import ADMIN_IDS
import logging

logger = logging.getLogger(__name__)

# Состояния диалога для /add_tokens
ASK_USER_ID, ASK_AMOUNT = range(2)

# ------------------------------------------------------------
# 1. Команда /add_tokens (диалог для начисления жетонов)
# ------------------------------------------------------------
async def add_tokens_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("⛔ У вас нет прав на эту команду.")
        return ConversationHandler.END

    await update.message.reply_text(
        "🔹 Введите user_id пользователя, которому хотите начислить жетоны:\n"
        "(можно узнать через @userinfobot)"
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
        "🔹 Введите количество жетонов для начисления:"
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

    await update.message.reply_text(
        f"✅ Начислено {amount} жетонов пользователю {target_user_id}."
    )

    # Попытка уведомить пользователя
    try:
        await context.bot.send_message(
            chat_id=target_user_id,
            text=f"🎁 Вам начислено {amount} жетонов! Спасибо, что пользуетесь ботом."
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

# ConversationHandler для /add_tokens
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

# ------------------------------------------------------------
# 2. Команда /broadcast (массовая рассылка сообщений)
# ------------------------------------------------------------
async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет сообщение всем пользователям из таблицы users."""
    user_id = update.effective_user.id

    # Проверка прав администратора
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("⛔ У вас нет прав на эту команду.")
        return

    # Получаем текст сообщения из аргументов команды
    if not context.args:
        await update.message.reply_text(
            "ℹ️ *Как использовать:*\n"
            "Отправьте `/broadcast ваше_сообщение`\n"
            "Пример: `/broadcast Всем привет!`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    broadcast_text = ' '.join(context.args)
    await update.message.reply_text(
        f"⏳ Начинаю рассылку сообщения:\n\n_{broadcast_text}_",
        parse_mode=ParseMode.MARKDOWN
    )

    # Получаем список всех user_id из таблицы users
    db = await get_db()
    async with db.pool.acquire() as conn:
        rows = await conn.fetch("SELECT user_id FROM users")
        user_ids = [row['user_id'] for row in rows]

    logger.info(f"Начинается рассылка для {len(user_ids)} пользователей.")

    success_count = 0
    fail_count = 0

    for uid in user_ids:
        try:
            await context.bot.send_message(
                chat_id=uid,
                text=broadcast_text,
                parse_mode=ParseMode.MARKDOWN
            )
            success_count += 1
        except Exception as e:
            fail_count += 1
            logger.warning(f"Не удалось отправить сообщение пользователю {uid}: {e}")

    result_message = (
        f"✅ *Рассылка завершена!*\n"
        f"Успешно отправлено: `{success_count}`\n"
        f"Не удалось отправить: `{fail_count}`"
    )
    await update.message.reply_text(result_message, parse_mode=ParseMode.MARKDOWN)
    logger.info(f"Рассылка завершена. Отправлено: {success_count}, Ошибок: {fail_count}")

# Обработчик команды /broadcast
broadcast_handler = CommandHandler("broadcast", broadcast_command, filters=filters.ChatType.PRIVATE)