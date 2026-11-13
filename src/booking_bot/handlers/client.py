"""Сценарий клиента: запись (услуга → мастер → дата → время), мои записи, перенос, FAQ."""

from __future__ import annotations

import contextlib
import re
from datetime import datetime, timedelta

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from booking_bot import keyboards as kb
from booking_bot import notify, texts, widget
from booking_bot.config import Service, Settings
from booking_bot.db import Booking, Database
from booking_bot.slots import (
    ANY_MASTER, candidate_masters, days_with_slots, free_masters_at, slots_for,
)

router = Router(name="client")

PHONE_RE = re.compile(r"^\+?\d{10,15}$")
MENU_BUTTONS = {texts.BTN_BOOK, texts.BTN_MY, texts.BTN_PRICES, texts.BTN_FAQ, texts.BTN_ADMIN}


class BookingForm(StatesGroup):
    name = State()
    phone = State()
    confirm = State()


def now_local(settings: Settings) -> datetime:
    return datetime.now(settings.tz)


def menu_for(user_id: int, settings: Settings):
    return kb.main_menu(show_admin=settings.demo_mode or user_id in settings.admin_ids)


def bookable(settings: Settings, service_id: str) -> Service | None:
    """Услуга, на которую можно записаться сейчас (существует и не скрыта)."""
    service = settings.service(service_id)
    return service if service is not None and service.active else None


def parse_day(raw: str):
    try:
        return datetime.strptime(raw, "%Y%m%d").date()
    except ValueError:
        return None


def master_title(settings: Settings, master_id: str) -> str:
    if len(settings.catalog.masters) < 2:
        return ""
    if master_id == ANY_MASTER:
        return "\n💇 Любой свободный мастер"
    master = settings.catalog.master(master_id)
    return f"\n💇 Мастер: {texts.escape(master.name)}" if master else ""


# ---------- главное меню ----------


@router.message(CommandStart())
async def start(message: Message, state: FSMContext, settings: Settings) -> None:
    await state.clear()
    text = (
        f"Здравствуйте! Это бот онлайн-записи «{texts.escape(settings.business_name)}».\n"
        "Выберите действие в меню ниже."
    )
    if settings.demo_mode:
        text += (
            "\n\nЭто демонстрационный бот. Кнопка «👀 Как это видит администратор» "
            "покажет, как с ботом работает владелец салона."
        )
    await message.answer(text, reply_markup=menu_for(message.from_user.id, settings))


@router.message(F.text == texts.BTN_PRICES)
async def prices(message: Message, state: FSMContext, settings: Settings) -> None:
    await state.clear()
    await message.answer(
        texts.price_list(settings), reply_markup=menu_for(message.from_user.id, settings)
    )


@router.message(F.text == texts.BTN_BOOK)
async def book(message: Message, state: FSMContext, settings: Settings) -> None:
    await state.clear()
    await message.answer(
        "Выберите услугу:", reply_markup=kb.services_kb(settings.catalog.active_services())
    )


@router.message(F.text == texts.BTN_ADMIN)
async def admin_view(message: Message, state: FSMContext, db: Database, settings: Settings) -> None:
    await state.clear()
    user_id = message.from_user.id
    if user_id in settings.admin_ids:
        await message.answer(texts.ADMIN_HELP, reply_markup=kb.admin_panel_kb(demo=False))
    elif settings.demo_mode:
        db.set_demo(user_id, True)
        await message.answer(texts.DEMO_INTRO, reply_markup=kb.admin_panel_kb(demo=True))
    else:
        await message.answer("Этот раздел доступен только администратору.")


# ---------- частые вопросы ----------


@router.message(F.text == texts.BTN_FAQ)
async def faq(message: Message, state: FSMContext, settings: Settings) -> None:
    await state.clear()
    if not settings.catalog.faq:
        await message.answer("Раздел пока пуст. Напишите нам — ответим.")
        return
    await message.answer("Частые вопросы:", reply_markup=kb.faq_kb(settings.catalog.faq))


