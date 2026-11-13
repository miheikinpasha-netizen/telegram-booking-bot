import json
import sqlite3
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from booking_bot.config import PROJECT_ROOT, Settings, WorkHours, load_catalog, parse_catalog
from booking_bot.db import Database
from booking_bot.schedule import all_slots, available_days, free_slots, overlaps
from booking_bot.slots import ANY_MASTER, days_with_slots, free_masters_at, slots_for

TZ = ZoneInfo("Europe/Moscow")
HOURS = WorkHours(
    start=time(10, 0), end=time(12, 0), slot_step_min=30, days_ahead=7,
    weekdays=frozenset(range(5)),  # пн–пт
)
DAY = date(2026, 11, 16)  # понедельник


def at(h: int, m: int = 0, day: date = DAY) -> datetime:
    return datetime.combine(day, time(h, m), tzinfo=TZ)


# ---------- schedule ----------


def test_overlaps_touching_intervals_do_not_overlap():
    assert not overlaps((at(10), at(11)), (at(11), at(12)))
    assert overlaps((at(10), at(11)), (at(10, 30), at(11, 30)))


def test_all_slots_service_must_finish_before_closing():
    # 60-минутная услуга, приём до 12:00 → последний старт в 11:00
    assert all_slots(DAY, 60, HOURS, TZ) == [at(10), at(10, 30), at(11)]


def test_available_days_skips_weekends():
    days = available_days(date(2026, 11, 13), HOURS)  # пятница
    assert date(2026, 11, 14) not in days and date(2026, 11, 15) not in days
    assert days[0] == date(2026, 11, 13)


def test_free_slots_excludes_busy_and_past():
    busy = [(at(10, 30), at(11, 30))]
    now = at(9)
    assert free_slots(DAY, 30, HOURS, TZ, busy, now) == [at(10), at(11, 30)]
    assert free_slots(DAY, 30, HOURS, TZ, [], at(11)) == [at(11, 30)]


# ---------- db ----------


@pytest.fixture
def db(tmp_path: Path):
    database = Database(tmp_path / "test.sqlite3")
    yield database
    database.close()


def book(db: Database, start: datetime, minutes: int = 60, user_id: int = 1, master: str = "anna"):
    return db.create_booking(
        user_id=user_id, user_name="Анна", phone="+79990000000", service_id="haircut",
        master_id=master, starts_at=start, ends_at=start + timedelta(minutes=minutes),
    )


def test_double_booking_is_rejected_per_master(db):
    assert book(db, at(10)) is not None
    assert book(db, at(10, 30), user_id=2) is None  # пересекается у того же мастера
    assert book(db, at(10, 30), user_id=2, master="igor") is not None  # другой мастер свободен
    assert book(db, at(11), user_id=2) is not None  # стык — можно


def test_cancel_frees_slot_and_checks_owner(db):
    first = book(db, at(10))
    assert db.cancel(first.id, user_id=999) is None  # чужую отменить нельзя
    assert db.cancel(first.id, user_id=1).status == "cancelled"
    assert db.cancel(first.id, user_id=1) is None  # повторно — нет
    assert book(db, at(10), user_id=2) is not None


def test_times_roundtrip_with_timezone(db):
    b = book(db, at(10))
    assert b.starts_at == at(10)
    assert db.busy_intervals("anna", at(0), at(23)) == [(at(10), at(11))]
    assert db.busy_intervals("igor", at(0), at(23)) == []


def test_reschedule_checks_owner_conflicts_and_resets_reminder(db):
    b = book(db, at(10))
    book(db, at(11), user_id=2)
    db.mark_reminded(b.id)

    assert db.reschedule(b.id, starts_at=at(13), ends_at=at(14), user_id=999) is None  # чужая
    assert db.reschedule(b.id, starts_at=at(11), ends_at=at(12), user_id=1) is None  # занято
    assert db.reschedule(b.id, starts_at=at(10, 30), ends_at=at(11, 30), user_id=1) is None
    # Пересечение только с самой собой конфликтом не считается
    moved = db.reschedule(b.id, starts_at=at(9, 30), ends_at=at(10, 30), user_id=1)
    assert moved is not None and moved.starts_at == at(9, 30)
    assert [r.id for r in db.due_reminders(at(8), timedelta(hours=2))] == [b.id]  # напомнит снова


def test_due_reminders_once(db):
    b = book(db, at(11))
    now = at(9, 30)
    assert [r.id for r in db.due_reminders(now, timedelta(hours=2))] == [b.id]
    db.mark_reminded(b.id)
    assert db.due_reminders(now, timedelta(hours=2)) == []


def test_upcoming_for_user_hides_past_and_cancelled(db):
    past = book(db, at(10, day=date(2026, 11, 2)))
    future = book(db, at(10))
    cancelled = book(db, at(11))
    db.cancel(cancelled.id)
    ids = [b.id for b in db.upcoming_for_user(1, at(9, day=date(2026, 11, 10)))]
    assert ids == [future.id] and past.id not in ids


def test_between_can_be_limited_to_one_user(db):
    mine = book(db, at(10), user_id=1)
    book(db, at(10), user_id=2, master="igor")
    assert len(db.between(at(0), at(23))) == 2
    assert [b.id for b in db.between(at(0), at(23), user_id=1)] == [mine.id]


def test_demo_flag(db):
    assert not db.is_demo(5)
    db.set_demo(5, True)
    db.set_demo(5, True)  # повторно — без ошибки
    assert db.is_demo(5)
    db.set_demo(5, False)
    assert not db.is_demo(5)


