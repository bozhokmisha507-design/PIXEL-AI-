import aiosqlite
import logging
import os
import json  # добавлен импорт
from datetime import datetime

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, db_path="bot_database.db"):
        self.db_path = db_path

    async def init(self):
        async with aiosqlite.connect(self.db_path) as db:
            # Таблица пользователей
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
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
            await db.execute("""
                CREATE TABLE IF NOT EXISTS photos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    file_id TEXT,
                    file_path TEXT,
                    photo_type TEXT DEFAULT 'input',
                    style TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)

            # Таблица генераций
            await db.execute("""
                CREATE TABLE IF NOT EXISTS generations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    style TEXT,
                    status TEXT DEFAULT 'completed',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)

            # Таблица заказов для платежей
            await db.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    label TEXT UNIQUE,
                    amount REAL,
                    status TEXT DEFAULT 'pending',
                    data TEXT,                    -- новое поле для хранения JSON
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    processed BOOLEAN DEFAULT 0,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)

            # Проверяем наличие колонки tokens в users и добавляем, если её нет
            cursor = await db.execute("PRAGMA table_info(users)")
            columns = await cursor.fetchall()
            column_names = [col[1] for col in columns]
            if 'tokens' not in column_names:
                await db.execute("ALTER TABLE users ADD COLUMN tokens INTEGER DEFAULT 0")
                logger.info("✅ Добавлена колонка tokens в таблицу users")

            # Проверяем наличие колонки data в orders (на случай, если таблица уже существовала)
            cursor = await db.execute("PRAGMA table_info(orders)")
            columns = await cursor.fetchall()
            column_names = [col[1] for col in columns]
            if 'data' not in column_names:
                await db.execute("ALTER TABLE orders ADD COLUMN data TEXT")
                logger.info("✅ Добавлена колонка data в таблицу orders")

            await db.commit()

    # ===== Пользователи =====
    async def get_or_create_user(self, user_id, username=None, first_name=None):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT * FROM users WHERE user_id = ?", (user_id,)
            )
            user = await cursor.fetchone()
            if not user:
                await db.execute(
                    "INSERT INTO users (user_id, username, first_name) VALUES (?, ?, ?)",
                    (user_id, username, first_name)
                )
                await db.commit()
                cursor = await db.execute(
                    "SELECT * FROM users WHERE user_id = ?", (user_id,)
                )
                user = await cursor.fetchone()
            return user

    async def get_user_tokens(self, user_id: int) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT tokens FROM users WHERE user_id = ?", (user_id,)
            )
            row = await cursor.fetchone()
            return row[0] if row else 0

    async def add_tokens(self, user_id: int, amount: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE users SET tokens = tokens + ? WHERE user_id = ?",
                (amount, user_id)
            )
            await db.commit()

    async def use_tokens(self, user_id: int, cost: int) -> bool:
        """Атомарно списывает указанное количество жетонов, если их достаточно."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "UPDATE users SET tokens = tokens - ? WHERE user_id = ? AND tokens >= ?",
                (cost, user_id, cost)
            )
            await db.commit()
            return cursor.rowcount > 0

    # ===== Фотографии =====
    async def get_user_photo_count(self, user_id):
        paths = await self.get_user_photos(user_id, "input")
        return len(paths)

    async def get_user_photos(self, user_id, photo_type="input"):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT file_path FROM photos WHERE user_id = ? AND photo_type = ?",
                (user_id, photo_type)
            )
            rows = await cursor.fetchall()
            all_paths = [row[0] for row in rows]
            existing_paths = [p for p in all_paths if os.path.exists(p)]
            if len(existing_paths) != len(all_paths):
                logger.warning(f"Для user {user_id} в БД {len(all_paths)} записей, но только {len(existing_paths)} файлов существуют.")
            return existing_paths

    async def add_photo(self, user_id, file_id, file_path, photo_type="input", style=None):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO photos (user_id, file_id, file_path, photo_type, style) VALUES (?, ?, ?, ?, ?)",
                (user_id, file_id, file_path, photo_type, style)
            )
            await db.commit()

    async def clear_user_photos(self, user_id):
        paths = await self.get_user_photos(user_id, "input")
        for path in paths:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception as e:
                logger.error(f"Ошибка удаления файла {path}: {e}")
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM photos WHERE user_id = ? AND photo_type = 'input'", (user_id,))
            await db.commit()

    async def set_user_gender(self, user_id: int, gender: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE users SET gender = ? WHERE user_id = ?", (gender, user_id))
            await db.commit()

    async def get_user_gender(self, user_id: int) -> str | None:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT gender FROM users WHERE user_id = ?", (user_id,))
            row = await cursor.fetchone()
            return row[0] if row else None

    async def set_user_selected_style(self, user_id: int, style_key: str):
        logger.info(f"📝 Сохраняем стиль {style_key} для user {user_id}")
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE users SET selected_style = ? WHERE user_id = ?", (style_key, user_id))
            await db.commit()
        logger.info(f"✅ Стиль сохранён")

    async def get_user_selected_style(self, user_id: int) -> str | None:
        logger.info(f"🔍 Получаем стиль для user {user_id}")
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT selected_style FROM users WHERE user_id = ?", (user_id,))
            row = await cursor.fetchone()
            style = row[0] if row else None
            logger.info(f"📦 Найден стиль: {style}")
            return style

    # ===== Заказы =====
    async def create_order(self, user_id: int, label: str, amount: float, data: dict = None) -> None:
        """Создаёт запись о заказе. Если передан data, сохраняет его как JSON в поле data."""
        async with aiosqlite.connect(self.db_path) as db:
            if data is not None:
                data_json = json.dumps(data, ensure_ascii=False)
                await db.execute(
                    "INSERT INTO orders (user_id, label, amount, data) VALUES (?, ?, ?, ?)",
                    (user_id, label, amount, data_json)
                )
            else:
                await db.execute(
                    "INSERT INTO orders (user_id, label, amount) VALUES (?, ?, ?)",
                    (user_id, label, amount)
                )
            await db.commit()

    async def get_unprocessed_orders(self) -> list:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT label, user_id FROM orders WHERE processed = 0")
            rows = await cursor.fetchall()
            return [{"label": row[0], "user_id": row[1]} for row in rows]

    async def mark_order_processed(self, label: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE orders SET processed = 1 WHERE label = ?", (label,))
            await db.commit()

    async def try_mark_order_processed(self, label: str) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("UPDATE orders SET processed = 1 WHERE label = ? AND processed = 0", (label,))
            await db.commit()
            return cursor.rowcount > 0

    async def is_order_processed(self, label: str) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT processed FROM orders WHERE label = ?", (label,))
            row = await cursor.fetchone()
            return bool(row and row[0])

    async def get_order_data(self, label: str) -> dict | None:
        """Возвращает данные заказа (поле data) в виде словаря, если они есть."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT data FROM orders WHERE label = ?", (label,))
            row = await cursor.fetchone()
            if row and row[0]:
                return json.loads(row[0])
        return None

# ===== Глобальный экземпляр БД =====
_db_instance = None

async def get_db():
    global _db_instance
    if _db_instance is None:
        _db_instance = Database()
        await _db_instance.init()
    return _db_instance