import re
import base64
import logging
from telegram import Bot

logger = logging.getLogger(__name__)

async def send_photo_or_fallback(bot: Bot, chat_id: int, image_data: str, caption: str = ""):
    """
    Универсальная отправка фото: принимает base64, URL или текст.
    В случае ошибки отправляет сообщение об ошибке.
    """
    try:
        if image_data.startswith('data:image'):
            # Base64 изображение
            base64_str = re.sub('^data:image/.+;base64,', '', image_data)
            image_bytes = base64.b64decode(base64_str)
            await bot.send_photo(chat_id=chat_id, photo=image_bytes, caption=caption)
        elif image_data.startswith('http'):
            # Ссылка на изображение
            await bot.send_photo(chat_id=chat_id, photo=image_data, caption=caption)
        else:
            # Текстовый ответ (например, ошибка)
            await bot.send_message(chat_id=chat_id, text=caption + "\n" + image_data)
    except Exception as e:
        logger.error(f"Ошибка отправки фото пользователю {chat_id}: {e}")
        await bot.send_message(chat_id=chat_id, text="❌ Не удалось отправить фото. Попробуйте позже.")