from aiogram import Router
from pathlib import Path
import sqlite3 as sql

PROJECT_DIR = Path(__file__).resolve().parent

DB_PATH = PROJECT_DIR / "bot.db"
def get_connection():
    return sql.connect(DB_PATH)

with get_connection() as db:
    db.execute(
        """CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        language TEXT NOT NULL
        );"""
    )
    db.commit()

    def get_language(user_id: int):
        data = db.execute(
            "SELECT language FROM users WHERE user_id = ?",
            (user_id,) 
        ).fetchone()
        return data[0] if data else None


    def save_language(user_id: int, lang: str):
        db.execute(
            """INSERT INTO users (user_id, language)
            VALUES (?, ?)
            ON CONFLICT(user_id)
            DO UPDATE SET language = excluded.language""",
            (user_id, lang)
        )
        db.commit()

    db.execute(
     """
            CREATE TABLE IF NOT EXISTS support_messages (
                admin_message_id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                user_message_id INTEGER NOT NULL,
                status TEXT NOT NULL
            )
            """
    )


    def save_appeal(user_id, admin_chat_id, admin_message_id):
        db.execute("""
            INSERT INTO appeals (
                user_id,
                admin_chat_id,
                admin_message_id
            )
            VALUES (?, ?, ?)
        """, (user_id, admin_chat_id, admin_message_id))
        db.commit()


    def get_appeal_user(admin_message_id):
        result = db.execute("""
            SELECT user_id
            FROM appeals
            WHERE admin_message_id = ?
            AND status = 'open'
        """, (admin_message_id,)).fetchone()
        return result[0] if result else None
