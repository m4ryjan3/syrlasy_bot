import os
import sqlite3
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from aiohttp.test_utils import TestClient, TestServer
from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.fsm.storage.base import StorageKey
from aiogram.methods import AnswerCallbackQuery, CopyMessage, EditMessageText, SendMessage, SetWebhook, GetWebhookInfo
from aiogram.types import Message, MessageId, WebhookInfo

import databases as db

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def database(monkeypatch):
    dsn = os.environ.get('TEST_DATABASE_URL')
    if not dsn:
        pytest.skip('TEST_DATABASE_URL must point to a disposable PostgreSQL database')
    monkeypatch.setenv('DATABASE_URL', dsn)
    await db.init_db()
    await db.pool().execute('TRUNCATE users, support_messages, fsm_state')
    yield
    await db.close_db()


async def test_database_and_persistent_state(database):
    await db.save_language(1234567890123, 'ru')
    await db.save_language(1234567890123, 'kz')
    assert await db.get_language(1234567890123) == 'kz'
    assert await db.get_language(0) is None
    await db.save_link(100, 1234567890123, 200)
    assert await db.get_link(100) == (1234567890123, 200)
    assert await db.get_link(999) is None
    storage = db.PostgresStorage()
    key = StorageKey(bot_id=1, chat_id=2, user_id=3)
    await storage.set_state(key, 'SupportState:waiting_message')
    await storage.set_data(key, {'language': 'қазақша'})
    await db.close_db()
    await db.init_db()
    restored = db.PostgresStorage()
    assert await restored.get_state(key) == 'SupportState:waiting_message'
    assert await restored.get_data(key) == {'language': 'қазақша'}
    assert await restored.get_state(StorageKey(bot_id=2, chat_id=2, user_id=3)) is None
    await restored.set_state(key, None)
    await restored.set_data(key, {})
    assert await restored.get_state(key) is None
    assert await restored.get_data(key) == {}


async def test_sqlite_migration_is_repeatable(database, tmp_path):
    from scripts.migrate_sqlite import migrate
    source = tmp_path / 'legacy.db'
    with sqlite3.connect(source) as conn:
        conn.executescript('''CREATE TABLE users (user_id INTEGER PRIMARY KEY, language TEXT);
        CREATE TABLE support_messages (admin_message_id INTEGER PRIMARY KEY,
        user_id INTEGER, user_message_id INTEGER, status TEXT);
        INSERT INTO users VALUES (12345, 'ru');
        INSERT INTO support_messages VALUES (100,12345,200,'anon');''')
    before = source.read_bytes()
    await migrate(source)
    await db.init_db()
    await db.save_language(12345, 'kz')
    await migrate(source)
    await db.init_db()
    assert await db.get_language(12345) == 'kz'
    assert await db.get_link(100) == (12345, 200)
    assert source.read_bytes() == before


class OfflineSession(BaseSession):
    """Telegram fixture: no external calls or real credentials."""
    def __init__(self):
        super().__init__()
        self.calls = []
        self.closed = False
        self.webhook_url = None

    async def close(self):
        self.closed = True

    async def stream_content(self, *args, **kwargs):
        if False:
            yield b''

    async def make_request(self, bot, method, timeout=None):
        self.calls.append(method)
        if isinstance(method, SetWebhook):
            assert method.max_connections == 1
            assert method.drop_pending_updates is False
            self.webhook_url = method.url
            return True
        if isinstance(method, GetWebhookInfo):
            return WebhookInfo(url=self.webhook_url, has_custom_certificate=False, pending_update_count=0)
        if isinstance(method, AnswerCallbackQuery):
            return True
        if isinstance(method, CopyMessage):
            return MessageId(message_id=900)
        if isinstance(method, (SendMessage, EditMessageText)):
            return Message(message_id=901, date=datetime.now(timezone.utc),
                           chat={'id': method.chat_id, 'type': 'private'}, text=method.text)
        raise AssertionError(type(method).__name__)


