"""One-time, idempotent migration. Run with the bot stopped and DATABASE_URL set."""
import asyncio
import sqlite3
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from databases import init_db, close_db, pool


async def migrate(path):
    source = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)
    try:
        users = source.execute('SELECT user_id, language FROM users').fetchall()
        links = source.execute('SELECT admin_message_id, user_id, user_message_id, status FROM support_messages').fetchall()
    finally:
        source.close()
    await init_db()
    try:
        async with pool().acquire() as conn:
            async with conn.transaction():
                await conn.executemany('''INSERT INTO users VALUES ($1, $2)
                    ON CONFLICT (user_id) DO NOTHING''', users)
                await conn.executemany('''INSERT INTO support_messages VALUES ($1, $2, $3, $4)
                    ON CONFLICT (admin_message_id) DO NOTHING''', links)
        print(f'Migration complete: {len(users)} users, {len(links)} message links processed; existing rows preserved.')
    finally:
        await close_db()


if __name__ == '__main__':
    load_dotenv()
    if len(sys.argv) != 2:
        raise SystemExit('Usage: python scripts/migrate_sqlite.py /path/to/bot.db')
    asyncio.run(migrate(sys.argv[1]))
