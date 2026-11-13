"""Сквозной сценарий через диспетчер aiogram без Telegram: сессия подменена, апдейты подаются вручную.

Проверяет связку обработчиков, кнопок и базы: запись, перенос, права, демо-режим, цены.
"""

import asyncio
import json
import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import SendMessage, TelegramMethod
from aiogram.types import Message, Update

from booking_bot.config import PROJECT_ROOT, Settings, load_catalog
from booking_bot.db import Database
from booking_bot.handlers import admin, client

ADMIN = 100
CLIENT = 555
STRANGER = 777


class FakeSession(BaseSession):
    """Запоминает всё, что бот отправил бы в Telegram."""

    def __init__(self):
        super().__init__()
        self.sent: list[tuple[int, str, list[str]]] = []
        self.calls: list[tuple[str, dict]] = []  # (метод API, параметры)
        self.fail: dict[str, str] = {}  # метод API → текст ошибки Telegram

    async def close(self):
        pass

    async def make_request(self, bot, method: TelegramMethod, timeout=None):
        data = method.model_dump()
        markup = data.get("reply_markup") or {}
        cbs = [b["callback_data"] for row in markup.get("inline_keyboard") or [] for b in row]
        assert all(len(cb.encode()) <= 64 for cb in cbs), cbs  # лимит Telegram
        self.sent.append((data.get("chat_id") or 0, data.get("text") or "", cbs))
        self.calls.append((method.__api_method__, data))
        if method.__api_method__ in self.fail:
            error = self.fail[method.__api_method__]
            raise TelegramBadRequest(method=method, message=f"Bad Request: {error}")
        if isinstance(method, SendMessage) or method.__returning__ is Message:
            return Message.model_validate(
                {"message_id": len(self.sent), "date": 0,
                 "chat": {"id": data["chat_id"], "type": "private"}, "text": data.get("text", "")}
            )
        return True

    async def stream_content(self, *args, **kwargs):
        yield b""

    def buttons(self, prefix: str) -> list[str]:
        for _, _, cbs in reversed(self.sent):
            found = [c for c in cbs if c.startswith(prefix)]
            if found:
                return found
        raise AssertionError(f"нет кнопок {prefix}")

    def texts(self, chat: int) -> list[str]:
        return [t for c, t, _ in self.sent if c == chat]


class Harness:
    def __init__(self, tmp_path: Path, *, widgets: bool = False):
        shutil.copy(PROJECT_ROOT / "services.json", tmp_path / "services.json")
        self.services_file = tmp_path / "services.json"
        self.settings = Settings(
            bot_token="1:x", admin_ids=frozenset({ADMIN}), tz=ZoneInfo("Europe/Moscow"),
            db_path=tmp_path / "db.sqlite3", catalog=load_catalog(self.services_file),
            demo_mode=True, widgets=widgets,
        )
        self.db = Database(self.settings.db_path, default_master="anna")
        self.session = FakeSession()
        self.bot = Bot("1:x", session=self.session)
        self.dp = Dispatcher(storage=MemoryStorage(), settings=self.settings, db=self.db)
        for router in (admin.router, client.router):
            router._parent_router = None  # роутеры модульные: в тестах их берут несколько диспетчеров
            self.dp.include_router(router)
        if widgets:
            from booking_bot.widget import WidgetQueryMiddleware

            self.dp.update.outer_middleware(WidgetQueryMiddleware(self.dp.storage))
        self._id = 0

    async def widget_tap(self, user: int, message_id: int, data: str):
        """Нажатие в виджете: так Telegram присылает widget_query (Bot API 10.4)."""
        self._id += 1
        raw = {"update_id": self._id, "widget_query": {
            "id": f"wq{self._id}", "from": {"id": user, "is_bot": False, "first_name": "U"},
            "chat": {"id": user, "type": "private"}, "message_id": message_id,
            "chat_instance": "1", "data": data}}
        await self.dp.feed_update(self.bot, Update.model_validate(raw))

    async def send(self, user: int, *, text=None, cb=None, contact=None):
        self._id += 1
        frm = {"id": user, "is_bot": False, "first_name": "U"}
        msg = {"message_id": 1, "date": 0, "chat": {"id": user, "type": "private"}, "from": frm}
        if text is not None:
            msg["text"] = text
            if text.startswith("/"):
                msg["entities"] = [{"type": "bot_command", "offset": 0, "length": len(text)}]
        if contact:
            msg["contact"] = {"phone_number": contact, "first_name": "U", "user_id": user}
        if cb is not None:
            raw = {"update_id": self._id, "callback_query": {
                "id": str(self._id), "from": frm, "chat_instance": "1", "data": cb, "message": msg}}
        else:
            raw = {"update_id": self._id, "message": msg}
        await self.dp.feed_update(self.bot, Update.model_validate(raw))


