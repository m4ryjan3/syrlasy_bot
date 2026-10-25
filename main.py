from aiogram import Bot, Dispatcher
from dotenv import load_dotenv
import os
import asyncio

from handlers import rt as router_handler
from anon_appeals import router as router_anon

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=TOKEN)
dp = Dispatcher()
dp.include_router(router_handler)
dp.include_router(router_anon)

async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
