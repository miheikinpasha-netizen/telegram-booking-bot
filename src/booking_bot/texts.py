"""Форматирование сообщений. Всё, что пришло от пользователя, экранируется."""

from __future__ import annotations

from datetime import date, datetime
from html import escape
from zoneinfo import ZoneInfo

from booking_bot.config import Master, Service, Settings
from booking_bot.db import Booking

WEEKDAYS = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
MONTHS = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]

BTN_BOOK = "📅 Записаться"
BTN_MY = "📋 Мои записи"
BTN_PRICES = "💰 Услуги и цены"
BTN_FAQ = "❓ Частые вопросы"
BTN_ADMIN = "👀 Как это видит администратор"

DEMO_NOTE = "👀 <i>Демо: так это сообщение увидит администратор салона</i>\n\n"

__all__ = ["escape"]


def fmt_day(day: date) -> str:
    return f"{WEEKDAYS[day.weekday()]}, {day.day} {MONTHS[day.month - 1]}"


def fmt_dt(value: datetime, tz: ZoneInfo) -> str:
    local = value.astimezone(tz)
    return f"{fmt_day(local.date())}, {local:%H:%M}"


def fmt_price(price: int) -> str:
    return f"{price:,}".replace(",", " ") + " ₽"


def fmt_weekdays(days: frozenset[int]) -> str:
    return ", ".join(WEEKDAYS[d] for d in sorted(days))


def price_list(settings: Settings) -> str:
    catalog = settings.catalog
    lines = [f"<b>{escape(catalog.business_name)}</b>\n"]
    for s in catalog.active_services():
        lines.append(f"• {escape(s.name)}: {fmt_price(s.price)}, {s.duration_min} мин")
    if len(catalog.masters) > 1:
        lines.append("\n<b>Мастера</b>")
        for m in catalog.masters:
            h = m.hours
            lines.append(
                f"• {escape(m.name)}: {fmt_weekdays(h.weekdays)}, {h.start:%H:%M}–{h.end:%H:%M}"
            )
    return "\n".join(lines)


def master_name(settings: Settings, master_id: str) -> str | None:
    """Имя мастера для показа. None, если мастер один (тогда его не упоминаем)."""
    if len(settings.catalog.masters) < 2:
        return None
    master = settings.catalog.master(master_id)
    return master.name if master else master_id


def booking_card(booking: Booking, settings: Settings, *, for_admin: bool) -> str:
    service = settings.service(booking.service_id)
    service_name = escape(service.name) if service else escape(booking.service_id)
    lines = [f"<b>{service_name}</b>", f"🕒 {fmt_dt(booking.starts_at, settings.tz)}"]
    if (name := master_name(settings, booking.master_id)) is not None:
        lines.append(f"💇 Мастер: {escape(name)}")
    if service:
        lines.append(f"💰 {fmt_price(service.price)}")
    if for_admin:
        lines.append(
            f'👤 {escape(booking.user_name)} (<a href="tg://user?id={booking.user_id}">профиль</a>)'
        )
        lines.append(f"📞 {escape(booking.phone)}")
        lines.append(f"№ {booking.id}")
    return "\n".join(lines)


def summary(
    service: Service, master: Master | None, start: datetime, name: str, phone: str, tz: ZoneInfo
) -> str:
    lines = ["Проверьте запись:\n", f"<b>{escape(service.name)}</b>", f"🕒 {fmt_dt(start, tz)}"]
    if master is not None:
        lines.append(f"💇 Мастер: {escape(master.name)}")
    lines += [f"💰 {fmt_price(service.price)}", f"👤 {escape(name)}", f"📞 {escape(phone)}"]
    return "\n".join(lines)


def service_admin_card(service: Service) -> str:
    status = "показывается клиентам" if service.active else "скрыта от клиентов"
    return (
        f"<b>{escape(service.name)}</b>\n"
        f"💰 Цена: {fmt_price(service.price)}\n"
        f"⏱ Длительность: {service.duration_min} мин\n"
        f"👁 Статус: {status}"
    )


ADMIN_HELP = (
    "<b>Панель администратора</b>\n\n"
    "• Расписание на сегодня, завтра и неделю — с кнопкой отмены у каждой записи\n"
    "• Услуги и цены — меняются прямо здесь, без программиста\n"
    "• О каждой новой записи, переносе и отмене приходит уведомление\n\n"
    "Команды: /today, /tomorrow, /week, /admin"
)

DEMO_INTRO = (
    "👀 <b>Демо-режим администратора</b>\n\n"
    "Вы видите бот глазами владельца салона, но только на своих записях — "
    "чужие данные не показываются.\n\n"
    "Попробуйте: запишитесь через «📅 Записаться» — придёт уведомление, как администратору. "
    "Затем откройте расписание или поменяйте цену услуги (в демо изменения не сохраняются)."
)
