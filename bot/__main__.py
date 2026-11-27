import asyncio

from aiogram import Bot, Dispatcher
from sqlalchemy.ext.asyncio import async_sessionmaker

from .config import Settings
from .db import open_database
from .handlers import router


async def main():
    settings = Settings.load()
    engine = await open_database(settings.database_url)
    try:
        dispatcher = Dispatcher()
        dispatcher.include_router(router)
        async with Bot(settings.token) as bot:
            await dispatcher.start_polling(
                bot, sessions=async_sessionmaker(engine, expire_on_commit=False),
                zone=settings.timezone, handle_as_tasks=False, close_bot_session=False,
            )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
