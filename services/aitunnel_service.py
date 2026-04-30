import os
import base64
import logging
import aiohttp
import asyncio
import json
from PIL import Image
import io
from config import Config
from typing import Optional

logger = logging.getLogger(__name__)

class AITunnelService:
    # Константы тайм-аутов (в секундах)
    TIMEOUT_GEMINI = 90
    TIMEOUT_GPT = 90
    TIMEOUT_NANOBANANA = 180
    TIMEOUT_COUPLE = 180
    TIMEOUT_VIDEO_CREATE = 180   # создание видео
    TIMEOUT_VIDEO_POLL = 300     # ожидание готовности видео (макс. 5 минут)

    def __init__(self, model_type: str = "gemini", quality: str = "medium", size: str = "1536x1024"):
        self.api_key = Config.AITUNNEL_API_KEY
        self.base_url = "https://api.aitunnel.ru/v1"
        self.model_type = model_type
        self.quality = quality
        self.size = size  # для GPT Image горизонтальный формат

    # ---------- Вспомогательный метод для повторных попыток (JSON) ----------
    async def _post_with_retry(self, session, url, headers, json_payload, timeout, retries=2):
        """
        Выполняет POST-запрос с повторными попытками при ошибках сети/тайм-ауте.
        Возвращает обработанный ответ (JSON) или None.
        """
        delay = 1.5
        for attempt in range(retries + 1):
            try:
                async with session.post(url, headers=headers, json=json_payload, timeout=timeout) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    else:
                        error_text = await resp.text()
                        logger.error(f"Попытка {attempt+1}: HTTP {resp.status} - {error_text[:200]}")
                        if attempt == retries:
                            return None
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                logger.error(f"Попытка {attempt+1} не удалась: {type(e).__name__}: {e}")
                if attempt == retries:
                    raise
                await asyncio.sleep(delay)
                delay *= 2
        return None

    # ---------- Одиночные фото (Gemini, GPT, Nano Banana) ----------
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
            if gender == 'male':
                subject = "this man"
            elif gender == 'female':
                subject = "this woman"
            else:
                subject = "this person"
            prompt = base_prompt.replace("{token}", subject)

        # Добавляем указание на горизонтальный формат
        if self.model_type in ["gemini", "nanobanana"]:
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
                        # Используем повторные попытки
                        result = await self._post_with_retry(
                            session,
                            f"{self.base_url}/chat/completions",
                            headers,
                            payload,
                            aiohttp.ClientTimeout(total=self.TIMEOUT_GEMINI),
                            retries=2
                        )
                        if result and 'choices' in result and result['choices']:
                            message = result['choices'][0].get('message', {})
                            if 'images' in message:
                                for img in message['images']:
                                    if 'image_url' in img and 'url' in img['image_url']:
                                        results.append(img['image_url']['url'])
                            elif 'content' in message and message['content'].startswith('data:image'):
                                results.append(message['content'])
                            else:
                                logger.warning("⚠️ Нет изображения в ответе Gemini")
                        else:
                            logger.error(f"Ошибка Gemini: ответ пуст или некорректен")
                except Exception as e:
                    logger.error(f"❌ Ошибка генерации Gemini после всех попыток: {e}", exc_info=True)

        elif self.model_type == "gpt":
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

                        headers = {"Authorization": f"Bearer {self.api_key}"}
                        # Для form-data тоже добавим retry вручную
                        for attempt in range(3):
                            try:
                                async with session.post(
                                    f"{self.base_url}/images/edits",
                                    headers=headers,
                                    data=form_data,
                                    timeout=aiohttp.ClientTimeout(total=self.TIMEOUT_GPT)
                                ) as resp:
                                    if resp.status == 200:
                                        data = await resp.json()
                                        if 'data' in data:
                                            for item in data['data']:
                                                if 'b64_json' in item:
                                                    results.append(f"data:image/png;base64,{item['b64_json']}")
                                                elif 'url' in item:
                                                    results.append(item['url'])
                                        break  # успех, выходим из retry
                                    else:
                                        error_text = await resp.text()
                                        logger.error(f"Попытка {attempt+1}: GPT ошибка {resp.status} - {error_text[:200]}")
                                        if attempt == 2:
                                            logger.error("GPT Image не удалось после 3 попыток")
                            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                                logger.error(f"Попытка {attempt+1}: сеть/тайм-аут GPT: {e}")
                                if attempt == 2:
                                    raise
                                await asyncio.sleep(1.5 * (2 ** attempt))
                except Exception as e:
                    logger.error(f"❌ Ошибка при генерации GPT Image: {e}", exc_info=True)

        elif self.model_type == "nanobanana":
            # ---------- Nano Banana Pro для одиночных фото ----------
            try:
                with open(ref_photo_path, "rb") as f:
                    image_data = base64.b64encode(f.read()).decode("utf-8")
                    data_url = f"data:image/jpeg;base64,{image_data}"
            except Exception as e:
                logger.error(f"❌ Ошибка кодирования фото для Nano Banana: {e}")
                return []

            enhanced_prompt = (
                f"{prompt} Ultra-realistic, cinematic lighting, "
                f"exact facial features as in reference image, "
                f"face clearly visible, sharp focus on face, "
                f"4K resolution, professional photography style, "
                f"perfect facial similarity. Landscape orientation, horizontal composition, aspect ratio 16:9, wide format."
            )

            for i in range(num_images):
                try:
                    async with aiohttp.ClientSession() as session:
                        headers = {
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json"
                        }
                        payload = {
                            "model": "gemini-3-pro-image-preview",
                            "messages": [
                                {
                                    "role": "user",
                                    "content": [
                                        {"type": "image_url", "image_url": {"url": data_url}},
                                        {"type": "text", "text": enhanced_prompt}
                                    ]
                                }
                            ],
                            "modalities": ["image", "text"],
                            "max_tokens": 3000
                        }
                        result = await self._post_with_retry(
                            session,
                            f"{self.base_url}/chat/completions",
                            headers,
                            payload,
                            aiohttp.ClientTimeout(total=self.TIMEOUT_NANOBANANA),
                            retries=2
                        )
                        if result and 'choices' in result and result['choices']:
                            message = result['choices'][0].get('message', {})
                            if 'images' in message:
                                for img in message['images']:
                                    if 'image_url' in img and 'url' in img['image_url']:
                                        results.append(img['image_url']['url'])
                                    elif 'b64_json' in img:
                                        results.append(f"data:image/png;base64,{img['b64_json']}")
                            elif 'content' in message and message['content'].startswith('data:image'):
                                results.append(message['content'])
                except Exception as e:
                    logger.error(f"❌ Ошибка при генерации Nano Banana Pro: {e}", exc_info=True)

        logger.info(f"✅ Генерация завершена, получено {len(results)} фото")
        return results

    # ---------- КАСТОМНАЯ ГЕНЕРАЦИЯ (произвольный промпт) ----------
    async def generate_custom_photo(self, user_photo_paths: list, prompt: str, num_images: int = 1) -> list:
        """Генерация фото по произвольному промпту через GPT Image High."""
        try:
            if not user_photo_paths:
                logger.error("❌ Список фото пользователя пуст")
                return []

            ref_photo_path = None
            for path in user_photo_paths:
                if os.path.exists(path):
                    ref_photo_path = path
                    logger.info(f"✅ Используем референс фото для кастомной генерации: {ref_photo_path}")
                    break
                else:
                    logger.warning(f"⚠️ Файл не найден: {path}")

            if not ref_photo_path:
                logger.error("❌ Ни одно из фото пользователя не найдено на диске")
                return []

            results = []
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

                        headers = {"Authorization": f"Bearer {self.api_key}"}
                        for attempt in range(3):
                            try:
                                async with session.post(
                                    f"{self.base_url}/images/edits",
                                    headers=headers,
                                    data=form_data,
                                    timeout=aiohttp.ClientTimeout(total=self.TIMEOUT_GPT)
                                ) as resp:
                                    if resp.status == 200:
                                        data = await resp.json()
                                        if 'data' in data:
                                            for item in data['data']:
                                                if 'b64_json' in item:
                                                    results.append(f"data:image/png;base64,{item['b64_json']}")
                                                elif 'url' in item:
                                                    results.append(item['url'])
                                        break
                                    else:
                                        error_text = await resp.text()
                                        logger.error(f"Попытка {attempt+1}: GPT custom ошибка {resp.status}")
                                        if attempt == 2:
                                            logger.error("Кастомная генерация не удалась после 3 попыток")
                            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                                logger.error(f"Попытка {attempt+1}: сеть/тайм-аут custom GPT: {e}")
                                if attempt == 2:
                                    raise
                                await asyncio.sleep(1.5 * (2 ** attempt))
                except Exception as e:
                    logger.error(f"❌ Ошибка при генерации кастомного фото: {e}", exc_info=True)
            logger.info(f"✅ Кастомная генерация завершена, получено {len(results)} фото")
            return results
        except Exception as e:
            logger.error(f"❌ Общая ошибка в generate_custom_photo: {e}", exc_info=True)
            return []

    # ---------- ПАРНЫЕ ФОТО через Nano Banana Pro ----------
    async def generate_couple_photo_nanobanana(
        self,
        male_photo_path: str,
        female_photo_path: str,
        prompt: str,
        resolution: str = "2K"
    ) -> list:
        """Генерация парного фото с повторными попытками."""
        try:
            with open(male_photo_path, "rb") as f:
                male_data = base64.b64encode(f.read()).decode("utf-8")
            with open(female_photo_path, "rb") as f:
                female_data = base64.b64encode(f.read()).decode("utf-8")

            enhanced_prompt = (
                f"{prompt} Ultra-realistic, cinematic lighting, "
                f"exact facial features as in reference images, "
                f"both faces clearly visible, sharp focus on faces, "
                f"4K resolution, professional photography style, "
                f"consistent characters, perfect facial similarity. "
                f"Landscape orientation, horizontal composition, aspect ratio 16:9, wide format."
            )

            async with aiohttp.ClientSession() as session:
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": "gemini-3-pro-image-preview",
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{male_data}"}},
                                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{female_data}"}},
                                {"type": "text", "text": enhanced_prompt}
                            ]
                        }
                    ],
                    "modalities": ["image", "text"],
                    "max_tokens": 3000,
                }
                result = await self._post_with_retry(
                    session,
                    f"{self.base_url}/chat/completions",
                    headers,
                    payload,
                    aiohttp.ClientTimeout(total=self.TIMEOUT_COUPLE),
                    retries=2
                )
                if result and 'choices' in result and result['choices']:
                    message = result['choices'][0].get('message', {})
                    images = []
                    if 'images' in message and message['images']:
                        for img in message['images']:
                            if 'image_url' in img and 'url' in img['image_url']:
                                images.append(img['image_url']['url'])
                                break
                            elif 'b64_json' in img:
                                images.append(f"data:image/png;base64,{img['b64_json']}")
                                break
                    elif 'content' in message and message['content'] and message['content'].startswith('data:image'):
                        images.append(message['content'])
                    return images
                else:
                    logger.error("Ошибка генерации парного фото: пустой ответ")
                    return []
        except Exception as e:
            logger.error(f"❌ Ошибка при генерации парного фото: {e}", exc_info=True)
            return []

    # ---------- ВИДЕО Sora 2 Pro (Image-to-Video) ----------
    async def generate_video_sora_i2v(self, image_paths: list, prompt: str, size: str = "1280x720", duration: int = 4) -> bytes | None:
        """Генерация видео из изображения с повторными попытками при создании."""
        try:
            allowed = [4, 8, 12]
            if duration not in allowed:
                logger.warning(f"Недопустимое значение duration={duration}, используем 4")
                duration = 4
            seconds_str = str(duration)

            image_path = image_paths[0]
            target_width, target_height = map(int, size.split('x'))
            with Image.open(image_path) as img:
                img.thumbnail((target_width, target_height), Image.LANCZOS)
                new_img = Image.new('RGB', (target_width, target_height), (0, 0, 0))
                paste_x = (target_width - img.width) // 2
                paste_y = (target_height - img.height) // 2
                new_img.paste(img, (paste_x, paste_y))
                buffer = io.BytesIO()
                new_img.save(buffer, format='JPEG')
                image_bytes = buffer.getvalue()

            image_base64 = base64.b64encode(image_bytes).decode("utf-8")
            data_url = f"data:image/jpeg;base64,{image_base64}"

            payload = {
                "model": "sora-2-pro",
                "prompt": prompt,
                "size": size,
                "seconds": seconds_str,
                "input_reference": {
                    "image_url": data_url
                }
            }

            logger.info(f"Отправляем запрос на создание видео, duration={duration} сек")

            video_id = None
            async with aiohttp.ClientSession() as session:
                headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
                # Попытки создания видео
                for attempt in range(3):
                    try:
                        async with session.post(
                            f"{self.base_url}/videos",
                            headers=headers,
                            json=payload,
                            timeout=aiohttp.ClientTimeout(total=self.TIMEOUT_VIDEO_CREATE)
                        ) as resp:
                            if resp.status == 200:
                                create_result = await resp.json()
                                video_id = create_result.get("id")
                                if video_id:
                                    break
                            else:
                                error_text = await resp.text()
                                logger.error(f"Попытка {attempt+1}: создание видео ошибка {resp.status}: {error_text[:200]}")
                    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                        logger.error(f"Попытка {attempt+1}: сеть/тайм-аут при создании видео: {e}")
                        if attempt == 2:
                            return None
                        await asyncio.sleep(1.5 * (2 ** attempt))
                if not video_id:
                    logger.error("Не удалось получить video_id после всех попыток")
                    return None

                # Ожидание готовности видео
                for attempt in range(60):
                    await asyncio.sleep(5)
                    try:
                        async with session.get(
                            f"{self.base_url}/videos/{video_id}",
                            headers=headers,
                            timeout=aiohttp.ClientTimeout(total=30)
                        ) as resp:
                            if resp.status != 200:
                                logger.warning(f"Ошибка получения статуса: {resp.status}")
                                continue
                            status_data = await resp.json()
                            status = status_data.get("status")
                            progress = status_data.get("progress", 0)
                            logger.info(f"Видео {video_id}: статус {status}, прогресс {progress}%")
                            if status == "completed":
                                async with session.get(
                                    f"{self.base_url}/videos/{video_id}/content",
                                    headers=headers,
                                    timeout=aiohttp.ClientTimeout(total=60)
                                ) as download_resp:
                                    if download_resp.status == 200:
                                        video_bytes = await download_resp.read()
                                        logger.info(f"Видео {video_id} скачано, размер {len(video_bytes)} байт")
                                        return video_bytes
                                    else:
                                        logger.error(f"Ошибка скачивания видео: {download_resp.status}")
                                        return None
                            elif status == "failed":
                                logger.error(f"Генерация видео {video_id} провалилась")
                                return None
                    except Exception as e:
                        logger.error(f"Ошибка при опросе статуса видео: {e}")
                        continue
                logger.error(f"Таймаут ожидания видео {video_id}")
                return None
        except Exception as e:
            logger.error(f"❌ Ошибка при генерации видео: {e}", exc_info=True)
            return None

    # ---------- УНИВЕРСАЛЬНАЯ ГЕНЕРАЦИЯ ВИДЕО (поддержка любых моделей) ----------
    async def generate_video_generic(self, model: str, image_paths: list, prompt: str, size: str, duration: int = 4) -> Optional[bytes]:
        """
        Универсальная генерация видео для любой модели AI Tunnel.
        model: "sora-2-pro", "seedance-1.5-pro" и т.д.
        image_paths: список путей к изображениям (берётся первое)
        prompt: текстовое описание
        size: "1280x720", "1080x1440" и т.д. (требуется моделью)
        duration: длительность в секундах (если модель поддерживает, иначе игнорируется)
        """
        if not image_paths:
            logger.error("❌ Нет изображений для генерации видео")
            return None
        
        image_path = image_paths[0]
        if not os.path.exists(image_path):
            logger.error(f"❌ Файл не найден: {image_path}")
            return None
        
        # Кодируем изображение в base64
        try:
            with open(image_path, "rb") as f:
                image_data = base64.b64encode(f.read()).decode('utf-8')
        except Exception as e:
            logger.error(f"❌ Ошибка кодирования изображения: {e}")
            return None
        
        url = f"{self.base_url}/videos"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": model,
            "prompt": prompt,
            "image": image_data,
            "size": size,
            "duration": duration
        }
        
        logger.info(f"Запрос на создание видео: модель={model}, size={size}, duration={duration} сек")
        
        async with aiohttp.ClientSession() as session:
            # 1. Создаём задание (с повторными попытками)
            job = None
            for attempt in range(3):
                try:
                    async with session.post(url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                        # Разрешаем и 200, и 202 (Accepted)
                        if resp.status in (200, 202):
                            job = await resp.json()
                            break
                        else:
                            error_text = await resp.text()
                            logger.error(f"Попытка {attempt+1}: ошибка создания видео ({resp.status}): {error_text[:200]}")
                except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                    logger.error(f"Попытка {attempt+1}: сеть/тайм-аут при создании видео: {e}")
                    if attempt == 2:
                        return None
                    await asyncio.sleep(1.5 * (2 ** attempt))
            
            if not job:
                logger.error("Не удалось создать видео-задание после всех попыток")
                return None
            
            job_id = job.get("id")
            polling_url = job.get("polling_url")
            if not polling_url:
                logger.error("Ответ не содержит polling_url")
                return None
            logger.info(f"Видео-задание создано: id={job_id}, polling_url={polling_url}")
            
            # 2. Ожидаем завершения (polling)
            max_attempts = 60  # максимум 5 минут при интервале 5 сек
            for attempt in range(max_attempts):
                await asyncio.sleep(5)
                try:
                    async with session.get(polling_url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        if resp.status != 200:
                            logger.warning(f"Polling attempt {attempt+1}: статус {resp.status}")
                            continue
                        status_data = await resp.json()
                        status = status_data.get("status")
                        logger.info(f"Статус видео: {status} (прогресс: {status_data.get('progress', 'N/A')})")
                        if status == "completed":
                            video_url = status_data.get("unsigned_urls", [None])[0]
                            if video_url:
                                async with session.get(video_url, timeout=aiohttp.ClientTimeout(total=60)) as video_resp:
                                    if video_resp.status == 200:
                                        video_bytes = await video_resp.read()
                                        logger.info(f"Видео получено, размер {len(video_bytes)} байт")
                                        return video_bytes
                                    else:
                                        logger.error(f"Не удалось скачать видео: {video_resp.status}")
                                        return None
                            else:
                                logger.error("Нет ссылки на готовое видео в ответе")
                                return None
                        elif status == "failed":
                            error_msg = status_data.get("error", "Неизвестная ошибка")
                            logger.error(f"Генерация видео провалилась: {error_msg}")
                            return None
                except Exception as e:
                    logger.warning(f"Ошибка при опросе статуса: {e}")
                    continue
            
            logger.error("Таймаут ожидания видео")
            return None

    # ---------- ГЕНЕРАЦИЯ ВИДЕО ЧЕРЕЗ Wan 2.7 (исправленная) ----------
    async def generate_video_wan27(self, prompt: str, size: str = "1280x720", duration: int = 4) -> Optional[bytes]:
        """
        Генерация видео через модель Wan 2.7 (без исходного изображения, только prompt).
        Исправлена обработка статуса 202 как успеха.
        """
        url = f"{self.base_url}/videos"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "wan-2.7",
            "prompt": prompt,
            "size": size,
            "duration": duration
        }
        
        logger.info(f"Запрос на создание видео Wan 2.7: prompt={prompt[:100]}..., size={size}, duration={duration} сек")
        
        async with aiohttp.ClientSession() as session:
            # 1. Создаём задание (с повторными попытками)
            job = None
            for attempt in range(3):
                try:
                    async with session.post(url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=self.TIMEOUT_VIDEO_CREATE)) as resp:
                        # Успешные статусы: 200 OK или 202 Accepted
                        if resp.status in (200, 202):
                            job = await resp.json()
                            logger.info(f"Попытка {attempt+1}: видео-задание Wan 2.7 создано (HTTP {resp.status})")
                            break
                        else:
                            error_text = await resp.text()
                            logger.error(f"Попытка {attempt+1}: ошибка создания видео ({resp.status}): {error_text[:200]}")
                except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                    logger.error(f"Попытка {attempt+1}: сеть/тайм-аут при создании видео: {e}")
                    if attempt == 2:
                        return None
                    await asyncio.sleep(1.5 * (2 ** attempt))
            
            if not job:
                logger.error("Не удалось создать видео-задание Wan 2.7 после всех попыток")
                return None
            
            job_id = job.get("id")
            polling_url = job.get("polling_url")
            if not polling_url:
                logger.error("Ответ Wan 2.7 не содержит polling_url")
                return None
            logger.info(f"Видео-задание Wan 2.7 создано: id={job_id}, polling_url={polling_url}")
            
            # 2. Ожидаем завершения (polling)
            max_attempts = 60  # 5 минут
            for attempt in range(max_attempts):
                await asyncio.sleep(5)
                try:
                    async with session.get(polling_url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        if resp.status != 200:
                            logger.warning(f"Polling attempt {attempt+1}: статус {resp.status}")
                            continue
                        status_data = await resp.json()
                        status = status_data.get("status")
                        logger.info(f"Статус видео Wan 2.7: {status} (прогресс: {status_data.get('progress', 'N/A')})")
                        if status == "completed":
                            video_url = status_data.get("unsigned_urls", [None])[0]
                            if video_url:
                                async with session.get(video_url, timeout=aiohttp.ClientTimeout(total=60)) as video_resp:
                                    if video_resp.status == 200:
                                        video_bytes = await video_resp.read()
                                        logger.info(f"Видео Wan 2.7 получено, размер {len(video_bytes)} байт")
                                        return video_bytes
                                    else:
                                        logger.error(f"Не удалось скачать видео Wan 2.7: {video_resp.status}")
                                        return None
                            else:
                                logger.error("Нет ссылки на готовое видео Wan 2.7 в ответе")
                                return None
                        elif status == "failed":
                            error_msg = status_data.get("error", "Неизвестная ошибка")
                            logger.error(f"Генерация видео Wan 2.7 провалилась: {error_msg}")
                            return None
                except Exception as e:
                    logger.warning(f"Ошибка при опросе статуса Wan 2.7: {e}")
                    continue
            
            logger.error("Таймаут ожидания видео Wan 2.7")
            return None