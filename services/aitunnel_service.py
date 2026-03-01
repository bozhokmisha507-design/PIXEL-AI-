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

    async def generate_photos(self, user_photo_paths: list, style_key: str, num_images: int = 1) -> list:
        style = Config.STYLES.get(style_key)
        if not style:
            raise ValueError(f"Unknown style: {style_key}")

        prompt = style["prompt"]
        logger.info(f"Генерация фото в стиле {style_key}, модель: {self.image_model}")
        
        results = []
        
        if not user_photo_paths:
            logger.error("Нет фото пользователя")
            return []
            
        ref_photo_path = user_photo_paths[0]
        logger.info(f"Используем референс фото: {ref_photo_path}")
        
        try:
            with open(ref_photo_path, "rb") as f:
                image_data = base64.b64encode(f.read()).decode("utf-8")
                data_url = f"data:image/jpeg;base64,{image_data}"
                logger.info(f"Фото закодировано, размер: {len(image_data)} символов")
        except Exception as e:
            logger.error(f"Ошибка кодирования фото: {e}")
            return []

        for i in range(num_images):
            try:
                logger.info(f"Отправка запроса к AI Tunnel (Gemini 2.5 Flash Image) для фото #{i+1}")
                
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
                    
                    async with session.post(
                        f"{self.base_url}/chat/completions",
                        headers=headers,
                        json=payload,
                        timeout=60  # Увеличиваем таймаут до 60 секунд
                    ) as response:
                        if response.status == 200:
                            result = await response.json()
                            logger.info(f"Ответ от Gemini API получен")
                            
                            if 'choices' in result and len(result['choices']) > 0:
                                message = result['choices'][0].get('message', {})
                                
                                # Сохраняем результат в файл
                                if 'images' in message:
                                    for img in message['images']:
                                        if 'image_url' in img and 'url' in img['image_url']:
                                            image_url = img['image_url']['url']
                                            results.append(image_url)
                                            logger.info(f"Получено изображение: {image_url[:50]}...")
                                
                                elif 'content' in message and message['content']:
                                    content = message['content']
                                    if content.startswith('data:image') or len(content) > 1000:
                                        results.append(content)
                                        logger.info("Получено base64 изображение в content")
                                    else:
                                        logger.warning(f"Получен текст вместо изображения: {content[:100]}")
                                else:
                                    logger.warning(f"Нет изображения в ответе")
                            else:
                                logger.error(f"Нет choices в ответе")
                        else:
                            error_text = await response.text()
                            logger.error(f"Ошибка Gemini API: {response.status}")
                            
            except asyncio.TimeoutError:
                logger.error(f"Таймаут при генерации фото #{i+1}")
            except Exception as e:
                logger.error(f"Ошибка при генерации фото #{i+1}: {e}", exc_info=True)

        logger.info(f"Генерация завершена, получено {len(results)} фото")
        return results

    @staticmethod
    def _encode_image(image_path: str) -> str:
        """Кодирует изображение в base64"""
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")