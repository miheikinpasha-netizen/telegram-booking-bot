"""Расчёт рабочих дней и свободных слотов. Чистые функции, без Telegram и БД."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from booking_bot.config import WorkHours

Interval = tuple[datetime, datetime]


def overlaps(a: Interval, b: Interval) -> bool:
    """Пересекаются ли два полуинтервала [start, end)."""
    return a[0] < b[1] and b[0] < a[1]


def available_days(today: date, hours: WorkHours) -> list[date]:
    """Рабочие дни, начиная с сегодняшнего, на days_ahead дней вперёд."""
    days = (today + timedelta(days=i) for i in range(hours.days_ahead))
    return [d for d in days if d.weekday() in hours.weekdays]


def all_slots(day: date, duration_min: int, hours: WorkHours, tz: ZoneInfo) -> list[datetime]:
    """Все начала приёма в течение дня, при которых услуга успевает закончиться."""
    start = datetime.combine(day, hours.start, tzinfo=tz)
    end = datetime.combine(day, hours.end, tzinfo=tz)
    step = timedelta(minutes=hours.slot_step_min)
    duration = timedelta(minutes=duration_min)

    slots: list[datetime] = []
    current = start
    while current + duration <= end:
        slots.append(current)
        current += step
    return slots


def free_slots(
    day: date,
    duration_min: int,
    hours: WorkHours,
    tz: ZoneInfo,
    busy: list[Interval],
    now: datetime,
) -> list[datetime]:
    """Свободные слоты: не в прошлом и не пересекаются с занятыми интервалами."""
    duration = timedelta(minutes=duration_min)
    result = []
    for slot in all_slots(day, duration_min, hours, tz):
        if slot <= now:
            continue
        if any(overlaps((slot, slot + duration), b) for b in busy):
            continue
        result.append(slot)
    return result
