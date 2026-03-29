import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    BOT_TOKEN = os.getenv("BOT_TOKEN", "")
    AITUNNEL_API_KEY = os.getenv("AITUNNEL_API_KEY", "")
    AITUNNEL_IMAGE_MODEL = os.getenv("AITUNNEL_IMAGE_MODEL", "gemini-3.1-flash-image-preview")

    # ЮMoney
    YOOMONEY_ACCESS_TOKEN = os.getenv("YOOMONEY_ACCESS_TOKEN")
    YOOMONEY_WALLET = os.getenv("YOOMONEY_WALLET", "")
    PRICE_PER_GENERATION = 38          # базовая цена (Gemini)
    PRICE_PREMIUM = 76                  # премиум цена (GPT Image High)
    PRICE_NANOBANANA = 75                # цена для Nano Banana Pro (одиночные фото)
    PRICE_20_TOKENS = 700                # пакет 20 жетонов
    # Парные фото теперь генерируются через Nano Banana Pro (премиум-качество)
    COUPLE_PRICE = 75                     # цена парной генерации
    COUPLE_TOKEN_COST = 2                  # стоимость в жетонах для пар

    # Стоимость в жетонах для одиночных генераций
    TOKEN_COST_GEMINI = 1
    TOKEN_COST_GPT = 2
    TOKEN_COST_NANOBANANA = 2

    # Telegram Payments (на будущее)
    PAYMENT_PROVIDER_TOKEN = os.getenv("PAYMENT_PROVIDER_TOKEN", "")

    # Папки для загрузки и вывода – используем общее хранилище, если доступно
    SHARED_DIR = os.getenv("SHARED_DIR", "/app/shared")
    UPLOAD_DIR = os.path.join(SHARED_DIR, "uploads")
    OUTPUT_DIR = os.path.join(SHARED_DIR, "outputs")

    MIN_PHOTOS = 2
    MAX_PHOTOS = 5
    RECOMMENDED_PHOTOS = 4

    # ==================== ВСЕ СТИЛИ ====================
    STYLES = {
        # 🔥 Студийная съемка – первый
        "editorial_studio": {
            "name": "📸 Студийная съемка",
            "prompt": "placeholder",
            "count": 1
        },
        "business": {
            "name": "💼 Уверенный бизнес-костюм",
            "prompt": "confident corporate portrait of {token}, wearing a sharp tailored navy business suit, white shirt, and silk tie, standing with arms crossed, modern office background with bokeh, dramatic studio lighting, 85mm lens, shallow depth of field, sharp focus on eyes, high-end fashion photography, 8k, photorealistic, face clearly visible",
            "count": 1
        },
        "fashion": {
            "name": "👗 Fashion/Глянец",
            "prompt": "high fashion editorial photo of {token}, vogue magazine style, studio lighting, glamorous, professional photography, 8k, face clearly visible",
            "count": 1
        },
        "casual": {
            "name": "😊 Повседневный",
            "prompt": "natural lifestyle photo of {token}, casual outfit, golden hour, candid photography, warm tones, bokeh background, 8k, face clearly visible",
            "count": 1
        },
        "creative": {
            "name": "🎨 Креативный/Арт",
            "prompt": "artistic creative portrait of {token}, dramatic lighting, cinematic color grading, fantasy elements, digital art style, 8k, face clearly visible",
            "count": 1
        },
        "fitness": {
            "name": "💪 Спортивный",
            "prompt": "dynamic fitness portrait of {token} in athletic wear, gym background with equipment, intense workout pose, professional sports photography, dramatic lighting, 8k, photorealistic, face clearly visible, muscular definition",
            "count": 1
        },
        "travel": {
            "name": "✈️ Путешествия",
            "prompt": "travel photography of {token}, beautiful landscape background, adventure style, natural lighting, wanderlust aesthetic, 8k, face clearly visible",
            "count": 1
        },
        "dating": {
            "name": "❤️ Для знакомств",
            "prompt": "attractive dating profile photo of {token}, warm smile, flattering angle, soft natural lighting, approachable, 8k, face clearly visible",
            "count": 1
        },
        "snowboard": {
            "name": "🏂 На сноуборде",
            "prompt": "action shot of {token} snowboarding in summer outfit, wearing shorts and a tank top, holding a colorful cocktail, no helmet, face clearly visible, bright sunny day, professional sports photography, 8k, photorealistic, dynamic pose, mountain background",
            "count": 1
        },
        "club": {
            "name": "🪩 Клубный",
            "prompt": "nightclub party photo of {token}, neon lights, laser beams, energetic atmosphere, stylish club outfit, dance floor background, professional nightlife photography, 8k, face clearly visible",
            "count": 1
        },
        "bare_chest": {
            "name": "💪 Голый торс",
            "prompt": "professional fitness photoshoot of this person with bare chest, muscular physique, athletic body, studio lighting, gym background, dramatic shadows, high quality, 8k, face clearly visible, masculine pose",
            "count": 1
        },
        "lookbook": {
            "name": "📸 Лук бук",
            "prompt": "fashion lookbook photo of {token}, street style outfit, urban background, model pose, professional fashion photography, natural lighting, high quality, 8k, face clearly visible, full body shot",
            "count": 1
        },
        "yacht": {
            "name": "🛥️ На яхте",
            "prompt": "luxury lifestyle portrait of {token} on a yacht, wearing elegant white outfit and sunglasses, relaxing on deck with ocean background, sunny day, champagne or lemonade in hand, vacation vibe, professional photography, 8k, photorealistic, face clearly visible, stylish sunglasses",
            "count": 1
        },
        "mounter": {
            "name": "👷‍♂️ Рабочий-монтажник",
            "prompt": "professional photo of {token} as a skilled construction worker or rigger, wearing a yellow or orange hard hat, reflective safety vest, work gloves, and a full-body safety harness with lanyards. The setting is either high up on a towering construction crane with a city view far below, or on a construction site with steel beams and machinery. In one hand, {token} holds a large heavy-duty wrench (size 55) confidently. The image should be photorealistic, high detail, dramatic lighting (golden hour or industrial lighting), shallow depth of field, sharp focus on the face and the tool, 8k, professional photography style, face clearly visible.",
            "count": 1
        },
        "streetstyle": {
            "name": "🧥 Уличный стиль",
            "prompt": "stylish streetwear portrait of {token}, wearing trendy casual clothes like a hoodie, denim jacket, or graphic tee, urban background with graffiti, natural lighting, candid attitude, edgy style, professional photography, 8k, photorealistic, face clearly visible",
            "count": 1
        },
        "summer_vacation": {
            "name": "☀️ Летний отпуск",
            "prompt": "vacation lifestyle photo of {token}, wearing summer outfit like linen shirt and shorts, sunglasses, beach or tropical resort background, sunny day, relaxed mood, vibrant colors, professional photography, 8k, photorealistic, face clearly visible",
            "count": 1
        },
        "artistic_bw": {
            "name": "🎨 Ч/б портрет",
            "prompt": "artistic black and white portrait of {token}, dramatic lighting, high contrast, expressive eyes, minimalist background, fine art photography style, 8k, photorealistic, face clearly visible, emotional expression",
            "count": 1
        },
        "evening_suit": {
            "name": "🤵 Вечерний костюм",
            "prompt": "elegant evening suit portrait of {token} in a classic tuxedo or formal suit, red carpet or luxurious interior background, sophisticated lighting, sharp focus, high-end fashion photography, 8k, photorealistic, face clearly visible, confident pose",
            "count": 1
        },
        "cyberpunk_sunset": {
            "name": "🌆 Киберпанк на закате",
            "prompt": "ultra-modern cyberpunk portrait of {token} at sunset, warm golden and pink sky contrasting with neon lights, holographic elements, futuristic cityscape with skyscrapers, glowing accessories, vibrant purple and blue tones, high-tech atmosphere, 8k, photorealistic, professional retouching, face clearly visible, magazine cover quality",
            "count": 1
        },
        "fantasy_elf": {
            "name": "🧝 Фэнтези эльф",
            "prompt": "fantasy portrait of {token} as an elegant elf, pointed ears, ethereal glowing skin, mystical forest background with sparkling lights, intricate armor or robes, magical atmosphere, dramatic lighting, 8k, photorealistic, high fashion fantasy art, face clearly visible",
            "count": 1
        },
        "retro_80s": {
            "name": "📼 Ретро 80-е",
            "prompt": "vibrant retro 1980s style portrait of {token}, neon colors, big hair, vintage sunglasses, cassette tape or boombox in background, retro arcade lights, bold patterns, 8k, photorealistic, professional retouching, authentic 80s vibe, face clearly visible",
            "count": 1
        },
        "extreme_sport": {
            "name": "🏄 Экстрим",
            "prompt": "dynamic action shot of {token} doing extreme sport like surfing, skateboarding, or motocross, dramatic motion blur, sunset or industrial background, energetic pose, professional sports photography, 8k, photorealistic, face clearly visible, intense expression",
            "count": 1
        },
        "old_hollywood": {
            "name": "🎬 Старый Голливуд",
            "prompt": "glamorous black and white portrait of {token} in old Hollywood style, classic vintage suit or dress, soft dramatic lighting, film noir aesthetic, elegant pose, luxurious background, 8k, photorealistic, professional retouching, timeless elegance, face clearly visible",
            "count": 1
        },
        "space_tourist": {
            "name": "🚀 Космический турист",
            "prompt": "futuristic portrait of {token} as a space tourist, wearing a stylish modern spacesuit with neon accents, floating in zero gravity inside a high-tech spaceship with Earth visible through window, vibrant galaxy colors, 8k, photorealistic, professional retouching, face clearly visible through helmet",
            "count": 1
        },
        "androgynous": {
            "name": "🌀 Андрогинная мода",
            "prompt": "high fashion androgynous portrait of {token}, blending masculine and feminine elements, avant-garde designer clothing, minimalist studio background with geometric shapes, sharp lighting, editorial style, 8k, photorealistic, professional retouching, face clearly visible",
            "count": 1
        },
        "beach_sunset": {
            "name": "🌅 Пляжный закат",
            "prompt": "romantic sunset portrait of {token} on the beach, golden hour lighting, warm orange and pink sky, ocean waves, relaxed vacation outfit, barefoot in sand, soft bokeh, 8k, photorealistic, professional retouching, face clearly visible, serene expression",
            "count": 1
        },
        "urban_chic": {
            "name": "🏙️ Урбанистический шик",
            "prompt": "sophisticated urban portrait of {token} in a modern cityscape at night, wearing high-end designer streetwear, reflections in glass buildings, neon signs, moody atmosphere, cinematic lighting, 8k, photorealistic, professional retouching, face clearly visible",
            "count": 1
        },
        "cyborg": {
            "name": "⚙️ Киборг",
            "prompt": "ultra-detailed futuristic cyborg portrait of {token}, half human half machine, glowing cybernetic implants, metallic textures, holographic interface elements, dark industrial background with neon lights, 8k, photorealistic, professional retouching, face clearly visible",
            "count": 1
        },
        "boho_style": {
            "name": "🌸 Бохо-шик",
            "prompt": "free-spirited bohemian portrait of {token}, wearing flowy floral dress or linen shirt, flower crown, natural makeup, sun flare effect, meadow or forest background, warm earthy tones, 8k, photorealistic, professional retouching, face clearly visible",
            "count": 1
        },
        "minimalist": {
            "name": "⬜ Минимализм",
            "prompt": "clean minimalist portrait of {token}, simple white or pastel background, sharp contrast, geometric composition, modern fashion clothing, soft diffused lighting, 8k, photorealistic, professional retouching, face clearly visible, editorial style",
            "count": 1
        },
        "steampunk": {
            "name": "⚙️ Стимпанк",
            "prompt": "steampunk portrait of {token} with Victorian era clothing, brass goggles, mechanical accessories, gears and cogs, vintage industrial background with steam, warm sepia and bronze tones, 8k, photorealistic, professional retouching, face clearly visible",
            "count": 1
        },
        "red_carpet": {
            "name": "🌟 Красная дорожка",
            "prompt": "glamorous red carpet portrait of {token} in stunning evening gown or tuxedo, sparkling jewelry, paparazzi flashes, luxurious hotel lobby or event background, confident pose, 8k, photorealistic, professional retouching, face clearly visible, celebrity style",
            "count": 1
        },
        "forest_spirit": {
            "name": "🌲 Лесной дух",
            "prompt": "ethereal portrait of {token} as a forest spirit, natural makeup with leaves and vines, glowing skin, mystical forest with sun rays filtering through trees, soft focus, magical atmosphere, 8k, photorealistic, professional retouching, face clearly visible",
            "count": 1
        },
    }

    # Список администраторов (из переменной окружения или значения по умолчанию)
    ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "955206480,5063386675").split(",") if x.strip()]

    @classmethod
    def ensure_dirs(cls):
        os.makedirs(cls.UPLOAD_DIR, exist_ok=True)
        os.makedirs(cls.OUTPUT_DIR, exist_ok=True)