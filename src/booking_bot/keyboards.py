"""Клавиатуры и callback-данные (Telegram ограничивает callback_data 64 байтами)."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from booking_bot.config import FaqItem, Master, Service
from booking_bot.db import Booking
from booking_bot.slots import ANY_MASTER
from booking_bot.texts import (
    BTN_ADMIN, BTN_BOOK, BTN_FAQ, BTN_MY, BTN_PRICES, fmt_day, fmt_dt, fmt_price,
)

# ---------- запись ----------


class ServiceCb(CallbackData, prefix="svc"):
    service_id: str


class MasterCb(CallbackData, prefix="mst"):
    service_id: str
    master_id: str


class DayCb(CallbackData, prefix="day"):
    service_id: str
    master_id: str
    day: str  # YYYYMMDD


class SlotCb(CallbackData, prefix="slot"):
    service_id: str
    master_id: str
    ts: int  # unix timestamp начала


class NavCb(CallbackData, prefix="nav"):
    to: str  # services | masters | days | abort
    service_id: str = ""
    master_id: str = ""


class ConfirmCb(CallbackData, prefix="ok"):
    yes: bool


class CalendarCb(CallbackData, prefix="cal"):
    service_id: str
    master_id: str


# ---------- мои записи и перенос ----------


class CancelCb(CallbackData, prefix="cnl"):
    booking_id: int


class MoveCb(CallbackData, prefix="mv"):
    booking_id: int


class MoveDayCb(CallbackData, prefix="mvd"):
    booking_id: int
    day: str


class MoveSlotCb(CallbackData, prefix="mvs"):
    booking_id: int
    ts: int


class MoveAbortCb(CallbackData, prefix="mvx"):
    booking_id: int


# ---------- частые вопросы ----------


class FaqCb(CallbackData, prefix="faq"):
    index: int  # -1 — список вопросов


# ---------- администратор ----------


class AdminCb(CallbackData, prefix="adm"):
    action: str  # today | tomorrow | week | services | exit_demo


class AdminCancelCb(CallbackData, prefix="acnl"):
    booking_id: int


class SvcEditCb(CallbackData, prefix="sve"):
    service_id: str
    action: str  # open | price | duration | toggle


# ---------- reply-клавиатуры ----------


def main_menu(*, show_admin: bool = False) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text=BTN_BOOK)],
        [KeyboardButton(text=BTN_MY), KeyboardButton(text=BTN_PRICES)],
        [KeyboardButton(text=BTN_FAQ)],
    ]
    if show_admin:
        rows.append([KeyboardButton(text=BTN_ADMIN)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def phone_request() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Отправить мой номер", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


# ---------- инлайн: запись ----------


def services_kb(services: list[Service]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for s in services:
        kb.button(text=f"{s.name} · {fmt_price(s.price)}", callback_data=ServiceCb(service_id=s.id))
    kb.button(text="✖️ Отмена", callback_data=NavCb(to="abort"))
    kb.adjust(1)
    return kb.as_markup()


def masters_kb(service_id: str, masters: list[Master]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text="✨ Любой свободный мастер",
        callback_data=MasterCb(service_id=service_id, master_id=ANY_MASTER),
    )
    for m in masters:
        kb.button(text=m.name, callback_data=MasterCb(service_id=service_id, master_id=m.id))
    kb.adjust(1)
    kb.row(InlineKeyboardButton(text="⬅️ К услугам", callback_data=NavCb(to="services").pack()))
    return kb.as_markup()


def days_kb(
    service_id: str,
    master_id: str,
    days: list[date],
    *,
    back_to_masters: bool,
    calendar: bool = False,
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if calendar:
        kb.button(
            text="🗓 Открыть календарь на неделю",
            callback_data=CalendarCb(service_id=service_id, master_id=master_id),
        )
    for d in days:
        kb.button(
            text=fmt_day(d),
            callback_data=DayCb(service_id=service_id, master_id=master_id, day=d.strftime("%Y%m%d")),
        )
    kb.adjust(1, 2) if calendar else kb.adjust(2)
    if back_to_masters:
        back, text = NavCb(to="masters", service_id=service_id), "⬅️ К мастерам"
    else:
        back, text = NavCb(to="services"), "⬅️ К услугам"
    kb.row(InlineKeyboardButton(text=text, callback_data=back.pack()))
    return kb.as_markup()


def slots_kb(
    service_id: str, master_id: str, slots: list[datetime], tz: ZoneInfo
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for slot in slots:
        kb.button(
            text=slot.astimezone(tz).strftime("%H:%M"),
            callback_data=SlotCb(service_id=service_id, master_id=master_id, ts=int(slot.timestamp())),
        )
    kb.adjust(4)
    kb.row(
        InlineKeyboardButton(
            text="⬅️ К датам",
            callback_data=NavCb(to="days", service_id=service_id, master_id=master_id).pack(),
        )
    )
    return kb.as_markup()


def confirm_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Подтвердить", callback_data=ConfirmCb(yes=True))
    kb.button(text="✖️ Отменить", callback_data=ConfirmCb(yes=False))
    kb.adjust(2)
    return kb.as_markup()


# ---------- инлайн: мои записи и перенос ----------


def my_bookings_kb(bookings: list[Booking], tz: ZoneInfo) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for b in bookings:
        when = fmt_dt(b.starts_at, tz)
        kb.row(
            InlineKeyboardButton(text=f"🔁 Перенести {when}", callback_data=MoveCb(booking_id=b.id).pack())
        )
        kb.row(
            InlineKeyboardButton(text=f"❌ Отменить {when}", callback_data=CancelCb(booking_id=b.id).pack())
        )
    return kb.as_markup()


def move_days_kb(booking_id: int, days: list[date]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for d in days:
        kb.button(
            text=fmt_day(d), callback_data=MoveDayCb(booking_id=booking_id, day=d.strftime("%Y%m%d"))
        )
    kb.adjust(2)
    kb.row(
        InlineKeyboardButton(
            text="✖️ Не переносить", callback_data=MoveAbortCb(booking_id=booking_id).pack()
        )
    )
    return kb.as_markup()


def move_slots_kb(booking_id: int, slots: list[datetime], tz: ZoneInfo) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for slot in slots:
        kb.button(
            text=slot.astimezone(tz).strftime("%H:%M"),
            callback_data=MoveSlotCb(booking_id=booking_id, ts=int(slot.timestamp())),
        )
    kb.adjust(4)
    kb.row(InlineKeyboardButton(text="⬅️ К датам", callback_data=MoveCb(booking_id=booking_id).pack()))
    return kb.as_markup()


# ---------- инлайн: частые вопросы ----------


def faq_kb(items: list[FaqItem]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for i, item in enumerate(items):
        kb.button(text=item.question, callback_data=FaqCb(index=i))
    kb.adjust(1)
    return kb.as_markup()


def faq_back_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ Все вопросы", callback_data=FaqCb(index=-1))
    return kb.as_markup()


# ---------- инлайн: администратор ----------


def admin_panel_kb(*, demo: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📅 Сегодня", callback_data=AdminCb(action="today"))
    kb.button(text="📅 Завтра", callback_data=AdminCb(action="tomorrow"))
    kb.button(text="🗓 Неделя", callback_data=AdminCb(action="week"))
    kb.button(text="💰 Услуги и цены", callback_data=AdminCb(action="services"))
    if demo:
        kb.button(text="🚪 Выйти из демо-режима", callback_data=AdminCb(action="exit_demo"))
    kb.adjust(3, 1, 1)
    return kb.as_markup()


def admin_cancel_kb(booking_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="❌ Отменить запись", callback_data=AdminCancelCb(booking_id=booking_id))
    return kb.as_markup()


def admin_services_kb(services: list[Service]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for s in services:
        mark = "" if s.active else "🙈 "
        kb.button(
            text=f"{mark}{s.name} · {fmt_price(s.price)}",
            callback_data=SvcEditCb(service_id=s.id, action="open"),
        )
    kb.adjust(1)
    return kb.as_markup()


def admin_service_kb(service: Service) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="💰 Изменить цену", callback_data=SvcEditCb(service_id=service.id, action="price"))
    kb.button(
        text="⏱ Изменить длительность",
        callback_data=SvcEditCb(service_id=service.id, action="duration"),
    )
    kb.button(
        text="🙈 Скрыть от клиентов" if service.active else "👁 Показывать клиентам",
        callback_data=SvcEditCb(service_id=service.id, action="toggle"),
    )
    kb.button(text="⬅️ Все услуги", callback_data=AdminCb(action="services"))
    kb.adjust(1)
    return kb.as_markup()
