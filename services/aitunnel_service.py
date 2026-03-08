import os
import base64
import logging
import aiohttp
import asyncio
import json
from config import Config

logger = logging.getLogger(__name__)

class AITunnelService:
    def __init__(self):
        self.api_key = Config.AITUNNEL_API_KEY
        self.base_url = "https://api.aitunnel.ru/v1"
        self.image_model = Config.AITUNNEL_IMAGE_MODEL

    async def generate_photos(self, user_photo_paths: list, style_key: str, num_images: int = 1, gender=None) -> list:
        style = Config.STYLES.get(style_key)
        if not style:
            raise ValueError(f"Unknown style: {style_key}")

        base_prompt = style["prompt"]

        # Специальная обработка для стилей, требующих гендерной адаптации
        if style_key == "bare_chest":
            if gender == 'male':
                prompt = "professional fitness portrait of this man, showing muscular athletic physique, six-pack abs visible, gym background, dramatic lighting, 8k, face clearly visible"
            elif gender == 'female':
                prompt = "professional fitness portrait of this woman, wearing a sports bra, showing fit feminine physique, toned body, gym background, soft lighting, 8k, face clearly visible, photorealistic"
            else:
                prompt = base_prompt.replace("{token}", "this person")

        elif style_key == "evening_suit":
            if gender == 'male':
                prompt = "elegant evening suit portrait of this man in a classic tuxedo or formal suit, red carpet or luxurious interior background, sophisticated lighting, sharp focus, high-end fashion photography, 8k, photorealistic, face clearly visible, confident pose"
            elif gender == 'female':
                prompt = "glamorous evening gown portrait of this woman, wearing a stunning evening dress, high heels, holding a glass of wine, luxurious ballroom or red carpet background, sophisticated lighting, 8k, photorealistic, professional retouching, face clearly visible, elegant pose"
            else:
                prompt = base_prompt.replace("{token}", "this person")

        elif style_key == "business":
            if gender == 'male':
                prompt = base_prompt.replace("{token}", "this man")
            elif gender == 'female':
                prompt = (
                    "professional confident business portrait of this woman, wearing a stylish blue fitted jacket "
                    "and a pencil skirt or tailored dress, professional makeup with red lips, elegant modern office background, "
                    "corporate atmosphere, sharp studio lighting, 8k, photorealistic, professional retouching, face clearly visible"
                )
            else:
                prompt = base_prompt.replace("{token}", "this person")

        # 🔥 НОВЫЙ СТИЛЬ – Студийная съемка
        elif style_key == "editorial_studio":
            if gender == 'male':
                prompt = (
                    "Hyper-realistic studio photography on a beige background, cinematic bright expensive lighting, "
                    "sitting on a soft ottoman in full length, wearing white shoes, light jeans, and a light gray unbuttoned shirt, "
                    "like in a high-end fashion magazine, 8k, photorealistic, face clearly visible, professional retouching"
                )
            elif gender == 'female':
                prompt = (
                    "Hyper-realistic studio photography on a beige background, cinematic bright expensive lighting, "
                    "sitting on a soft ottoman, full body or close-up, wearing beige shoes and a powder-colored dress, "
                    "sometimes holding a bouquet of large white roses, like in a high-end fashion magazine, 8k, photorealistic, "
                    "face clearly visible, professional retouching, varied composition"
                )
            else:
                prompt = base_prompt.replace("{token}", "this person")

        else:
            # Для всех остальных стилей просто подставляем правильное обращение
            if gender == 'male':
                subject = "this man"
            elif gender == 'female':
                subject = "this woman"
            else:
                subject = "this person"
            prompt = base_prompt.replace("{token}", subject)

        logger.info(f"Генерация фото в стиле {style_key}, промпт: {prompt[:100]}...")

        if not user_photo_paths:
            logger.error("❌ Список фото пользователя пуст")
            return []

        # Находим первый существующий файл
        ref_photo_path = None
        for path in user_photo_paths:
            if os.path.exists(path):
                ref_photo_path = path
                logger.info(f"✅ Используем референс фото: {ref_photo_path}")
                break
            else:
                logger.warning(f"⚠️ Файл не найден: {path}")

        if not ref_photo_path:
            logger.error("❌ Ни одно из фото пользователя не найдено на диске")
            return []

        try:
            with open(ref_photo_path, "rb") as f:
                image_data = base64.b64encode(f.read()).decode("utf-8")
                data_url = f"data:image/jpeg;base64,{image_data}"
                logger.info(f"📸 Фото закодировано, размер: {len(image_data)} символов")
        except Exception as e:
            logger.error(f"❌ Ошибка кодирования фото {ref_photo_path}: {e}")
            return []

        results = []
        for i in range(num_images):
            try:
                logger.info(f"📤 Отправка запроса к AI Tunnel (Gemini 2.5 Flash Image) для фото #{i+1}")

                async with aiohttp.ClientSession() as session:
                    headers = {
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    }

                    payload = {
                        "model": self.image_model,
                        "messages": [
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "image_url",
                                        "image_url": {
                                            "url": data_url
                                        }
                                    },
                                    {
                                        "type": "text",
                                        "text": f"Сгенерируй фото на основе этого человека: {prompt}"
                                    }
                                ]
                            }
                        ],
                        "modalities": ["image", "text"],
                        "max_tokens": 1000
                    }

                    timeout_obj = aiohttp.ClientTimeout(total=60)
                    async with session.post(
                        f"{self.base_url}/chat/completions",
                        headers=headers,
                        json=payload,
                        timeout=timeout_obj
                    ) as response:
                        if response.status == 200:
                            result = await response.json()
                            logger.info(f"📩 Ответ от Gemini API получен")

                            if 'choices' in result and len(result['choices']) > 0:
                                message = result['choices'][0].get('message', {})

                                if 'images' in message:
                                    for img in message['images']:
                                        if 'image_url' in img and 'url' in img['image_url']:
                                            image_url = img['image_url']['url']
                                            results.append(image_url)
                                            logger.info(f"🖼️ Получено изображение: {image_url[:50]}...")

                                elif 'content' in message and message['content']:
                                    content = message['content']
                                    if content.startswith('data:image') or len(content) > 1000:
                                        results.append(content)
                                        logger.info("📦 Получено base64 изображение в content")
                                    else:
                                        logger.warning(f"⚠️ Получен текст вместо изображения: {content[:100]}")
                                else:
                                    logger.warning("⚠️ Нет изображения в ответе")
                            else:
                                logger.error("❌ Нет choices в ответе")
                        else:
                            error_text = await response.text()
                            logger.error(f"❌ Ошибка Gemini API: {response.status}")

            except asyncio.TimeoutError:
                logger.error(f"⏰ Таймаут при генерации фото #{i+1}")
            except Exception as e:
                logger.error(f"❌ Ошибка при генерации фото #{i+1}: {e}", exc_info=True)

        logger.info(f"✅ Генерация завершена, получено {len(results)} фото")
        return results

    @staticmethod
    def _encode_image(image_path: str) -> str:
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")