from itertools import count
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher
from aiogram.types import Update

from bot.handlers import router


async def test_private_chat_flow(sessions):
    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    seq = count(1)
    async with Bot("123456:test") as bot:
        request = AsyncMock(return_value=True)
        bot.session.make_request = request

        async def send(text=None, button=None, chat_type="private"):
            n = next(seq)
            user = {"id": 10, "is_bot": False, "first_name": "Анна"}
            message = {"message_id": n, "date": 1000, "chat": {"id": 10, "type": chat_type},
                       "from": user, "text": text or "Черновик"}
            payload = {"message": message} if button is None else {"callback_query": {
                "id": str(n), "from": user, "message": message,
                "chat_instance": "instance", "data": button.callback_data}}
            await dispatcher.feed_update(bot, Update.model_validate({"update_id": n, **payload}),
                                         sessions=sessions, zone=ZoneInfo("Europe/Moscow"))
            return request.await_args.args[1]

        assert "350 кофе" in (await send("/start")).text
        assert "350 кофе" in (await send("кофе")).text
        draft = await send("349,90 кофе")
        assert draft.text == "349,90 ₽ · Кафе · кофе"
        buttons = draft.reply_markup.inline_keyboard[0]
        assert [b.text for b in buttons] == ["Записать", "Категория", "Отмена"]
        menu = await send(button=buttons[1])
        home = next(b for row in menu.reply_markup.inline_keyboard for b in row if b.text == "Дом")
        edited = await send(button=home)
        assert edited.text == "349,90 ₽ · Дом · кофе"
        assert "сохранён" in (await send(button=buttons[0])).text
        assert "Итого: 349,90 ₽" in (await send("/today")).text
        second = await send("7 хлеб")
        assert "отменён" in (await send(button=second.reply_markup.inline_keyboard[0][2])).text
        assert "хлеб" not in (await send("/today")).text
        calls = request.await_count
        await send("10 кофе", chat_type="group")
        assert request.await_count == calls