@router.callback_query(kb.FaqCb.filter())
async def on_faq(call: CallbackQuery, callback_data: kb.FaqCb, settings: Settings) -> None:
    items = settings.catalog.faq
    if 0 <= callback_data.index < len(items):
        item = items[callback_data.index]
        await call.message.edit_text(
            f"<b>{texts.escape(item.question)}</b>\n\n{texts.escape(item.answer)}",
            reply_markup=kb.faq_back_kb(),
        )
    else:
        await call.message.edit_text("Частые вопросы:", reply_markup=kb.faq_kb(items))
    await call.answer()


# ---------- услуга → мастер → дата → время ----------


async def show_services(call: CallbackQuery, settings: Settings, prefix: str = "") -> None:
    await call.message.edit_text(
        prefix + "Выберите услугу:", reply_markup=kb.services_kb(settings.catalog.active_services())
    )


def needs_master_choice(settings: Settings, service: Service) -> bool:
    return len(settings.catalog.masters_for(service.id)) > 1


async def show_masters(call: CallbackQuery, settings: Settings, service: Service) -> None:
    await call.message.edit_text(
        f"<b>{texts.escape(service.name)}</b>, {service.duration_min} мин.\nВыберите мастера:",
        reply_markup=kb.masters_kb(service.id, settings.catalog.masters_for(service.id)),
    )


async def show_days(
    call: CallbackQuery, db: Database, settings: Settings, service: Service, master_id: str
) -> None:
    days = days_with_slots(db, settings, service, master_id, now_local(settings))
    if not days:
        await show_services(
            call,
            settings,
            f"На «{texts.escape(service.name)}» в ближайшие дни свободного времени нет.\n",
        )
        return
    await call.message.edit_text(
        f"<b>{texts.escape(service.name)}</b>, {service.duration_min} мин."
        f"{master_title(settings, master_id)}\nВыберите дату:",
        reply_markup=kb.days_kb(
            service.id,
            master_id,
            days,
            back_to_masters=needs_master_choice(settings, service),
            calendar=calendar_enabled(call, settings, service, master_id),
        ),
    )


def calendar_enabled(call: CallbackQuery, settings: Settings, service: Service, master_id: str) -> bool:
    """Виджеты Telegram пока работают только в личных чатах."""
    chat = call.message.chat if call.message else None
    return (
        settings.widgets
        and not widget.blocked()
        and chat is not None
        and chat.type == "private"
        and widget.available(service, master_id)
    )


@router.callback_query(kb.CalendarCb.filter())
async def on_calendar(
    call: CallbackQuery, callback_data: kb.CalendarCb, bot: Bot, db: Database, settings: Settings
) -> None:
    service = bookable(settings, callback_data.service_id)
    if (
        service is None
        or not candidate_masters(settings, service, callback_data.master_id)
        or not calendar_enabled(call, settings, service, callback_data.master_id)
    ):
        await call.answer("Календарь недоступен, выберите дату кнопками", show_alert=True)
        return
    try:
        await widget.send_calendar(
            bot, call.message.chat.id, db, settings, service, callback_data.master_id
        )
    except TelegramAPIError:
        # Причина записана в лог (widget.send_calendar). Клиенту — обычные кнопки с датами,
        # без кнопки календаря, если Telegram его пока не разрешает.
        await call.answer("Календарь пока недоступен — выберите дату кнопками ниже")
        with contextlib.suppress(TelegramAPIError):  # «message is not modified» не страшно
            await show_days(call, db, settings, service, callback_data.master_id)
        return
    await call.answer()


async def after_service(
    call: CallbackQuery, db: Database, settings: Settings, service: Service
) -> None:
    masters = settings.catalog.masters_for(service.id)
    if len(masters) > 1:
        await show_masters(call, settings, service)
    elif masters:
        await show_days(call, db, settings, service, masters[0].id)
    else:
        await show_services(call, settings, "Эту услугу сейчас никто не выполняет.\n")


@router.callback_query(kb.ServiceCb.filter())
async def on_service(
    call: CallbackQuery, callback_data: kb.ServiceCb, db: Database, settings: Settings
) -> None:
    service = bookable(settings, callback_data.service_id)
    if service is None:
        await call.answer("Услуга больше недоступна", show_alert=True)
        return
    await after_service(call, db, settings, service)
    await call.answer()


