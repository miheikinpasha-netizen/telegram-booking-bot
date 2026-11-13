"""Отправка уведомлений администраторам и клиентам."""

from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardMarkup

from booking_bot import texts
from booking_bot.config import Settings
from booking_bot.db import Booking, Database

log = logging.getLogger(__name__)


async def to_admins(
    bot: Bot, settings: Settings, text: str, markup: InlineKeyboardMarkup | None = None
) -> None:
    for admin_id in settings.admin_ids:
        try:
            await bot.send_message(admin_id, text, reply_markup=markup)
        except TelegramAPIError:
            # Администратор не запускал бота или заблокировал его: не роняем сценарий клиента.
            log.warning("Не удалось отправить уведомление администратору %s", admin_id)


async def to_user(
    bot: Bot, user_id: int, text: str, markup: InlineKeyboardMarkup | None = None
) -> bool:
    try:
        await bot.send_message(user_id, text, reply_markup=markup)
        return True
    except TelegramAPIError:
        log.warning("Не удалось отправить сообщение клиенту %s", user_id)
        return False


async def booking_event(
    bot: Bot,
    db: Database,
    settings: Settings,
    booking: Booking,
    title: str,
    markup: InlineKeyboardMarkup | None = None,
) -> None:
    """Уведомляет администраторов о записи / переносе / отмене.

    Если клиент включил демо-режим, он тоже получает это уведомление —
    так он видит, как бот работает для владельца салона.
    """
    text = f"{title}\n\n" + texts.booking_card(booking, settings, for_admin=True)
    await to_admins(bot, settings, text, markup)
    if booking.user_id not in settings.admin_ids and db.is_demo(booking.user_id):
        await to_user(bot, booking.user_id, texts.DEMO_NOTE + text, markup)
