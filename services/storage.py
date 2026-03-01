import os
import shutil
import aiohttp
from config import Config

class StorageService:
    @staticmethod
    async def save_telegram_photo(bot, file_id: str, user_id: int, photo_num: int) -> str:
        user_dir = os.path.join(Config.UPLOAD_DIR, str(user_id))
        os.makedirs(user_dir, exist_ok=True)
        
        file = await bot.get_file(file_id)
        file_path = os.path.join(user_dir, f"photo_{photo_num}.jpg")
        await file.download_to_drive(file_path)
        return file_path

    @staticmethod
    async def save_generated_photo(image_url: str, user_id: int, style_key: str, index: int) -> str:
        user_dir = os.path.join(Config.OUTPUT_DIR, str(user_id), style_key)
        os.makedirs(user_dir, exist_ok=True)
        
        file_path = os.path.join(user_dir, f"{style_key}_{index}.png")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(image_url) as resp:
                if resp.status == 200:
                    with open(file_path, 'wb') as f:
                        f.write(await resp.read())
        return file_path

    @staticmethod
    def cleanup_user_uploads(user_id: int) -> None:
        user_dir = os.path.join(Config.UPLOAD_DIR, str(user_id))
        if os.path.exists(user_dir):
            shutil.rmtree(user_dir)
        os.makedirs(user_dir, exist_ok=True)