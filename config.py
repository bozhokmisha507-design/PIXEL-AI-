import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    BOT_TOKEN = os.getenv("BOT_TOKEN", "")
    AITUNNEL_API_KEY = os.getenv("AITUNNEL_API_KEY", "")
    AITUNNEL_IMAGE_MODEL = os.getenv("AITUNNEL_IMAGE_MODEL", "gemini-2.5-flash-image")
    
    # Новые переменные для ЮMoney
    YOOMONEY_ACCESS_TOKEN = os.getenv("YOOMONEY_ACCESS_TOKEN")
    YOOMONEY_WALLET = os.getenv("YOOMONEY_WALLET", "")  # номер вашего кошелька
    PRICE_PER_GENERATION = 38  # стоимость одной генерации в рублях
    
    UPLOAD_DIR = "uploads"
    OUTPUT_DIR = "outputs"
    
    MIN_PHOTOS = 2
    MAX_PHOTOS = 5
    RECOMMENDED_PHOTOS = 4
    
    # ВСЕ СТИЛИ (старые + новые)
    STYLES = {
        # ... (без изменений, оставил как у вас)
    }
    
    @classmethod
    def ensure_dirs(cls):
        os.makedirs(cls.UPLOAD_DIR, exist_ok=True)
        os.makedirs(cls.OUTPUT_DIR, exist_ok=True)