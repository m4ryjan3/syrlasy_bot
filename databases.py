"""Shared PostgreSQL storage. Connections are initialized by application startup."""
import json
import os
import ssl
from urllib.parse import urlsplit

import asyncpg
from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, DefaultKeyBuilder, StorageKey

_pool: asyncpg.Pool | None = None


def pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError('Database is not initialized')
    return _pool


async def init_db():
    global _pool
    if _pool is not None:
        return
    dsn = os.environ.get('DATABASE_URL')
    if not dsn:
        raise RuntimeError('DATABASE_URL is required')
    # Neon uses public CA certificates. Pass an explicit verifying context because
    # asyncpg's libpq-style verify-full otherwise expects ~/.postgresql/root.crt.
    host = urlsplit(dsn).hostname or ''
    tls = {'ssl': ssl.create_default_context()} if host.endswith('.neon.tech') else {}
    candidate = await asyncpg.create_pool(
        dsn, min_size=0, max_size=3, command_timeout=30,
        max_inactive_connection_lifetime=60, statement_cache_size=0, **tls,
    )
    try:
        async with candidate.acquire() as conn:
            async with conn.transaction():
                # Serialize schema initialization across instances/revisions.
                await conn.execute('SELECT pg_advisory_xact_lock(713124005)')
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        user_id BIGINT PRIMARY KEY,
                        language TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS support_messages (
                        admin_message_id BIGINT PRIMARY KEY,
                        user_id BIGINT NOT NULL,
                        user_message_id BIGINT NOT NULL,
                        status TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS fsm_state (
                        storage_key TEXT PRIMARY KEY,
                        state TEXT,
                        data JSONB NOT NULL DEFAULT '{}'::jsonb
                    );
                ''')
    except BaseException:
        await candidate.close()
        raise
    _pool = candidate


async def close_db():
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def get_language(user_id: int):
    return await pool().fetchval('SELECT language FROM users WHERE user_id = $1', user_id)


async def save_language(user_id: int, lang: str):
    await pool().execute('''INSERT INTO users (user_id, language) VALUES ($1, $2)
        ON CONFLICT (user_id) DO UPDATE SET language = EXCLUDED.language''', user_id, lang)


async def save_link(admin_message_id: int, user_id: int, user_message_id: int, status: str = 'anon'):
    await pool().execute('''
        INSERT INTO support_messages (admin_message_id, user_id, user_message_id, status)
        VALUES ($1, $2, $3, $4) ON CONFLICT (admin_message_id) DO UPDATE
        SET user_id = EXCLUDED.user_id, user_message_id = EXCLUDED.user_message_id,
            status = EXCLUDED.status
    ''', admin_message_id, user_id, user_message_id, status)


async def get_link(admin_message_id: int):
    row = await pool().fetchrow('''SELECT user_id, user_message_id FROM support_messages
        WHERE admin_message_id = $1''', admin_message_id)
    return tuple(row) if row else None


class PostgresStorage(BaseStorage):
    """Persist aiogram conversation state across service restarts."""
    def __init__(self):
        self.key_builder = DefaultKeyBuilder(
            with_bot_id=True, with_business_connection_id=True, with_destiny=True
        )

    def key(self, key: StorageKey):
        return self.key_builder.build(key)

    async def set_state(self, key: StorageKey, state: str | State | None = None):
        value = state.state if isinstance(state, State) else state
        await pool().execute('''INSERT INTO fsm_state (storage_key, state) VALUES ($1, $2)
            ON CONFLICT (storage_key) DO UPDATE SET state = EXCLUDED.state''', self.key(key), value)

    async def get_state(self, key: StorageKey):
        return await pool().fetchval('SELECT state FROM fsm_state WHERE storage_key = $1', self.key(key))

    async def set_data(self, key: StorageKey, data: dict):
        await pool().execute('''INSERT INTO fsm_state (storage_key, data) VALUES ($1, $2::jsonb)
            ON CONFLICT (storage_key) DO UPDATE SET data = EXCLUDED.data''', self.key(key), json.dumps(data))

    async def get_data(self, key: StorageKey):
        data = await pool().fetchval('SELECT data FROM fsm_state WHERE storage_key = $1', self.key(key))
        return json.loads(data) if data else {}

    async def close(self):
        # Application lifespan owns the shared pool.
        pass