def test_migration_from_database_without_masters(tmp_path):
    path = tmp_path / "old.sqlite3"
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE bookings (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, "
        "user_name TEXT NOT NULL, phone TEXT NOT NULL, service_id TEXT NOT NULL, "
        "starts_at TEXT NOT NULL, ends_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'active', "
        "reminded INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL)"
    )
    conn.execute(
        "INSERT INTO bookings (user_id, user_name, phone, service_id, starts_at, ends_at, created_at) "
        "VALUES (1, 'Анна', '+7999', 'haircut', '2026-11-16T07:00:00+00:00', "
        "'2026-11-16T08:00:00+00:00', '2026-11-13T00:00:00+00:00')"
    )
    conn.commit()
    conn.close()

    database = Database(path, default_master="anna")
    try:
        assert database.get(1).master_id == "anna"
        assert database.busy_intervals("anna", at(0), at(23)) == [(at(10), at(11))]
    finally:
        database.close()


# ---------- каталог ----------

CATALOG = {
    "business_name": "Тест",
    "work_hours": {"start": "10:00", "end": "12:00", "slot_step_min": 30, "days_ahead": 7,
                   "weekdays": [0, 1, 2, 3, 4]},
    "services": [
        {"id": "haircut", "name": "Стрижка", "duration_min": 60, "price": 1000},
        {"id": "mens", "name": "Мужская", "duration_min": 30, "price": 500},
    ],
    "masters": [
        {"id": "anna", "name": "Анна", "services": ["haircut"]},
        {"id": "igor", "name": "Игорь", "services": ["haircut", "mens"],
         "start": "11:00", "end": "12:00", "weekdays": [0]},
    ],
    "faq": [{"q": "Где?", "a": "Тут"}],
}


def make_settings(tmp_path: Path, data: dict = CATALOG) -> Settings:
    path = tmp_path / "services.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return Settings(
        bot_token="x", admin_ids=frozenset({1}), tz=TZ, db_path=tmp_path / "db.sqlite3",
        catalog=load_catalog(path),
    )


def test_example_catalog_loads():
    catalog = load_catalog(PROJECT_ROOT / "services.json")
    assert catalog.business_name and catalog.services and catalog.masters
    assert catalog.hours.start < catalog.hours.end
    for master in catalog.masters:
        assert master.service_ids <= {s.id for s in catalog.services}


def test_catalog_without_masters_gets_one_default_master():
    data = {k: v for k, v in CATALOG.items() if k != "masters"}
    catalog = parse_catalog(data)
    assert [m.id for m in catalog.masters] == ["main"]
    assert catalog.masters[0].does("mens")


def test_catalog_rejects_unknown_service_for_master():
    data = dict(CATALOG, masters=[{"id": "x", "name": "X", "services": ["nope"]}])
    with pytest.raises(ValueError):
        parse_catalog(data)


def test_master_inherits_and_overrides_hours():
    anna, igor = parse_catalog(CATALOG).masters
    assert anna.hours.start == time(10) and anna.hours.weekdays == frozenset(range(5))
    assert igor.hours.start == time(11) and igor.hours.weekdays == frozenset({0})


def test_update_service_persists_to_file(tmp_path):
    settings = make_settings(tmp_path)
    settings.catalog.update_service("haircut", price=1500, active=False)
    assert settings.service("haircut").price == 1500
    assert [s.id for s in settings.catalog.active_services()] == ["mens"]

    reloaded = load_catalog(settings.catalog.path)
    assert reloaded.service("haircut").price == 1500 and not reloaded.service("haircut").active
    with pytest.raises(ValueError):
        settings.catalog.update_service("haircut", name="Взлом")


# ---------- слоты с мастерами ----------


def test_any_master_unions_free_time_and_picks_free_master(tmp_path):
    settings = make_settings(tmp_path)
    db = Database(settings.db_path)
    try:
        haircut = settings.service("haircut")
        now = at(8)
        # Анна 10–12 (старты 10:00, 10:30, 11:00), Игорь 11–12 (старт 11:00)
        assert slots_for(db, settings, haircut, "anna", DAY, now) == [at(10), at(10, 30), at(11)]
        assert slots_for(db, settings, haircut, "igor", DAY, now) == [at(11)]

        book(db, at(11), master="anna")
        assert slots_for(db, settings, haircut, "anna", DAY, now) == [at(10)]
        # 11:00 всё ещё доступно «любому мастеру» — у Игоря
        assert at(11) in slots_for(db, settings, haircut, ANY_MASTER, DAY, now)
        free = free_masters_at(db, settings, haircut, ANY_MASTER, at(11), now)
        assert [m.id for m in free] == ["igor"]

        mens = settings.service("mens")
        assert slots_for(db, settings, mens, "anna", DAY, now) == []  # Анна не делает мужские
        assert days_with_slots(db, settings, mens, "igor", now) == [DAY]  # Игорь только по пн
    finally:
        db.close()


def test_slots_for_reschedule_ignore_booking_itself(tmp_path):
    settings = make_settings(tmp_path)
    db = Database(settings.db_path)
    try:
        haircut = settings.service("haircut")
        b = book(db, at(10), master="anna")
        assert at(10, 30) not in slots_for(db, settings, haircut, "anna", DAY, at(8))
        assert at(10, 30) in slots_for(db, settings, haircut, "anna", DAY, at(8), exclude_id=b.id)
    finally:
        db.close()


def test_handlers_import():
    # Проверяет, что все модули бота собираются без ошибок импорта.
    from booking_bot import main, notify, reminders  # noqa: F401
    from booking_bot.handlers import admin, client  # noqa: F401
