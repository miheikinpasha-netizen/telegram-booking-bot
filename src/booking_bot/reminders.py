"""Фоновая задача: напоминает клиентам о визите заранее."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from aiogram import Bot

from booking_bot import notify, texts
from booking_bot.config import Settings
from booking_bot.db import Database

log = logging.getLogger(__name__)

REMIND_BEFORE = timedelta(hours=2)
CHECK_EVERY_SEC = 60


async def send_due(bot: Bot, db: Database, settings: Settings) -> int:
    """Отправляет все созревшие напоминания. Возвращает их количество."""
    sent = 0
    for booking in db.due_reminders(datetime.now(settings.tz), REMIND_BEFORE):
        await notify.to_user(
            bot,
            booking.user_id,
            "⏰ Напоминаем о записи:\n\n"
            + texts.booking_card(booking, settings, for_admin=False)
            + "\n\nЕсли планы изменились, перенесите или отмените запись в разделе «Мои записи».",
        )
        # Помечаем даже при ошибке отправки (клиент заблокировал бота), чтобы не повторять каждую минуту.
        db.mark_reminded(booking.id)
        sent += 1
    return sent


async def reminder_loop(bot: Bot, db: Database, settings: Settings) -> None:
    while True:
        try:
            await send_due(bot, db, settings)
        except Exception:
            log.exception("Ошибка при отправке напоминаний")
        await asyncio.sleep(CHECK_EVERY_SEC)
