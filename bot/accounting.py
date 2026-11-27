import re
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession

from .db import Budget, Draft, Expense

KEYWORDS = {
    "Продукты": {"хлеб", "молоко", "овощи"},
    "Кафе": {"кофе", "латте", "кафе", "капучино"},
    "Транспорт": {"метро", "такси", "автобус"},
    "Дом": {"лампа", "мебель", "аренда"},
    "Другое": set(),
}
EXAMPLE = "Введите положительную сумму и описание, например «350 кофе»."


def parse(text: str) -> tuple[int, str]:
    match = re.fullmatch(r"([0-9]+)(?:[,.]([0-9]{1,2}))?\s+(.+)", text.strip(), re.S)
    if not match:
        raise ValueError(EXAMPLE)
    rubles, fraction, description = match.groups()
    digits = rubles.lstrip("0") + (fraction or "").ljust(2, "0")
    if len(digits) > 19 or not 0 < (amount := int(digits)) <= 2**63 - 1:
        raise ValueError(EXAMPLE)
    return amount, description.strip()


def money(kopecks: int) -> str:
    return f"{kopecks // 100},{kopecks % 100:02d} ₽"


async def create_draft(session: AsyncSession, owner: int, text: str) -> Draft:
    amount, description = parse(text)
    words = set(re.findall(r"\w+", description.casefold()))
    category = next((name for name, keys in KEYWORDS.items() if words & keys), "Другое")
    async with session.begin():
        await session.execute(insert(Budget).values(owner=owner).on_conflict_do_nothing(
            index_elements=[Budget.owner]))
        budget_id = await session.scalar(select(Budget.id).where(Budget.owner == owner))
        draft = Draft(budget_id=budget_id, kopecks=amount, description=description,
                      category=category)
        session.add(draft)
    return draft


def owned_pending(owner: int, draft_id: int):
    budget = select(Budget.id).where(Budget.owner == owner).scalar_subquery()
    return (Draft.id == draft_id, Draft.budget_id == budget, Draft.status == "pending")


async def get_pending(session: AsyncSession, owner: int, draft_id: int):
    return await session.scalar(select(Draft).where(*owned_pending(owner, draft_id)))


async def change_category(session: AsyncSession, owner: int, draft_id: int, category: str):
    if category not in KEYWORDS:
        raise ValueError("Неизвестная категория")
    async with session.begin():
        return await session.scalar(update(Draft).where(*owned_pending(owner, draft_id))
                                    .values(category=category).returning(Draft))


async def cancel(session: AsyncSession, owner: int, draft_id: int):
    async with session.begin():
        return await session.scalar(update(Draft).where(*owned_pending(owner, draft_id))
                                    .values(status="cancelled").returning(Draft.id))


async def confirm(session: AsyncSession, owner: int, draft_id: int, now: datetime | None = None):
    async with session.begin():
        draft = await session.scalar(update(Draft).where(*owned_pending(owner, draft_id))
                                     .values(status="confirmed").returning(Draft))
        if draft is None:
            return False
        instant = now or datetime.now(UTC)
        session.add(Expense(draft_id=draft.id, budget_id=draft.budget_id,
                            kopecks=draft.kopecks, description=draft.description,
                            category=draft.category,
                            confirmed_utc=instant.astimezone(UTC).replace(tzinfo=None)))
    return True


async def today(session: AsyncSession, owner: int, zone: ZoneInfo, now: datetime | None = None):
    day = (now or datetime.now(UTC)).astimezone(zone).date()
    start, end = (datetime.combine(d, time.min, zone).astimezone(UTC).replace(tzinfo=None)
                  for d in (day, day + timedelta(days=1)))
    rows = (await session.scalars(select(Expense).join(Budget).where(
        Budget.owner == owner, Expense.confirmed_utc >= start, Expense.confirmed_utc < end
    ).order_by(Expense.confirmed_utc, Expense.id))).all()
    return rows, sum(row.kopecks for row in rows)
