import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from bot.db import open_database


@pytest.fixture
async def sessions(tmp_path):
    engine = await open_database(f"sqlite+aiosqlite:///{tmp_path}/data/bot.db")
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()
