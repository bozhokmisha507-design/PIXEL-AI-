from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from services.aitunnel_service import AITunnelService
from config import Config
from handlers.menu import get_main_menu_keyboard
import logging

logger = logging.getLogger(__name__)
aitunnel_service = AITunnelService()

async def generate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /generate - показывает меню стилей через inline"""
    if not update.message or not update.effective_user:
        return

    db = context.bot_data['db']
    user_id = update.effective_user.id
    photo_count = await db.get_user_photo_count(user_id)

    if photo_count < Config.MIN_PHOTOS:
        await update.message.reply_text(
            f"⚠️ *Сначала нужно загрузить фото!*\n\n"
            f"Загружено: {photo_count}\n"
            f"Минимум: {Config.MIN_PHOTOS}\n\n"
            f"Нажми кнопку «📤 Загрузить фото» внизу.",
            parse_mode='Markdown',
            reply_markup=get_main_menu_keyboard()
        )
        return

    # Показываем inline-меню со стилями (используем функцию из styles.py)
    from handlers.styles import show_styles_menu
    await show_styles_menu(update.message)

generate_handler = CommandHandler("generate", generate_command)

async def handle_style_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик выбора стиля из Reply-кнопок"""
    if not update.message or not update.effective_user:
        return
    
    # Проверяем, что мы действительно ждем выбора стиля
    if not context.user_data.get('waiting_for_style'):
        # Если не ждем стиль, игнорируем сообщение (оно попадет в другие обработчики)
        return
    
    text = update.message.text
    
    # Проверяем, не является ли это кнопкой главного меню
    if text in ["📤 Загрузить фото", "📸 Генерировать", "🖼️ Стили", "❓ Помощь", "🗑 Очистить селфи", "🏠 Главное меню"]:
        # Возвращаем управление - эти кнопки обработает другой handler
        context.user_data['waiting_for_style'] = False
        return
    
    # Ищем выбранный стиль
    selected_style = None
    selected_key = None
    for key, style in Config.STYLES.items():
        if text == f"🎨 {style['name']}":
            selected_style = style
            selected_key = key
            break
    
    if not selected_style:
        await update.message.reply_text(
            "Пожалуйста, выбери стиль из кнопок ниже 👇",
            reply_markup=get_styles_keyboard()
        )
        return
    
    # Очищаем состояние
    context.user_data['waiting_for_style'] = False
    
    # Получаем фото пользователя
    db = context.bot_data['db']
    user_id = update.effective_user.id
    photo_paths = await db.get_user_photos(user_id, "input")
    
    if not photo_paths:
        await update.message.reply_text(
            "❌ У тебя нет загруженных фото. Нажми «📤 Загрузить фото»",
            reply_markup=get_main_menu_keyboard()
        )
        return
    
    # Сообщаем о начале генерации
    await update.message.reply_text(
        f"🚀 *Генерация запущена!*\n\n"
        f"Стиль: {selected_style['name']}\n\n"
        f"⏳ Подожди 1-2 минуты...",
        parse_mode='Markdown'
    )

    try:
        # Здесь будет вызов AI Tunnel для генерации
        # Пока просто имитируем генерацию
        await update.message.reply_text(
            f"✅ *Готово!*\n\n"
            f"Вот твое фото в стиле {selected_style['name']}:",
            parse_mode='Markdown'
        )
        
        # Отправляем тестовое сообщение (замените на реальную генерацию)
        await update.message.reply_text("🖼️ [Здесь будет сгенерированное фото]")

    except Exception as e:
        logger.error(f"Ошибка генерации: {e}")
        await update.message.reply_text(
            f"❌ Ошибка при генерации: {str(e)}"
        )

    # Возвращаем главное меню
    await update.message.reply_text(
        "👇 *Главное меню*:",
        parse_mode='Markdown',
        reply_markup=get_main_menu_keyboard()
    )

generate_handler = CommandHandler("generate", generate_command)