@router.callback_query(kb.MasterCb.filter())
async def on_master(
    call: CallbackQuery, callback_data: kb.MasterCb, db: Database, settings: Settings
) -> None:
    service = bookable(settings, callback_data.service_id)
    if service is None or not candidate_masters(settings, service, callback_data.master_id):
        await call.answer("Выбор недоступен, начните заново", show_alert=True)
        return
    await show_days(call, db, settings, service, callback_data.master_id)
    await call.answer()


@router.callback_query(kb.NavCb.filter())
async def on_nav(
    call: CallbackQuery,
    callback_data: kb.NavCb,
    state: FSMContext,
    db: Database,
    settings: Settings,
) -> None:
    service = bookable(settings, callback_data.service_id)
    if callback_data.to == "abort":
        await state.clear()
        await call.message.edit_text("Запись отменена.")
    elif callback_data.to == "masters" and service is not None:
        await show_masters(call, settings, service)
    elif (
        callback_data.to == "days"
        and service is not None
        and candidate_masters(settings, service, callback_data.master_id)
    ):
        await show_days(call, db, settings, service, callback_data.master_id)
    else:
        await show_services(call, settings)
    await call.answer()


@router.callback_query(kb.DayCb.filter())
async def on_day(
    call: CallbackQuery, callback_data: kb.DayCb, db: Database, settings: Settings
) -> None:
    service = bookable(settings, callback_data.service_id)
    day = parse_day(callback_data.day)
    if service is None or day is None or not candidate_masters(settings, service, callback_data.master_id):
        await call.answer("Эта дата недоступна", show_alert=True)
        return

    slots = slots_for(db, settings, service, callback_data.master_id, day, now_local(settings))
    if not slots:
        await call.answer("На эту дату свободного времени нет", show_alert=True)
        await show_days(call, db, settings, service, callback_data.master_id)
        return
    await call.message.edit_text(
        f"<b>{texts.escape(service.name)}</b>, {texts.fmt_day(day)}"
        f"{master_title(settings, callback_data.master_id)}\nВыберите время:",
        reply_markup=kb.slots_kb(service.id, callback_data.master_id, slots, settings.tz),
    )
    await call.answer()


@router.callback_query(kb.SlotCb.filter())
async def on_slot(
    call: CallbackQuery,
    callback_data: kb.SlotCb,
    state: FSMContext,
    db: Database,
    settings: Settings,
) -> None:
    service = bookable(settings, callback_data.service_id)
    start_at = datetime.fromtimestamp(callback_data.ts, settings.tz)
    # Повторно проверяем на сервере: кнопка могла устареть или быть подделана.
    if service is None or not free_masters_at(
        db, settings, service, callback_data.master_id, start_at, now_local(settings)
    ):
        await call.answer("Это время уже недоступно, выберите другое", show_alert=True)
        return

    await state.set_state(BookingForm.name)
    await state.update_data(
        service_id=service.id, master_id=callback_data.master_id, ts=callback_data.ts
    )
    await call.message.edit_text(
        f"<b>{texts.escape(service.name)}</b>\n🕒 {texts.fmt_dt(start_at, settings.tz)}"
        f"{master_title(settings, callback_data.master_id)}"
    )
    await call.message.answer("Как к вам обращаться? Напишите имя.")
    await call.answer()


# ---------- контакты и подтверждение ----------


@router.message(BookingForm.name, F.text, ~F.text.in_(MENU_BUTTONS))
async def on_name(message: Message, state: FSMContext) -> None:
    name = " ".join(message.text.split())
    if not 2 <= len(name) <= 60:
        await message.answer("Имя должно быть от 2 до 60 символов. Попробуйте ещё раз.")
        return
    await state.update_data(name=name)
    await state.set_state(BookingForm.phone)
    await message.answer(
        "Оставьте номер телефона: нажмите кнопку ниже или напишите номер.",
        reply_markup=kb.phone_request(),
    )


