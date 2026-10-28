import asyncio
import logging
import os
import re

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import SimpleEventIsolation
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from dotenv import load_dotenv

load_dotenv()

from anon_appeals import router as router_anon
from databases import PostgresStorage, close_db, init_db, pool
from handlers import rt as router_handler


def create_bot() -> Bot:
    token = os.environ.get('BOT_TOKEN')
    if not token:
        raise RuntimeError('BOT_TOKEN is required')
    proxy = os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy')
    return Bot(token=token, session=AiohttpSession(proxy=proxy))


def create_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=PostgresStorage(), events_isolation=SimpleEventIsolation())
    dp.include_router(router_handler)
    dp.include_router(router_anon)
    return dp


def webhook_secret() -> str:
    secret = os.environ.get('WEBHOOK_SECRET', '')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,256}', secret):
        raise RuntimeError('WEBHOOK_SECRET must contain 1–256 letters, digits, _ or -')
    return secret


def webhook_settings() -> tuple[str, str]:
    url = (os.environ.get('WEBHOOK_BASE_URL') or os.environ.get('RENDER_EXTERNAL_URL', '')).rstrip('/')
    if not url.startswith('https://'):
        raise RuntimeError('WEBHOOK_BASE_URL must be the public HTTPS service URL')
    return url + '/webhook', webhook_secret()


async def create_app() -> web.Application:
    secret = webhook_secret()
    bot = create_bot()
    dp = create_dispatcher()
    app = web.Application()

    async def database_lifespan(app):
        await init_db()
        try:
            yield
        finally:
            await close_db()

    async def live(request):
        return web.json_response({'status': 'ok'})

    async def health(request):
        try:
            await pool().fetchval('SELECT 1')
        except Exception:
            return web.json_response({'status': 'unavailable'}, status=503)
        return web.json_response({'status': 'ok'})

    app.cleanup_ctx.append(database_lifespan)
    app.router.add_get('/livez', live)
    app.router.add_get('/healthz', health)
    SimpleRequestHandler(
        dispatcher=dp, bot=bot, secret_token=secret, handle_in_background=False
    ).register(app, path='/webhook')
    if os.environ.get('AUTO_REGISTER_WEBHOOK', 'false').lower() == 'true':
        async def on_startup():
            await configure_webhook(bot, dp)
        dp.startup.register(on_startup)
    setup_application(app, dp, bot=bot)
    return app


async def polling():
    bot = create_bot()
    try:
        await init_db()
        # Switching to local polling is explicit; keep pending updates.
        await bot.delete_webhook(drop_pending_updates=False)
        await create_dispatcher().start_polling(bot)
    finally:
        await bot.session.close()
        await close_db()


async def configure_webhook(bot: Bot, dp: Dispatcher):
    url, secret = webhook_settings()
    await bot.set_webhook(
        url=url, secret_token=secret, allowed_updates=dp.resolve_used_update_types(),
        max_connections=1, drop_pending_updates=False,
    )
    info = await bot.get_webhook_info()
    if info.url != url:
        raise RuntimeError('Telegram did not retain the requested webhook URL')
    logging.getLogger(__name__).info('Webhook registered; pending updates: %d', info.pending_update_count)


async def register_webhook():
    bot = create_bot()
    try:
        await configure_webhook(bot, create_dispatcher())
    finally:
        await bot.session.close()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    mode = os.environ.get('BOT_MODE', 'polling')
    if mode == 'webhook':
        # Access logs can include user-supplied URLs. Telegram tokens are never URL routes here.
        web.run_app(create_app(), host='0.0.0.0', port=int(os.environ.get('PORT', '8080')), access_log=None)
    elif mode == 'register-webhook':
        asyncio.run(register_webhook())
    elif mode == 'polling':
        asyncio.run(polling())
    else:
        raise SystemExit('BOT_MODE must be polling, webhook or register-webhook')
