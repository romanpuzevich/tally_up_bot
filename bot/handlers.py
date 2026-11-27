from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.filters.callback_data import CallbackData
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import async_sessionmaker

from . import accounting as ledger

router = Router()
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")


class Action(CallbackData, prefix="draft"):
    kind: str
    draft_id: int
    category: str = ""


def keyboard(draft_id: int, categories: bool = False):
    choices = ([(category, "choose", category) for category in ledger.KEYWORDS]
               if categories else [("Записать", "save", ""), ("Категория", "menu", ""),
                                   ("Отмена", "cancel", "")])
    buttons = [InlineKeyboardButton(text=label, callback_data=Action(
        kind=kind, draft_id=draft_id, category=category).pack())
        for label, kind, category in choices]
    return InlineKeyboardMarkup(inline_keyboard=[[b] for b in buttons] if categories else [buttons])


def entry(row):
    return f"{ledger.money(row.kopecks)} · {row.category} · {row.description}"


def preview(row):
    line = entry(row)
    return line if len(line) <= 4096 else line[:4095] + "…"


@router.message(CommandStart())
async def start(message: Message):
    await message.answer("Отправьте сумму в рублях и описание, например «350 кофе». "
                         "Проверьте категорию и нажмите «Записать». Расходы за день — /today.")


@router.message(Command("today"))
async def report(message: Message, sessions: async_sessionmaker, zone: ZoneInfo):
    async with sessions() as session:
        rows, total = await ledger.today(session, message.from_user.id, zone)
    lines = ["Расходы за сегодня" if rows else "Сегодня расходов пока нет.",
             *(entry(row) for row in rows), f"Итого: {ledger.money(total)}"]
    report_text = "\n".join(lines)
    while len(report_text) > 4096:
        split = report_text.rfind("\n", 1, 4097)
        if split == -1:
            split = 4096
        await message.answer(report_text[:split])
        report_text = report_text[split:].removeprefix("\n")
    if report_text:
        await message.answer(report_text)


@router.message(F.text)
async def draft(message: Message, sessions: async_sessionmaker):
    try:
        async with sessions() as session:
            row = await ledger.create_draft(session, message.from_user.id, message.text)
    except ValueError:
        await message.answer(ledger.EXAMPLE)
        return
    await message.answer(preview(row), reply_markup=keyboard(row.id))


@router.callback_query(Action.filter())
async def act(query: CallbackQuery, callback_data: Action, sessions: async_sessionmaker):
    owner, draft_id = query.from_user.id, callback_data.draft_id
    kind = callback_data.kind
    markup = None
    result = None
    async with sessions() as session:
        if kind == "save" and await ledger.confirm(session, owner, draft_id):
            result = "Расход сохранён."
        elif kind == "cancel" and await ledger.cancel(session, owner, draft_id):
            result = "Черновик отменён."
        elif kind == "menu":
            row = await ledger.get_pending(session, owner, draft_id)
            if row:
                result = "Выберите категорию"
                markup = keyboard(draft_id, categories=True)
        elif kind == "choose" and callback_data.category in ledger.KEYWORDS:
            row = await ledger.change_category(session, owner, draft_id, callback_data.category)
            if row:
                result = preview(row)
                markup = keyboard(draft_id)
    if result is None:
        await query.answer("Черновик недоступен или уже обработан.")
        return
    await query.answer()
    if query.message.text != result or query.message.reply_markup != markup:
        await query.message.edit_text(result, reply_markup=markup)
