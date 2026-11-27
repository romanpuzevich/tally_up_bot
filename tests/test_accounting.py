import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from bot import accounting as a

MOSCOW = ZoneInfo("Europe/Moscow")


@pytest.mark.parametrize("text,amount", [
    ("350 кофе", 35000), ("349,90 кофе", 34990), ("349.90 кофе", 34990),
    ("0,01 кофе", 1), (" 2.5 кофе ", 250), ("92233720368547758.07 кофе", 2**63-1),
])
def test_amount(text, amount):
    assert a.parse(text) == (amount, "кофе")


@pytest.mark.parametrize("text", ["0 кофе", "-1 кофе", "0.001 кофе", "кофе", "5  ",
                                  "1e3 кофе", "92233720368547758.08 кофе"])
def test_invalid(text):
    with pytest.raises(ValueError, match="350 кофе"):
        a.parse(text)


async def call(sessions, function, *args):
    async with sessions() as session:
        return await function(session, *args)


async def test_double_confirm(sessions):
    draft = await call(sessions, a.create_draft, 1, "349,90 кофе")
    assert draft.category == "Кафе"
    results = await asyncio.gather(*(call(sessions, a.confirm, 1, draft.id) for _ in range(2)))
    assert sorted(results) == [False, True]
    assert not await call(sessions, a.confirm, 1, draft.id)
    assert not await call(sessions, a.cancel, 1, draft.id)
    rows, total = await call(sessions, a.today, 1, MOSCOW)
    assert [r.draft_id for r in rows] == [draft.id]
    assert total == 34990


async def test_cancel(sessions):
    draft = await call(sessions, a.create_draft, 1, "5 перо")
    assert draft.category == "Другое"
    assert await call(sessions, a.today, 1, MOSCOW) == ([], 0)
    assert await call(sessions, a.cancel, 1, draft.id)
    assert not await call(sessions, a.confirm, 1, draft.id)
    assert await call(sessions, a.today, 1, MOSCOW) == ([], 0)


async def test_owner(sessions):
    first = await call(sessions, a.create_draft, 11, "12 хлеб")
    other = await call(sessions, a.create_draft, 22, "78 метро")
    assert first.budget_id != other.budget_id
    assert not await call(sessions, a.get_pending, 22, first.id)
    assert not await call(sessions, a.change_category, 22, first.id, "Дом")
    assert not await call(sessions, a.cancel, 22, first.id)
    assert not await call(sessions, a.confirm, 22, first.id)
    await call(sessions, a.change_category, 11, first.id, "Кафе")
    await call(sessions, a.confirm, 11, first.id)
    await call(sessions, a.confirm, 22, other.id)
    for owner, amount, category in [(11, 1200, "Кафе"), (22, 7800, "Транспорт")]:
        rows, total = await call(sessions, a.today, owner, MOSCOW)
        assert total == amount
        assert [r.category for r in rows] == [category]


async def test_local_midnight(sessions):
    for stamp in ["01T20:59:59", "01T21:00:00", "02T20:59:59", "02T21:00:00"]:
        draft = await call(sessions, a.create_draft, 1, f"1 {stamp}")
        await call(sessions, a.confirm, 1, draft.id, datetime.fromisoformat(f"2026-01-{stamp}Z"))
    rows, total = await call(sessions, a.today, 1, MOSCOW,
                             datetime.fromisoformat("2026-01-01T23:00:00Z"))
    assert [row.description for row in rows] == ["01T21:00:00", "02T20:59:59"]
    assert total == 200


async def test_reopen_database(tmp_path):
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from bot.db import open_database

    url = f"sqlite+aiosqlite:///{tmp_path}/persist/bot.db"
    engine = await open_database(url)
    try:
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        saved = await call(sessions, a.create_draft, 1, "3 хлеб")
        pending = await call(sessions, a.create_draft, 1, "2 кофе")
        await call(sessions, a.confirm, 1, saved.id)
    finally:
        await engine.dispose()

    engine = await open_database(url)
    try:
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        assert await call(sessions, a.confirm, 1, pending.id)
        rows, total = await call(sessions, a.today, 1, MOSCOW)
        assert {row.draft_id for row in rows} == {saved.id, pending.id}
        assert total == 500
    finally:
        await engine.dispose()