@router.message(BookingForm.phone, F.contact | (F.text & ~F.text.in_(MENU_BUTTONS)))
async def on_phone(message: Message, state: FSMContext, settings: Settings) -> None:
    raw = message.contact.phone_number if message.contact else message.text
    phone = re.sub(r"[\s()\-]", "", raw or "")
    if not PHONE_RE.match(phone):
        await message.answer("Не похоже на номер телефона. Пример: +79991234567")
        return
    if not phone.startswith("+"):
        phone = "+" + phone

    data = await state.update_data(phone=phone)
    service = bookable(settings, data["service_id"])
    menu = menu_for(message.from_user.id, settings)
    if service is None:
        await state.clear()
        await message.answer("Услуга больше недоступна.", reply_markup=menu)
        return
    start_at = datetime.fromtimestamp(data["ts"], settings.tz)
    master = settings.catalog.master(data["master_id"])
    if len(settings.catalog.masters) < 2:
        master = None
    await state.set_state(BookingForm.confirm)
    await message.answer("Почти готово!", reply_markup=menu)
    await message.answer(
        texts.summary(service, master, start_at, data["name"], phone, settings.tz),
        reply_markup=kb.confirm_kb(),
    )


@router.callback_query(BookingForm.confirm, kb.ConfirmCb.filter())
async def on_confirm(
    call: CallbackQuery,
    callback_data: kb.ConfirmCb,
    state: FSMContext,
    bot: Bot,
    db: Database,
    settings: Settings,
) -> None:
    data = await state.get_data()
    await state.clear()
    if not callback_data.yes:
        await call.message.edit_text("Запись отменена.")
        await call.answer()
        return

    service = bookable(settings, data.get("service_id", ""))
    start_at = datetime.fromtimestamp(data.get("ts", 0), settings.tz)
    now = now_local(settings)
    if service is None or start_at <= now:
        await call.message.edit_text("Это время уже недоступно. Запишитесь заново.")
        await call.answer()
        return

    # Для «любого мастера» пробуем всех, у кого это время свободно; база всё равно
    # перепроверяет занятость в транзакции, так что одновременные нажатия безопасны.
    booking: Booking | None = None
    for master in free_masters_at(db, settings, service, data.get("master_id", ""), start_at, now):
        booking = db.create_booking(
            user_id=call.from_user.id,
            user_name=data["name"],
            phone=data["phone"],
            service_id=service.id,
            master_id=master.id,
            starts_at=start_at,
            ends_at=start_at + timedelta(minutes=service.duration_min),
        )
        if booking is not None:
            break

    if booking is None:
        await show_services(call, settings, "Увы, это время только что заняли.\n")
        await call.answer()
        return

    await call.message.edit_text(
        "✅ Вы записаны!\n\n"
        + texts.booking_card(booking, settings, for_admin=False)
        + "\n\nНапомним за 2 часа до визита. Перенести или отменить запись можно "
        "в разделе «Мои записи»."
    )
    await call.answer()
    await notify.booking_event(
        bot, db, settings, booking, "🆕 Новая запись", kb.admin_cancel_kb(booking.id)
    )


@router.callback_query(kb.ConfirmCb.filter())
async def on_stale_confirm(call: CallbackQuery) -> None:
    await call.answer("Эта запись уже обработана. Начните заново через меню.", show_alert=True)


# ---------- мои записи: отмена и перенос ----------


@router.message(F.text == texts.BTN_MY)
async def my_bookings(message: Message, state: FSMContext, db: Database, settings: Settings) -> None:
    await state.clear()
    user_id = message.from_user.id
    bookings = db.upcoming_for_user(user_id, now_local(settings))
    if not bookings:
        await message.answer("У вас нет предстоящих записей.", reply_markup=menu_for(user_id, settings))
        return
    cards = [texts.booking_card(b, settings, for_admin=False) for b in bookings]
    await message.answer(
        "Ваши записи:\n\n" + "\n\n".join(cards),
        reply_markup=kb.my_bookings_kb(bookings, settings.tz),
    )


@router.callback_query(kb.CancelCb.filter())
async def on_cancel(
    call: CallbackQuery, callback_data: kb.CancelCb, bot: Bot, db: Database, settings: Settings
) -> None:
    booking = db.cancel(callback_data.booking_id, user_id=call.from_user.id)
    if booking is None:
        await call.answer("Запись не найдена или уже отменена", show_alert=True)
        return
    await call.message.edit_text(
        "Запись отменена:\n\n" + texts.booking_card(booking, settings, for_admin=False)
    )
    await call.answer()
    await notify.booking_event(bot, db, settings, booking, "❌ Клиент отменил запись")


