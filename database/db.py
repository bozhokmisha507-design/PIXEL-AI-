import asyncpg
import logging
import os
import json
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.database_url = os.getenv("DATABASE_URL")
        if not self.database_url:
            raise ValueError("DATABASE_URL не задан в переменных окружения")
        self.pool = None

    async def init(self):
        """Инициализация пула соединений и создание таблиц"""
        try:
            self.pool = await asyncpg.create_pool(self.database_url)
            logger.info("✅ Подключение к PostgreSQL установлено")
            
            async with self.pool.acquire() as conn:
                # Таблица пользователей
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        user_id BIGINT PRIMARY KEY,
                        username TEXT,
                        first_name TEXT,
                        gender TEXT DEFAULT NULL,
                        selected_style TEXT DEFAULT NULL,
                        tokens INTEGER DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        state TEXT DEFAULT 'new',
                        photo_count INTEGER DEFAULT 0
                    )
                """)

                # Таблица фотографий
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS photos (
                        id SERIAL PRIMARY KEY,
                        user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
                        file_id TEXT,
                        file_path TEXT,
                        photo_type TEXT DEFAULT 'input',
                        style TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # Таблица генераций
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS generations (
                        id SERIAL PRIMARY KEY,
                        user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
                        style TEXT,
                        status TEXT DEFAULT 'completed',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        completed_at TIMESTAMP
                    )
                """)

                # Таблица заказов для платежей
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS orders (
                        id SERIAL PRIMARY KEY,
                        user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
                        label TEXT UNIQUE,
                        amount REAL,
                        status TEXT DEFAULT 'pending',
                        data TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        processed BOOLEAN DEFAULT FALSE
                    )
                """)

                # Проверяем и добавляем индексы для производительности
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_label ON orders(label)")
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_processed ON orders(processed)")
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_photos_user_id ON photos(user_id)")
                
                logger.info("✅ Таблицы созданы/проверены")
                
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации базы данных: {e}")
            raise

    async def close(self):
        """Закрытие пула соединений"""
        if self.pool:
            await self.pool.close()
            logger.info("✅ Пул соединений закрыт")

    # ===== Пользователи =====
    async def get_or_create_user(self, user_id: int, username: str = None, first_name: str = None) -> tuple:
        async with self.pool.acquire() as conn:
            user = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
            if not user:
                await conn.execute(
                    "INSERT INTO users (user_id, username, first_name) VALUES ($1, $2, $3)",
                    user_id, username, first_name
                )
                user = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
            return user

    async def get_user_tokens(self, user_id: int) -> int:
        async with self.pool.acquire() as conn:
            result = await conn.fetchval("SELECT tokens FROM users WHERE user_id = $1", user_id)
            return result if result is not None else 0

    async def add_tokens(self, user_id: int, amount: int):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET tokens = tokens + $1 WHERE user_id = $2",
                amount, user_id
            )

    async def use_tokens(self, user_id: int, cost: int) -> bool:
        """Атомарно списывает указанное количество жетонов, если их достаточно."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE users SET tokens = tokens - $1 WHERE user_id = $2 AND tokens >= $3",
                cost, user_id, cost
            )
            # В PostgreSQL результат - строка типа "UPDATE 1" если обновлено
            return "UPDATE 1" in result

    # ===== Фотографии =====
    async def get_user_photo_count(self, user_id: int) -> int:
        photos = await self.get_user_photos(user_id, "input")
        return len(photos)

    async def get_user_photos(self, user_id: int, photo_type: str = "input") -> List[str]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT file_path FROM photos WHERE user_id = $1 AND photo_type = $2",
                user_id, photo_type
            )
            all_paths = [row['file_path'] for row in rows]
            existing_paths = [p for p in all_paths if os.path.exists(p)]
            if len(existing_paths) != len(all_paths):
                logger.warning(f"Для user {user_id} в БД {len(all_paths)} записей, но только {len(existing_paths)} файлов существуют.")
            return existing_paths

    async def add_photo(self, user_id: int, file_id: str, file_path: str, photo_type: str = "input", style: str = None):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO photos (user_id, file_id, file_path, photo_type, style) VALUES ($1, $2, $3, $4, $5)",
                user_id, file_id, file_path, photo_type, style
            )

    async def clear_user_photos(self, user_id: int):
        paths = await self.get_user_photos(user_id, "input")
        for path in paths:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception as e:
                logger.error(f"Ошибка удаления файла {path}: {e}")
        
        async with self.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM photos WHERE user_id = $1 AND photo_type = 'input'",
                user_id
            )

    # ===== Пол =====
    async def set_user_gender(self, user_id: int, gender: str):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET gender = $1 WHERE user_id = $2",
                gender, user_id
            )

    async def get_user_gender(self, user_id: int) -> Optional[str]:
        async with self.pool.acquire() as conn:
            return await conn.fetchval(
                "SELECT gender FROM users WHERE user_id = $1",
                user_id
            )

    # ===== Стили =====
    async def set_user_selected_style(self, user_id: int, style_key: str):
        logger.info(f"📝 Сохраняем стиль {style_key} для user {user_id}")
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET selected_style = $1 WHERE user_id = $2",
                style_key, user_id
            )
        logger.info(f"✅ Стиль сохранён")

    async def get_user_selected_style(self, user_id: int) -> Optional[str]:
        logger.info(f"🔍 Получаем стиль для user {user_id}")
        async with self.pool.acquire() as conn:
            style = await conn.fetchval(
                "SELECT selected_style FROM users WHERE user_id = $1",
                user_id
            )
            logger.info(f"📦 Найден стиль: {style}")
            return style

    # ===== Заказы =====
    async def create_order(self, user_id: int, label: str, amount: float, data: dict = None) -> None:
        """Создаёт запись о заказе. Если передан data, сохраняет его как JSON в поле data."""
        async with self.pool.acquire() as conn:
            if data is not None:
                data_json = json.dumps(data, ensure_ascii=False)
                await conn.execute(
                    "INSERT INTO orders (user_id, label, amount, data) VALUES ($1, $2, $3, $4)",
                    user_id, label, amount, data_json
                )
            else:
                await conn.execute(
                    "INSERT INTO orders (user_id, label, amount) VALUES ($1, $2, $3)",
                    user_id, label, amount
                )

    async def get_unprocessed_orders(self) -> List[Dict[str, Any]]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT label, user_id FROM orders WHERE processed = FALSE"
            )
            return [{"label": row['label'], "user_id": row['user_id']} for row in rows]

    async def mark_order_processed(self, label: str) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE orders SET processed = TRUE WHERE label = $1",
                label
            )

    async def try_mark_order_processed(self, label: str) -> bool:
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE orders SET processed = TRUE WHERE label = $1 AND processed = FALSE",
                label
            )
            return "UPDATE 1" in result

    async def is_order_processed(self, label: str) -> bool:
        async with self.pool.acquire() as conn:
            result = await conn.fetchval(
                "SELECT processed FROM orders WHERE label = $1",
                label
            )
            return bool(result)

    async def get_order_data(self, label: str) -> Optional[dict]:
        """Возвращает данные заказа (поле data) в виде словаря, если они есть."""
        async with self.pool.acquire() as conn:
            data = await conn.fetchval(
                "SELECT data FROM orders WHERE label = $1",
                label
            )
            if data:
                return json.loads(data)
            return None

# ===== Глобальный экземпляр БД =====
_db_instance = None

async def get_db():
    global _db_instance
    if _db_instance is None:
        _db_instance = Database()
        await _db_instance.init()
    return _db_instance