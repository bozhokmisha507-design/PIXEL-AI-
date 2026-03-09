import os
import base64
import logging
import aiohttp
import asyncio
from config import Config

logger = logging.getLogger(__name__)

class AITunnelService:
    def __init__(self, model_type: str = "gemini", quality: str = "medium", size: str = "1536x1024"):
        self.api_key = Config.AITUNNEL_API_KEY
        self.base_url = "https://api.aitunnel.ru/v1"
        self.model_type = model_type
        self.quality = quality
        self.size = size  # для GPT Image горизонтальный формат

    async def generate_photos(self, user_photo_paths: list, style_key: str, num_images: int = 1, gender=None) -> list:
        style = Config.STYLES.get(style_key)
        if not style:
            raise ValueError(f"Unknown style: {style_key}")

        base_prompt = style["prompt"]

        # ---------- ГЕНДЕРНАЯ АДАПТАЦИЯ ----------
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
        elif style_key == "artistic_bw":
            if gender == 'male':
                prompt = (
                    "dramatic high-contrast black and white portrait of this man, "
                    "strong chiaroscuro lighting, deep shadows, silver gelatin print aesthetic, "
                    "heavily stylized fine art photography, expressive mood, "
                    "8k, photorealistic, face clearly visible"
                )
            elif gender == 'female':
                prompt = (
                    "dramatic high-contrast black and white portrait of this woman, "
                    "strong chiaroscuro lighting, deep shadows, silver gelatin print aesthetic, "
                    "heavily stylized fine art photography, expressive mood, "
                    "8k, photorealistic, face clearly visible"
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

        # Добавляем указание на горизонтальный формат для Gemini
        if self.model_type == "gemini":
            prompt += " Landscape orientation, horizontal composition, aspect ratio 16:9, wide format."

        logger.info(f"Генерация фото в стиле {style_key} через {self.model_type}, промпт: {prompt[:100]}...")

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

        results = []
        if self.model_type == "gemini":
            # ---------- Gemini через chat/completions ----------
            try:
                with open(ref_photo_path, "rb") as f:
                    image_data = base64.b64encode(f.read()).decode("utf-8")
                    data_url = f"data:image/jpeg;base64,{image_data}"
            except Exception as e:
                logger.error(f"❌ Ошибка кодирования фото: {e}")
                return []

            for i in range(num_images):
                try:
                    async with aiohttp.ClientSession() as session:
                        headers = {
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json"
                        }
                        payload = {
                            "model": Config.AITUNNEL_IMAGE_MODEL,
                            "messages": [
                                {
                                    "role": "user",
                                    "content": [
                                        {"type": "image_url", "image_url": {"url": data_url}},
                                        {"type": "text", "text": f"Сгенерируй фото на основе этого человека: {prompt}"}
                                    ]
                                }
                            ],
                            "modalities": ["image", "text"],
                            "max_tokens": 1000
                        }
                        async with session.post(
                            f"{self.base_url}/chat/completions",
                            headers=headers,
                            json=payload,
                            timeout=aiohttp.ClientTimeout(total=60)
                        ) as resp:
                            if resp.status == 200:
                                result = await resp.json()
                                if 'choices' in result and result['choices']:
                                    message = result['choices'][0].get('message', {})
                                    if 'images' in message:
                                        for img in message['images']:
                                            if 'image_url' in img and 'url' in img['image_url']:
                                                results.append(img['image_url']['url'])
                                    elif 'content' in message and message['content'].startswith('data:image'):
                                        results.append(message['content'])
                                    else:
                                        logger.warning("⚠️ Нет изображения в ответе")
                            else:
                                error_text = await resp.text()
                                logger.error(f"❌ Ошибка Gemini: {resp.status}")
                except Exception as e:
                    logger.error(f"❌ Ошибка генерации Gemini: {e}", exc_info=True)
        else:
            # ---------- GPT Image через /images/edits ----------
            for i in range(num_images):
                try:
                    async with aiohttp.ClientSession() as session:
                        form_data = aiohttp.FormData()
                        form_data.add_field('model', 'gpt-image-1.5')
                        with open(ref_photo_path, 'rb') as f:
                            image_bytes = f.read()
                        form_data.add_field('image[]', image_bytes, filename='photo.jpg', content_type='image/jpeg')
                        form_data.add_field('prompt', prompt)
                        form_data.add_field('quality', self.quality)
                        form_data.add_field('size', self.size)
                        form_data.add_field('n', str(num_images))

                        headers = {
                            "Authorization": f"Bearer {self.api_key}"
                        }
                        async with session.post(
                            f"{self.base_url}/images/edits",
                            headers=headers,
                            data=form_data
                        ) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                if 'data' in data:
                                    for item in data['data']:
                                        if 'b64_json' in item:
                                            results.append(f"data:image/png;base64,{item['b64_json']}")
                                        elif 'url' in item:
                                            results.append(item['url'])
                            else:
                                error_text = await resp.text()
                                logger.error(f"❌ Ошибка GPT Image: {resp.status} - {error_text}")
                except Exception as e:
                    logger.error(f"❌ Ошибка при генерации GPT Image: {e}", exc_info=True)

        logger.info(f"✅ Генерация завершена, получено {len(results)} фото")
        return results

    # ---------- НОВЫЙ МЕТОД ДЛЯ ПАРНОЙ ГЕНЕРАЦИИ ----------
    async def generate_couple_photo(self, male_photo_path: str, female_photo_path: str, prompt: str, num_images: int = 1) -> list:
        """
        Генерация парного фото на основе двух референсных изображений (мужчины и женщины).
        Использует ту же модель (gemini), но передаёт оба изображения в запрос.
        """
        try:
            with open(male_photo_path, "rb") as f:
                male_data = base64.b64encode(f.read()).decode("utf-8")
                male_url = f"data:image/jpeg;base64,{male_data}"
            with open(female_photo_path, "rb") as f:
                female_data = base64.b64encode(f.read()).decode("utf-8")
                female_url = f"data:image/jpeg;base64,{female_data}"
        except Exception as e:
            logger.error(f"❌ Ошибка кодирования фото для парной генерации: {e}")
            return []

        results = []
        for i in range(num_images):
            try:
                async with aiohttp.ClientSession() as session:
                    headers = {
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    }
                    payload = {
                        "model": Config.AITUNNEL_IMAGE_MODEL,
                        "messages": [
                            {
                                "role": "user",
                                "content": [
                                    {"type": "image_url", "image_url": {"url": male_url}},
                                    {"type": "image_url", "image_url": {"url": female_url}},
                                    {"type": "text", "text": prompt}
                                ]
                            }
                        ],
                        "modalities": ["image", "text"],
                        "max_tokens": 1000
                    }
                    async with session.post(
                        f"{self.base_url}/chat/completions",
                        headers=headers,
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=60)
                    ) as resp:
                        if resp.status == 200:
                            result = await resp.json()
                            if 'choices' in result and result['choices']:
                                message = result['choices'][0].get('message', {})
                                if 'images' in message:
                                    for img in message['images']:
                                        if 'image_url' in img and 'url' in img['image_url']:
                                            results.append(img['image_url']['url'])
                                        elif 'b64_json' in img:
                                            results.append(f"data:image/png;base64,{img['b64_json']}")
                                elif 'content' in message and message['content'].startswith('data:image'):
                                    results.append(message['content'])
                                else:
                                    logger.warning("⚠️ Нет изображения в ответе")
                            else:
                                logger.error("❌ Нет choices в ответе")
                        else:
                            error_text = await resp.text()
                            logger.error(f"❌ Ошибка Gemini при парной генерации: {resp.status} - {error_text}")
            except Exception as e:
                logger.error(f"❌ Ошибка при парной генерации: {e}", exc_info=True)

        logger.info(f"✅ Парная генерация завершена, получено {len(results)} фото")
        return results

    @staticmethod
    def _encode_image(image_path: str) -> str:
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")