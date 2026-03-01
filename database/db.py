import aiosqlite
from datetime import datetime

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
            await db.commit()

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

    async def update_user_state(self, user_id, state):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE users SET state = ? WHERE user_id = ?",
                (state, user_id)
            )
            await db.commit()

    async def get_user_state(self, user_id):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT state FROM users WHERE user_id = ?", (user_id,)
            )
            row = await cursor.fetchone()
            return row[0] if row else None

    async def get_user_photo_count(self, user_id):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM photos WHERE user_id = ? AND photo_type = 'input'",
                (user_id,)
            )
            row = await cursor.fetchone()
            return row[0] if row else 0

    async def add_photo(self, user_id, file_id, file_path, photo_type="input", style=None):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO photos (user_id, file_id, file_path, photo_type, style) "
                "VALUES (?, ?, ?, ?, ?)",
                (user_id, file_id, file_path, photo_type, style)
            )
            await db.execute(
                "UPDATE users SET photo_count = photo_count + 1 WHERE user_id = ?",
                (user_id,)
            )
            await db.commit()

    async def get_user_photos(self, user_id, photo_type="input"):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT file_path FROM photos WHERE user_id = ? AND photo_type = ?",
                (user_id, photo_type)
            )
            rows = await cursor.fetchall()
            return [row[0] for row in rows]

    async def clear_user_photos(self, user_id):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "DELETE FROM photos WHERE user_id = ? AND photo_type = 'input'",
                (user_id,)
            )
            await db.execute(
                "UPDATE users SET photo_count = 0 WHERE user_id = ?",
                (user_id,)
            )
            await db.commit()

    async def add_generation(self, user_id, style, status="completed"):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO generations (user_id, style, status, completed_at) VALUES (?, ?, ?, ?)",
                (user_id, style, status, datetime.now())
            )
            await db.commit()

    async def set_user_gender(self, user_id: int, gender: str):
        """Сохраняет пол пользователя."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE users SET gender = ? WHERE user_id = ?",
                (gender, user_id)
            )
            await db.commit()

    async def get_user_gender(self, user_id: int) -> str | None:
        """Возвращает пол пользователя или None."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT gender FROM users WHERE user_id = ?",
                (user_id,)
            )
            row = await cursor.fetchone()
            return row[0] if row else None