"""Свободное время с учётом мастеров: связывает расчёт слотов (schedule) с базой записей."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from booking_bot.config import Master, Service, Settings
from booking_bot.db import Database
from booking_bot.schedule import available_days, free_slots

ANY_MASTER = "any"


def candidate_masters(settings: Settings, service: Service, master_id: str) -> list[Master]:
    """Мастера, среди которых ищем время: выбранный (если он делает услугу) или все подходящие."""
    if master_id == ANY_MASTER:
        return settings.catalog.masters_for(service.id)
    master = settings.catalog.master(master_id)
    return [master] if master is not None and master.does(service.id) else []


def master_free_slots(
    db: Database,
    settings: Settings,
    master: Master,
    duration_min: int,
    day: date,
    now: datetime,
    *,
    exclude_id: int | None = None,
) -> list[datetime]:
    if day not in available_days(now.date(), master.hours):
        return []
    day_start = datetime.combine(day, time.min, tzinfo=settings.tz)
    busy = db.busy_intervals(master.id, day_start, day_start + timedelta(days=1), exclude_id=exclude_id)
    return free_slots(day, duration_min, master.hours, settings.tz, busy, now)


def slots_for(
    db: Database,
    settings: Settings,
    service: Service,
    master_id: str,
    day: date,
    now: datetime,
    *,
    exclude_id: int | None = None,
) -> list[datetime]:
    """Свободные начала приёма в день. Для «любого мастера» — объединение по всем подходящим."""
    found: set[datetime] = set()
    for master in candidate_masters(settings, service, master_id):
        found.update(
            master_free_slots(
                db, settings, master, service.duration_min, day, now, exclude_id=exclude_id
            )
        )
    return sorted(found)


def days_with_slots(
    db: Database,
    settings: Settings,
    service: Service,
    master_id: str,
    now: datetime,
    *,
    exclude_id: int | None = None,
) -> list[date]:
    horizon = max((m.hours.days_ahead for m in settings.catalog.masters), default=0)
    days = (now.date() + timedelta(days=i) for i in range(horizon))
    return [
        d for d in days if slots_for(db, settings, service, master_id, d, now, exclude_id=exclude_id)
    ]


def free_masters_at(
    db: Database, settings: Settings, service: Service, master_id: str, start: datetime, now: datetime
) -> list[Master]:
    """Мастера, у которых это время свободно (для «любого мастера» может быть несколько)."""
    local = start.astimezone(settings.tz)
    return [
        m
        for m in candidate_masters(settings, service, master_id)
        if local in master_free_slots(db, settings, m, service.duration_min, local.date(), now)
    ]