async def test_webhook_and_existing_bot_flows(database, monkeypatch):
    import main
    import anon_appeals
    from answers import texts
    session = OfflineSession()
    bot = Bot(token='123456789:offline_test_fixture', session=session)
    monkeypatch.setattr(main, 'create_bot', lambda: bot)
    monkeypatch.delenv('WEBHOOK_BASE_URL', raising=False)
    monkeypatch.setenv('WEBHOOK_SECRET', 'test-secret')
    monkeypatch.setenv('RENDER_EXTERNAL_URL', 'https://syrlasy-test.onrender.com')
    monkeypatch.setenv('AUTO_REGISTER_WEBHOOK', 'true')
    app = await main.create_app()
    user = {'id': 12345, 'is_bot': False, 'first_name': 'Test'}
    seq = 0

    def message(text, mid=1, chat=None):
        result = {'message_id': mid, 'date': 1700000000,
                  'chat': chat or {'id': 12345, 'type': 'private'}, 'from': user, 'text': text}
        if text.startswith('/'):
            result['entities'] = [{'type': 'bot_command', 'offset': 0, 'length': len(text.split()[0])}]
        return result

    async with TestClient(TestServer(app)) as client:
        assert (await client.get('/healthz')).status == 200
        for headers in ({}, {'X-Telegram-Bot-Api-Secret-Token': 'wrong'}):
            assert (await client.post('/webhook', json={'update_id': 1}, headers=headers)).status == 401
        assert len(session.calls) == 2
        assert isinstance(session.calls[0], SetWebhook)
        assert session.calls[0].url == 'https://syrlasy-test.onrender.com/webhook'
        assert session.calls[0].secret_token == 'test-secret'
        assert set(session.calls[0].allowed_updates) == {'message', 'callback_query'}
        assert (await client.get('/livez')).status == 200

        async def update(body):
            nonlocal seq
            seq += 1
            response = await client.post('/webhook', json={'update_id': seq, **body},
                                        headers={'X-Telegram-Bot-Api-Secret-Token': 'test-secret'})
            assert response.status == 200, await response.text()

        async def callback(data):
            await update({'callback_query': {'id': 'cb', 'from': user, 'chat_instance': 'ci',
                                            'data': data, 'message': message('menu')}})

        await update({'message': message('/start')})
        assert session.calls[-1].reply_markup.inline_keyboard[0][0].callback_data == 'lang:ru'
        for lang in ('ru', 'kz'):
            await callback('lang:' + lang)
            assert await db.get_language(12345) == lang
            await update({'message': message('/start')})
            assert session.calls[-1].text == texts[lang]['welcome']
            for data, key in [('func:phones', 'phones'), ('func:info', 'info'),
                              ('func:chat', 'chat'), ('func:emo_test', 'emotional_test'),
                              ('info:methods', 'bulling_info'), ('info:test', 'test'),
                              ('info:todo', 'instr'), ('back:menu', 'welcome'), ('back:info', 'info')]:
                await callback(data)
                assert session.calls[-1].text == texts[lang][key]
        for data, status, mid in [('appeal:anon', 'anon', 20), ('appeal:not_anon', 'named', 21)]:
            await callback(data)
            # Reconnect the database to simulate persistence between requests.
            await db.close_db()
            await db.init_db()
            await update({'message': message('support fixture', mid)})
            assert await db.get_link(900) == (12345, mid)
            assert await db.pool().fetchval('SELECT status FROM support_messages WHERE admin_message_id=900') == status
            assert session.calls[-1].text == texts['kz']['appeal_send']
        reply = message('admin response', 30, {'id': anon_appeals.ADMIN_CHAT_ID, 'type': 'group'})
        reply['reply_to_message'] = message('copied', 900)
        await update({'message': reply})
        assert isinstance(session.calls[-1], CopyMessage)
        assert session.calls[-1].chat_id == 12345
        assert session.calls[-1].reply_to_message_id == 21
        await update({'message': message('/change_language')})
        assert session.calls[-1].reply_markup.inline_keyboard[0][0].callback_data == 'lang:ru'
        def unavailable():
            raise RuntimeError('database unavailable')
        monkeypatch.setattr(main, 'pool', unavailable)
        assert (await client.get('/healthz')).status == 503
        assert (await client.get('/livez')).status == 200
    assert session.closed
