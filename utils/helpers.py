import re
import base64
import logging
from telegram import Bot

logger = logging.getLogger(__name__)

async def send_photo_or_fallback(bot: Bot, chat_id: int, image_data: str, caption: str = ""):
    """
    Отправляет фото по base64, URL или простой текст.
    При ошибке отправляет сообщение об ошибке.
    """
    try:
        if image_data.startswith('data:image'):
            base64_str = re.sub('^data:image/.+;base64,', '', image_data)
            image_bytes = base64.b64decode(base64_str)
            await bot.send_photo(chat_id=chat_id, photo=image_bytes, caption=caption)
        elif image_data.startswith('http'):
            await bot.send_photo(chat_id=chat_id, photo=image_data, caption=caption)
        else:
            await bot.send_message(chat_id=chat_id, text=caption + "\n" + image_data)
    except Exception as e:
        logger.error(f"Ошибка отправки фото пользователю {chat_id}: {e}")
        await bot.send_message(chat_id=chat_id, text="❌ Не удалось отправить фото. Попробуйте позже.")

async def send_video_or_fallback(bot: Bot, chat_id: int, video_data: str | bytes, caption: str = ""):
    """
    Отправляет видео по URL, base64 или байтам.
    При ошибке отправляет сообщение об ошибке.
    """
    try:
        if isinstance(video_data, bytes):
            await bot.send_video(chat_id=chat_id, video=video_data, caption=caption)
        elif video_data.startswith('data:video'):
            base64_str = re.sub('^data:video/.+;base64,', '', video_data)
            video_bytes = base64.b64decode(base64_str)
            await bot.send_video(chat_id=chat_id, video=video_bytes, caption=caption)
        elif video_data.startswith('http'):
            await bot.send_video(chat_id=chat_id, video=video_data, caption=caption)
        else:
            await bot.send_message(chat_id=chat_id, text=caption + "\n" + video_data)
    except Exception as e:
        logger.error(f"Ошибка отправки видео пользователю {chat_id}: {e}")
        await bot.send_message(chat_id=chat_id, text="❌ Не удалось отправить видео. Попробуйте позже.")