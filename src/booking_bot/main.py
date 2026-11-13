"""Точка входа: настраивает и запускает бота."""

from __future__ import annotations

import asyncio
import contextlib
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TEST
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from booking_bot.config import Settings, load_settings
from booking_bot.db import Database
from booking_bot.handlers import admin, client
from booking_bot.reminders import reminder_loop
from booking_bot.widget import UPDATE_TYPE, WidgetQueryMiddleware

log = logging.getLogger(__name__)


async def setup_profile(bot: Bot, settings: Settings) -> None:
    """Меню команд и описание бота (то, что клиент видит до нажатия «Start»)."""
    try:
        await bot.set_my_commands(
            [
                BotCommand(command="start", description="Главное меню"),
                BotCommand(command="admin", description="Панель администратора"),
            ]
        )
        description = settings.catalog.description
        if description:
            await bot.set_my_description(description[:512])
            await bot.set_my_short_description(description[:120])
    except TelegramAPIError:
        # Описание не критично: бот должен запуститься, даже если Telegram отказал.
        log.warning("Не удалось обновить описание бота", exc_info=True)


async def run() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = load_settings()
    db = Database(settings.db_path, default_master=settings.catalog.masters[0].id)
    session = AiohttpSession(api=TEST) if settings.test_server else None
    bot = Bot(
        settings.bot_token,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    if settings.test_server:
        log.info("Работаю в тестовой среде Telegram")
    dp = Dispatcher(storage=MemoryStorage(), settings=settings, db=db)
    dp.include_router(admin.router)
    dp.include_router(client.router)

    allowed_updates = dp.resolve_used_update_types()
    if settings.widgets:
        # aiogram пока не знает про виджеты: нажатия в календаре ловим сами.
        dp.update.outer_middleware(WidgetQueryMiddleware(dp.storage))
        allowed_updates.append(UPDATE_TYPE)

    await setup_profile(bot, settings)
    reminders = asyncio.create_task(reminder_loop(bot, db, settings))
    try:
        await dp.start_polling(bot, allowed_updates=allowed_updates)
    finally:
        reminders.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await reminders
        await bot.session.close()
        db.close()


def main() -> None:
    asyncio.run(run())
