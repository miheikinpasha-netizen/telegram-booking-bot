"""Календарь-виджет (Telegram Bot API 10.4): данные, лимиты Telegram и полный сценарий записи."""

import asyncio
import json
import shutil
import subprocess
import zlib
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from booking_bot.config import PROJECT_ROOT, Settings, load_catalog
from booking_bot.db import Database
from booking_bot.slots import ANY_MASTER, days_with_slots, slots_for
from booking_bot.widget import (
    CHAT_DATA_LIMIT, WIDGET_HTML, available, build_chat_data, decode_slots, encode_slots,
    parse_request,
)
from test_flow import CLIENT, Harness

TZ = ZoneInfo("Europe/Moscow")


def test_slots_roundtrip():
    day = date(2026, 11, 16)
    slots = [datetime.combine(day, time(h, m), tzinfo=TZ) for h, m in [(10, 0), (10, 30), (19, 55)]]
    encoded = encode_slots(slots, TZ)
    assert encoded[:2] == "3c" and len(encoded) == 6
    assert decode_slots(encoded) == [600, 630, 1195]


def test_html_fits_telegram_limits():
    raw = WIDGET_HTML.encode()
    assert len(raw) <= 32768
    assert len(zlib.compress(raw, 9)) <= 4096
    assert "\x00" not in WIDGET_HTML
    # песочница Telegram ничего не грузит извне — шаблон не должен на это рассчитывать
    for forbidden in ("http://", "https://", "fetch(", "XMLHttpRequest"):
        assert forbidden not in WIDGET_HTML