async def scenario(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    s, db, tg = h.settings, h.db, h.session

    await h.send(CLIENT, text="/start")
    await h.send(CLIENT, text="❓ Частые вопросы")
    await h.send(CLIENT, cb=tg.buttons("faq")[0])
    assert "Примерная" in tg.texts(CLIENT)[-1]

    # демо-режим администратора
    await h.send(CLIENT, text="👀 Как это видит администратор")
    assert db.is_demo(CLIENT)

    # запись: стрижка → любой мастер → дата → время → имя → телефон → подтверждение
    await h.send(CLIENT, text="📅 Записаться")
    await h.send(CLIENT, cb="svc:haircut")
    assert "mst:haircut:any" in tg.buttons("mst:")
    await h.send(CLIENT, cb="mst:haircut:any")
    await h.send(CLIENT, cb=tg.buttons("day:")[0])
    await h.send(CLIENT, cb=tg.buttons("slot:")[0])
    await h.send(CLIENT, text="Пётр")
    await h.send(CLIENT, contact="79991112233")
    await h.send(CLIENT, cb="ok:1")
    bookings = db.upcoming_for_user(CLIENT, datetime.now(s.tz))
    assert len(bookings) == 1
    booking = bookings[0]
    assert any("Новая запись" in t for t in tg.texts(ADMIN))
    assert any("Демо" in t and "Новая запись" in t for t in tg.texts(CLIENT))

    # перенос на последнюю доступную дату и время
    await h.send(CLIENT, text="📋 Мои записи")
    await h.send(CLIENT, cb=f"mv:{booking.id}")
    await h.send(CLIENT, cb=tg.buttons("mvd:")[-1])
    await h.send(CLIENT, cb=tg.buttons("mvs:")[-1])
    moved = db.get(booking.id)
    assert moved.starts_at != booking.starts_at
    assert any("перенёс" in t for t in tg.texts(ADMIN))

    # посторонний не может отменить или перенести чужую запись
    await h.send(STRANGER, cb=f"cnl:{booking.id}")
    await h.send(STRANGER, cb=f"acnl:{booking.id}")
    await h.send(STRANGER, cb=f"mvs:{booking.id}:{int(booking.starts_at.timestamp())}")
    assert db.get(booking.id).status == "active"
    assert db.get(booking.id).starts_at == moved.starts_at

    # демо-админ видит только свои записи; смена цены в демо не сохраняется
    await h.send(CLIENT, cb="adm:week")
    assert any("только ваши записи" in t for t in tg.texts(CLIENT))
    await h.send(CLIENT, cb="adm:services")
    await h.send(CLIENT, cb="sve:haircut:price")
    await h.send(CLIENT, text="9999")
    assert s.service("haircut").price == 1800
    assert "Демо" in tg.texts(CLIENT)[-1]

    # настоящий администратор меняет цену (сохраняется в файл) и скрывает услугу
    await h.send(ADMIN, cb="sve:haircut:price")
    await h.send(ADMIN, text="2 100")
    assert s.service("haircut").price == 2100
    saved = json.loads(h.services_file.read_text(encoding="utf-8"))
    assert next(i for i in saved["services"] if i["id"] == "haircut")["price"] == 2100
    await h.send(ADMIN, cb="sve:mens:toggle")
    assert not s.service("mens").active
    await h.send(CLIENT, text="📅 Записаться")
    assert "svc:mens" not in tg.buttons("svc:")

    # администратор отменяет запись — клиент получает сообщение
    await h.send(ADMIN, cb=f"acnl:{booking.id}")
    assert db.get(booking.id).status == "cancelled"
    assert any("отменена администратором" in t for t in tg.texts(CLIENT))

    await h.send(CLIENT, cb="adm:exit_demo")
    assert not db.is_demo(CLIENT)

    db.close()
    await h.bot.session.close()


def test_full_flow(tmp_path):
    asyncio.run(scenario(tmp_path))
