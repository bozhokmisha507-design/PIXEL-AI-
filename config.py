import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    BOT_TOKEN = os.getenv("BOT_TOKEN", "")
    AITUNNEL_API_KEY = os.getenv("AITUNNEL_API_KEY", "")
    AITUNNEL_IMAGE_MODEL = os.getenv("AITUNNEL_IMAGE_MODEL", "gemini-2.5-flash-image")
    
    # ЮMoney (оставляем как есть – платёжка не сломается)
    YOOMONEY_ACCESS_TOKEN = os.getenv("YOOMONEY_ACCESS_TOKEN")
    YOOMONEY_WALLET = os.getenv("YOOMONEY_WALLET", "")
    PRICE_PER_GENERATION = 38
    YOOMONEY_NOTIFICATION_URL = os.getenv("YOOMONEY_NOTIFICATION_URL", "")
    UPLOAD_DIR = "uploads"
    OUTPUT_DIR = "outputs"
    
    MIN_PHOTOS = 2
    MAX_PHOTOS = 5
    RECOMMENDED_PHOTOS = 4
    
    # ВСЕ СТИЛИ (те, что были до подключения оплаты, с учётом гендера)
    STYLES = {
        "business": {
            "name": "💼 Бизнес портрет",
            "prompt": "professional corporate portrait of this person, wearing a tailored navy suit and white shirt, confident smile, modern glass office background with bokeh, dramatic studio lighting (Rembrandt lighting), 85mm lens, shallow depth of field, sharp focus on eyes, high-end fashion photography style, 8k, photorealistic, face clearly visible",
            "count": 1
        },
        "fashion": {
            "name": "👗 Fashion/Глянец",
            "prompt": "high fashion editorial photo of this person, vogue magazine style, studio lighting, glamorous, professional photography, 8k, face clearly visible",
            "count": 1
        },
        "casual": {
            "name": "😊 Casual/Повседневный",
            "prompt": "natural lifestyle photo of this person, casual outfit, golden hour, candid photography, warm tones, bokeh background, 8k, face clearly visible",
            "count": 1
        },
        "creative": {
            "name": "🎨 Креативный/Арт",
            "prompt": "artistic creative portrait of this person, dramatic lighting, cinematic color grading, fantasy elements, digital art style, 8k, face clearly visible",
            "count": 1
        },
        "fitness": {
            "name": "💪 Фитнес",
            "prompt": "fitness lifestyle photo of this person, athletic wear, gym background, dynamic pose, professional sports photography, 8k, face clearly visible",
            "count": 1
        },
        "travel": {
            "name": "✈️ Путешествия",
            "prompt": "travel photography of this person, beautiful landscape background, adventure style, natural lighting, wanderlust aesthetic, 8k, face clearly visible",
            "count": 1
        },
        "dating": {
            "name": "❤️ Для знакомств",
            "prompt": "attractive dating profile photo of this person, warm smile, flattering angle, soft natural lighting, approachable, 8k, face clearly visible",
            "count": 1
        },
        "snowboard": {
            "name": "🏂 На сноуборде",
            "prompt": "action shot of this person snowboarding in summer outfit, wearing shorts, holding a cocktail, no helmet, face clearly visible, bright sunny day, professional sports photography, 8k",
            "count": 1
        },
        "club": {
            "name": "🪩 Клубный",
            "prompt": "nightclub party photo of this person, neon lights, laser beams, energetic atmosphere, stylish club outfit, dance floor background, professional nightlife photography, 8k, face clearly visible",
            "count": 1
        },
        "bare_chest": {
            "name": "💪 Голый торс",
            "prompt": "professional fitness photoshoot of this person with bare chest, muscular physique, athletic body, studio lighting, gym background, dramatic shadows, high quality, 8k, face clearly visible, masculine pose",
            "count": 1
        },
        "lookbook": {
            "name": "📸 Лук бук",
            "prompt": "fashion lookbook photo of this person, street style outfit, urban background, model pose, professional fashion photography, natural lighting, high quality, 8k, face clearly visible, full body shot",
            "count": 1
        },
        "yacht": {
            "name": "🛥️ На яхте с лимонадом",
            "prompt": "luxury yacht photo of this person, holding a glass of lemonade, relaxing on deck, ocean background, sunny day, white outfit, sunglasses, vacation lifestyle, professional photography, 8k, face clearly visible",
            "count": 1
        }
    }
    
    @classmethod
    def ensure_dirs(cls):
        os.makedirs(cls.UPLOAD_DIR, exist_ok=True)
        os.makedirs(cls.OUTPUT_DIR, exist_ok=True)