def own_future_booking(
    db: Database, settings: Settings, booking_id: int, user_id: int
) -> Booking | None:
    booking = db.get(booking_id)
    if (
        booking is None
        or booking.user_id != user_id
        or booking.status != "active"
        or booking.starts_at <= now_local(settings)
    ):
        return None
    return booking


@router.callback_query(kb.MoveCb.filter())
async def on_move(
    call: CallbackQuery, callback_data: kb.MoveCb, db: Database, settings: Settings
) -> None:
    booking = own_future_booking(db, settings, callback_data.booking_id, call.from_user.id)
    service = settings.service(booking.service_id) if booking else None
    if booking is None or service is None:
        await call.answer("Эту запись нельзя перенести", show_alert=True)
        return
    days = days_with_slots(
        db, settings, service, booking.master_id, now_local(settings), exclude_id=booking.id
    )
    card = texts.booking_card(booking, settings, for_admin=False)
    if not days:
        await call.message.edit_text(
            f"Перенос записи:\n\n{card}\n\nУ мастера нет другого свободного времени в ближайшие дни."
        )
        await call.answer()
        return
    await call.message.edit_text(
        f"Перенос записи:\n\n{card}\n\nВыберите новую дату:",
        reply_markup=kb.move_days_kb(booking.id, days),
    )
    await call.answer()


@router.callback_query(kb.MoveDayCb.filter())
async def on_move_day(
    call: CallbackQuery, callback_data: kb.MoveDayCb, db: Database, settings: Settings
) -> None:
    booking = own_future_booking(db, settings, callback_data.booking_id, call.from_user.id)
    service = settings.service(booking.service_id) if booking else None
    day = parse_day(callback_data.day)
    if booking is None or service is None or day is None:
        await call.answer("Эту запись нельзя перенести", show_alert=True)
        return
    slots = slots_for(
        db, settings, service, booking.master_id, day, now_local(settings), exclude_id=booking.id
    )
    if not slots:
        await call.answer("На эту дату свободного времени нет", show_alert=True)
        return
    await call.message.edit_text(
        f"Перенос: <b>{texts.escape(service.name)}</b>, {texts.fmt_day(day)}\nВыберите время:",
        reply_markup=kb.move_slots_kb(booking.id, slots, settings.tz),
    )
    await call.answer()


@router.callback_query(kb.MoveSlotCb.filter())
async def on_move_slot(
    call: CallbackQuery,
    callback_data: kb.MoveSlotCb,
    bot: Bot,
    db: Database,
    settings: Settings,
) -> None:
    booking = own_future_booking(db, settings, callback_data.booking_id, call.from_user.id)
    service = settings.service(booking.service_id) if booking else None
    new_start = datetime.fromtimestamp(callback_data.ts, settings.tz)
    allowed = (
        slots_for(
            db, settings, service, booking.master_id, new_start.date(), now_local(settings),
            exclude_id=booking.id,
        )
        if booking and service
        else []
    )
    if new_start not in allowed:
        await call.answer("Это время уже недоступно, выберите другое", show_alert=True)
        return

    old_when = texts.fmt_dt(booking.starts_at, settings.tz)
    moved = db.reschedule(
        booking.id,
        starts_at=new_start,
        ends_at=new_start + timedelta(minutes=service.duration_min),
        user_id=call.from_user.id,
    )
    if moved is None:
        await call.answer("Это время только что заняли, выберите другое", show_alert=True)
        return
    await call.message.edit_text(
        "✅ Запись перенесена:\n\n" + texts.booking_card(moved, settings, for_admin=False)
    )
    await call.answer()
    await notify.booking_event(
        bot, db, settings, moved, f"🔁 Клиент перенёс запись (было: {old_when})",
        kb.admin_cancel_kb(moved.id),
    )


@router.callback_query(kb.MoveAbortCb.filter())
async def on_move_abort(call: CallbackQuery) -> None:
    await call.message.edit_text("Перенос отменён, запись осталась без изменений.")
    await call.answer()
