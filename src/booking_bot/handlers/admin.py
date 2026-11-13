"""Администратор: расписание, отмена записей, управление услугами и ценами.

Демо-режим: любой пользователь может включить его кнопкой «Как это видит администратор».
Тогда он попадает в эту же панель, но видит и отменяет только свои записи,
а изменения услуг в демо не сохраняются.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta

from aiogram import Bot, F, Router
from aiogram.filters import BaseFilter, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, TelegramObject

from booking_bot import keyboards as kb
from booking_bot import notify, texts
from booking_bot.config import Settings
from booking_bot.db import Database

MENU_BUTTONS = {texts.BTN_BOOK, texts.BTN_MY, texts.BTN_PRICES, texts.BTN_FAQ, texts.BTN_ADMIN}


class IsAdmin(BaseFilter):
    """Настоящий администратор или пользователь в демо-режиме."""

    async def __call__(self, event: TelegramObject, settings: Settings, db: Database) -> bool:
        user = getattr(event, "from_user", None)
        if user is None:
            return False
        return user.id in settings.admin_ids or (settings.demo_mode and db.is_demo(user.id))


router = Router(name="admin")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


class EditService(StatesGroup):
    value = State()


def is_demo_user(user_id: int, settings: Settings) -> bool:
    return user_id not in settings.admin_ids


def scope(user_id: int, settings: Settings) -> int | None:
    """None — видны все записи (администратор); иначе только записи этого пользователя (демо)."""
    return user_id if is_demo_user(user_id, settings) else None


# ---------- панель и расписание ----------


@router.message(Command("admin"))
async def admin_help(message: Message, state: FSMContext, settings: Settings) -> None:
    await state.clear()
    demo = is_demo_user(message.from_user.id, settings)
    await message.answer(
        texts.DEMO_INTRO if demo else texts.ADMIN_HELP, reply_markup=kb.admin_panel_kb(demo=demo)
    )


PERIODS = {
    "today": (0, 1, "Сегодня"),
    "tomorrow": (1, 1, "Завтра"),
    "week": (0, 7, "Ближайшие 7 дней"),
}


async def send_schedule(
    message: Message, user_id: int, db: Database, settings: Settings, period: str
) -> None:
    days_from, days, title = PERIODS[period]
    first_day = datetime.now(settings.tz).date() + timedelta(days=days_from)
    start = datetime.combine(first_day, time.min, tzinfo=settings.tz)
    bookings = db.between(start, start + timedelta(days=days), user_id=scope(user_id, settings))
    note = " (демо: только ваши записи)" if is_demo_user(user_id, settings) else ""
    if not bookings:
        await message.answer(f"{title}: записей нет{note}.")
        return
    await message.answer(f"<b>{title}</b>: {len(bookings)}{note}")
    for b in bookings:
        await message.answer(
            texts.booking_card(b, settings, for_admin=True), reply_markup=kb.admin_cancel_kb(b.id)
        )


@router.message(Command("today", "tomorrow", "week"))
async def schedule_command(message: Message, db: Database, settings: Settings) -> None:
    period = message.text.split()[0].lstrip("/").split("@")[0]
    await send_schedule(message, message.from_user.id, db, settings, period)


@router.callback_query(kb.AdminCb.filter())
async def on_admin_action(
    call: CallbackQuery,
    callback_data: kb.AdminCb,
    state: FSMContext,
    db: Database,
    settings: Settings,
) -> None:
    user_id = call.from_user.id
    action = callback_data.action
    if action in PERIODS:
        await call.answer()
        await send_schedule(call.message, user_id, db, settings, action)
    elif action == "services":
        await state.clear()
        await call.message.edit_text(
            "<b>Услуги и цены</b>\nВыберите услугу, чтобы изменить цену, длительность "
            "или скрыть её от клиентов:",
            reply_markup=kb.admin_services_kb(settings.catalog.services),
        )
        await call.answer()
    elif action == "exit_demo":
        await state.clear()
        db.set_demo(user_id, False)
        await call.message.edit_text("Демо-режим выключен. Вы снова видите бот как клиент.")
        await call.answer()
    else:
        await call.answer()


@router.callback_query(kb.AdminCancelCb.filter())
async def admin_cancel(
    call: CallbackQuery, callback_data: kb.AdminCancelCb, bot: Bot, db: Database, settings: Settings
) -> None:
    booking = db.cancel(callback_data.booking_id, user_id=scope(call.from_user.id, settings))
    if booking is None:
        await call.answer("Запись уже отменена", show_alert=True)
        return
    await call.message.edit_text(
        "❌ Отменено администратором\n\n" + texts.booking_card(booking, settings, for_admin=True)
    )
    await call.answer()
    await notify.to_user(
        bot,
        booking.user_id,
        "К сожалению, ваша запись отменена администратором:\n\n"
        + texts.booking_card(booking, settings, for_admin=False)
        + "\n\nВы можете выбрать другое время через «📅 Записаться».",
    )


# ---------- услуги и цены ----------


@router.callback_query(kb.SvcEditCb.filter())
async def on_service_edit(
    call: CallbackQuery, callback_data: kb.SvcEditCb, state: FSMContext, settings: Settings
) -> None:
    service = settings.service(callback_data.service_id)
    if service is None:
        await call.answer("Услуга не найдена", show_alert=True)
        return

    if callback_data.action == "toggle":
        if is_demo_user(call.from_user.id, settings):
            await call.answer(
                "Демо: в рабочем боте услуга сразу "
                + ("скрылась бы от клиентов." if service.active else "появилась бы в меню."),
                show_alert=True,
            )
            return
        service = settings.catalog.update_service(service.id, active=not service.active)
        await call.answer("Сохранено")
    elif callback_data.action in {"price", "duration"}:
        await state.set_state(EditService.value)
        await state.update_data(service_id=service.id, field=callback_data.action)
        what = "цену в рублях, например 2000" if callback_data.action == "price" else (
            "длительность в минутах, например 60"
        )
        await call.message.answer(f"«{texts.escape(service.name)}»: напишите новую {what}.")
        await call.answer()
        return
    else:
        await call.answer()

    await call.message.edit_text(
        texts.service_admin_card(service), reply_markup=kb.admin_service_kb(service)
    )


def parse_value(field: str, raw: str) -> int | str:
    """Возвращает число или текст ошибки."""
    cleaned = raw.lower().replace(" ", "").replace("₽", "").removesuffix("руб").removesuffix("мин")
    if not cleaned.isdigit():
        return "Нужно целое число, например 1500."
    value = int(cleaned)
    if field == "price" and not 0 <= value <= 1_000_000:
        return "Цена должна быть от 0 до 1 000 000 ₽."
    if field == "duration" and not (10 <= value <= 480 and value % 5 == 0):
        return "Длительность — от 10 до 480 минут, кратно 5."
    return value


@router.message(EditService.value, F.text, ~F.text.startswith("/"), ~F.text.in_(MENU_BUTTONS))
async def on_service_value(message: Message, state: FSMContext, settings: Settings) -> None:
    data = await state.get_data()
    service = settings.service(data.get("service_id", ""))
    field = data.get("field", "")
    if service is None or field not in {"price", "duration"}:
        await state.clear()
        await message.answer("Услуга не найдена. Откройте /admin заново.")
        return

    value = parse_value(field, message.text)
    if isinstance(value, str):
        await message.answer(value)
        return
    await state.clear()

    if is_demo_user(message.from_user.id, settings):
        shown = texts.fmt_price(value) if field == "price" else f"{value} мин"
        await message.answer(
            f"Демо: в рабочем боте у «{texts.escape(service.name)}» сразу стало бы {shown}, "
            "и клиенты увидели бы это в меню. В демо каталог не меняется, чтобы всем "
            "показывался одинаковый пример.",
            reply_markup=kb.admin_service_kb(service),
        )
        return

    key = "price" if field == "price" else "duration_min"
    updated = settings.catalog.update_service(service.id, **{key: value})
    await message.answer(
        "✅ Сохранено\n\n" + texts.service_admin_card(updated),
        reply_markup=kb.admin_service_kb(updated),
    )