def test_widget_javascript_is_valid():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node не установлен")
    script = WIDGET_HTML.split("<script>")[1].split("</script>")[0]
    result = subprocess.run([node, "--check", "-"], input=script, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr


def test_parse_request_is_strict():
    assert parse_request("b:haircut:any:20261116:600") == ("haircut", "any", date(2026, 11, 16), 600)
    for bad in [
        "", "b:haircut:any:20261116", "b:hair cut:any:20261116:600", "b:haircut:any:20261399:600",
        "b:haircut:any:20261116:1440", "x:haircut:any:20261116:600", "b:<script>:any:20261116:600",
    ]:
        assert parse_request(bad) is None, bad


def test_chat_data_respects_limit_and_matches_slots(tmp_path):
    shutil.copy(PROJECT_ROOT / "services.json", tmp_path / "services.json")
    settings = Settings(bot_token="x", admin_ids=frozenset({1}), tz=TZ, db_path=tmp_path / "d.sqlite3",
                        catalog=load_catalog(tmp_path / "services.json"), widgets=True)
    db = Database(settings.db_path)
    try:
        now = datetime.combine(date(2026, 11, 16), time(8), tzinfo=TZ)  # понедельник
        for service in settings.catalog.services:
            for master_id in [ANY_MASTER] + [m.id for m in settings.catalog.masters_for(service.id)]:
                assert available(service, master_id)
                raw = build_chat_data(db, settings, service, master_id, now)
                assert len(raw.encode()) <= CHAT_DATA_LIMIT
                data = json.loads(raw)
                days = days_with_slots(db, settings, service, master_id, now)
                assert [d for d, _ in data["d"]] == [d.strftime("%Y%m%d") for d in days][: len(data["d"])]
                expected = [
                    s.hour * 60 + s.minute for s in slots_for(db, settings, service, master_id, days[0], now)
                ]
                assert decode_slots(data["d"][0][1]) == expected
    finally:
        db.close()


def last_call(tg, method: str) -> dict:
    return next(p for m, p in reversed(tg.calls) if m == method)


async def widget_scenario(tmp_path: Path) -> None:
    from booking_bot import widget

    widget.reset_block()
    h = Harness(tmp_path, widgets=True)
    s, db, tg = h.settings, h.db, h.session

    await h.send(CLIENT, text="📅 Записаться")
    await h.send(CLIENT, cb="svc:haircut")
    await h.send(CLIENT, cb="mst:haircut:anna")
    assert "cal:haircut:anna" in tg.buttons("cal:")

    await h.send(CLIENT, cb="cal:haircut:anna")
    params = last_call(tg, "sendWidget")
    # FakeSession выдаёт message_id = порядковый номер вызова API
    widget_message_id = max(i for i, (m, _) in enumerate(tg.calls) if m == "sendWidget") + 1
    assert params["allow_queries"] is True and params["html"] == WIDGET_HTML
    day, encoded = json.loads(params["chat_data"])["d"][0]
    minutes = decode_slots(encoded)[0]

    # подделанный запрос (несуществующая услуга) — отказ
    await h.widget_tap(CLIENT, widget_message_id, "b:nope:anna:20261116:600")
    assert json.loads(last_call(tg, "answerWidgetQuery")["data"])["ok"] == 0

    # нормальное нажатие на время
    await h.widget_tap(CLIENT, widget_message_id, f"b:haircut:anna:{day}:{minutes}")
    answer = json.loads(last_call(tg, "answerWidgetQuery")["data"])
    assert answer["ok"] == 1, answer
    edited = last_call(tg, "editMessageWidgetData")
    assert edited["message_id"] == widget_message_id
    assert json.loads(edited["chat_data"])["sel"] == f"{day}:{minutes}"
    assert tg.texts(CLIENT)[-1].startswith("Как к вам обращаться")

    # дальше — обычный сценарий записи
    await h.send(CLIENT, text="Ольга")
    await h.send(CLIENT, contact="79990001122")
    await h.send(CLIENT, cb="ok:1")
    bookings = db.upcoming_for_user(CLIENT, datetime.now(s.tz))
    assert len(bookings) == 1
    start = bookings[0].starts_at.astimezone(s.tz)
    assert start.strftime("%Y%m%d") == day and start.hour * 60 + start.minute == minutes
    assert bookings[0].master_id == "anna"

    # это же время ещё раз — уже занято: отказ и обновлённый календарь без этого слота
    await h.widget_tap(CLIENT + 1, widget_message_id, f"b:haircut:anna:{day}:{minutes}")
    assert json.loads(last_call(tg, "answerWidgetQuery")["data"])["ok"] == 0
    fresh = dict(json.loads(last_call(tg, "editMessageWidgetData")["chat_data"])["d"])
    assert minutes not in decode_slots(fresh.get(day, ""))

    db.close()
    await h.bot.session.close()


def test_widget_booking_flow(tmp_path):
    asyncio.run(widget_scenario(tmp_path))


def test_calendar_hidden_after_telegram_refuses_widgets(tmp_path):
    from booking_bot import widget

    async def run():
        widget.reset_block()
        h = Harness(tmp_path, widgets=True)
        h.session.fail["sendWidget"] = "INPUT_MEDIA_WIDGET_NOT_ALLOWED"
        await h.send(CLIENT, text="📅 Записаться")
        await h.send(CLIENT, cb="svc:haircut")
        await h.send(CLIENT, cb="mst:haircut:anna")
        await h.send(CLIENT, cb="cal:haircut:anna")
        # клиенту — обычные даты без кнопки календаря, бот запомнил запрет
        assert widget.blocked()
        last_markup = next(cbs for _, _, cbs in reversed(h.session.sent) if cbs)
        assert any(c.startswith("day:") for c in last_markup)
        assert not any(c.startswith("cal:") for c in last_markup)
        # по истечении паузы кнопка вернётся
        later = datetime.now(widget.UTC) + widget.RETRY_AFTER + widget.timedelta(minutes=1)
        assert not widget.blocked(later)
        widget.reset_block()
        h.db.close()
        await h.bot.session.close()

    asyncio.run(run())


def test_calendar_button_hidden_when_widgets_off(tmp_path):
    async def run():
        h = Harness(tmp_path, widgets=False)
        await h.send(CLIENT, text="📅 Записаться")
        await h.send(CLIENT, cb="svc:haircut")
        await h.send(CLIENT, cb="mst:haircut:anna")
        assert not any(c.startswith("cal:") for _, _, cbs in h.session.sent for c in cbs)
        h.db.close()
        await h.bot.session.close()

    asyncio.run(run())
