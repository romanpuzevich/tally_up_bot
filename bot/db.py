from datetime import datetime
from pathlib import Path

from sqlalchemy import ForeignKey, Index
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Budget(Base):
    __tablename__ = "budgets"
    id: Mapped[int] = mapped_column(primary_key=True)
    owner: Mapped[int] = mapped_column(unique=True)


class Draft(Base):
    __tablename__ = "drafts"
    id: Mapped[int] = mapped_column(primary_key=True)
    budget_id: Mapped[int] = mapped_column(ForeignKey("budgets.id"))
    kopecks: Mapped[int]
    description: Mapped[str]
    category: Mapped[str]
    status: Mapped[str] = mapped_column(default="pending")


class Expense(Base):
    __tablename__ = "expenses"
    __table_args__ = (Index("ix_expense_budget_time", "budget_id", "confirmed_utc"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    draft_id: Mapped[int] = mapped_column(ForeignKey("drafts.id"), unique=True)
    budget_id: Mapped[int] = mapped_column(ForeignKey("budgets.id"))
    kopecks: Mapped[int]
    description: Mapped[str]
    category: Mapped[str]
    confirmed_utc: Mapped[datetime]


async def open_database(url: str):
    path = make_url(url).database
    if path and path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    engine = create_async_engine(url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return engine
