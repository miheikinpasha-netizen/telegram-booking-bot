"""Настройки бота: читаются из .env и services.json.

Каталог (услуги, мастера, частые вопросы) администратор может менять прямо из Telegram:
изменения цен, длительности и видимости услуг сохраняются обратно в services.json.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, field, replace
from datetime import time
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Service:
    id: str
    name: str
    duration_min: int
    price: int
    active: bool = True


@dataclass(frozen=True)
class WorkHours:
    start: time
    end: time
    slot_step_min: int
    days_ahead: int
    weekdays: frozenset[int]  # 0 = понедельник


@dataclass(frozen=True)
class Master:
    id: str
    name: str
    service_ids: frozenset[str]
    hours: WorkHours

    def does(self, service_id: str) -> bool:
        return service_id in self.service_ids


@dataclass(frozen=True)
class FaqItem:
    question: str
    answer: str


def _parse_time(value: str) -> time:
    hours, minutes = value.split(":")
    return time(int(hours), int(minutes))


def _parse_hours(raw: dict, base: WorkHours | None = None) -> WorkHours:
    """Рабочие часы. Для мастера недостающие поля берутся из общего графика (base)."""
    hours = WorkHours(
        start=_parse_time(raw["start"]) if "start" in raw else base.start,
        end=_parse_time(raw["end"]) if "end" in raw else base.end,
        slot_step_min=int(raw.get("slot_step_min", base.slot_step_min if base else 30)),
        days_ahead=int(raw.get("days_ahead", base.days_ahead if base else 7)),
        weekdays=frozenset(int(d) for d in raw["weekdays"])
        if "weekdays" in raw
        else (base.weekdays if base else frozenset(range(7))),
    )
    if hours.start >= hours.end:
        raise ValueError("Начало рабочего дня должно быть раньше окончания")
    return hours


@dataclass
class Catalog:
    """Услуги, мастера и частые вопросы."""

    business_name: str
    description: str
    hours: WorkHours
    services: list[Service]
    masters: list[Master]
    faq: list[FaqItem]
    path: Path | None = None
    _raw: dict = field(default_factory=dict, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def service(self, service_id: str) -> Service | None:
        return next((s for s in self.services if s.id == service_id), None)

    def active_services(self) -> list[Service]:
        return [s for s in self.services if s.active]

    def master(self, master_id: str) -> Master | None:
        return next((m for m in self.masters if m.id == master_id), None)

    def masters_for(self, service_id: str) -> list[Master]:
        return [m for m in self.masters if m.does(service_id)]

    def update_service(self, service_id: str, **changes) -> Service:
        """Меняет price / duration_min / active и сохраняет services.json."""
        allowed = {"price", "duration_min", "active"}
        if not changes.keys() <= allowed:
            raise ValueError(f"Можно менять только {sorted(allowed)}")
        with self._lock:
            index = next((i for i, s in enumerate(self.services) if s.id == service_id), None)
            if index is None:
                raise KeyError(service_id)
            updated = replace(self.services[index], **changes)
            self.services[index] = updated
            for item in self._raw.get("services", []):
                if str(item.get("id")) == service_id:
                    item.update(changes)
            self._save()
        return updated

    def _save(self) -> None:
        if self.path is None:
            return
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(self.path)  # атомарная замена: файл не окажется недописанным


def parse_catalog(data: dict, path: Path | None = None) -> Catalog:
    services = [
        Service(
            id=str(item["id"]),
            name=str(item["name"]),
            duration_min=int(item["duration_min"]),
            price=int(item["price"]),
            active=bool(item.get("active", True)),
        )
        for item in data["services"]
    ]
    if not services:
        raise ValueError("В services.json нет ни одной услуги")
    if len({s.id for s in services}) != len(services):
        raise ValueError("В services.json повторяются id услуг")
    service_ids = {s.id for s in services}

    hours = _parse_hours(data["work_hours"])

    # Если мастера не описаны, считаем, что работает один мастер по общему графику.
    raw_masters = data.get("masters") or [{"id": "main", "name": "Мастер"}]
    masters = []
    for item in raw_masters:
        ids = frozenset(str(x) for x in item.get("services", service_ids))
        unknown = ids - service_ids
        if unknown:
            raise ValueError(f"У мастера {item['id']} неизвестные услуги: {', '.join(sorted(unknown))}")
        masters.append(
            Master(
                id=str(item["id"]),
                name=str(item["name"]),
                service_ids=ids,
                hours=_parse_hours(item, base=hours),
            )
        )
    if len({m.id for m in masters}) != len(masters):
        raise ValueError("В services.json повторяются id мастеров")

    return Catalog(
        business_name=str(data.get("business_name", "Запись онлайн")),
        description=str(data.get("description", "")),
        hours=hours,
        services=services,
        masters=masters,
        faq=[FaqItem(str(i["q"]), str(i["a"])) for i in data.get("faq", [])],
        path=path,
        _raw=data,
    )


def load_catalog(path: Path) -> Catalog:
    return parse_catalog(json.loads(path.read_text(encoding="utf-8")), path)


@dataclass(frozen=True)
class Settings:
    bot_token: str
    admin_ids: frozenset[int]
    tz: ZoneInfo
    db_path: Path
    catalog: Catalog
    demo_mode: bool = False
    widgets: bool = False  # календарь-виджет в чате (Telegram Bot API 10.4)
    test_server: bool = False  # тестовая среда Telegram (отдельные аккаунты и боты)

    @property
    def business_name(self) -> str:
        return self.catalog.business_name

    @property
    def hours(self) -> WorkHours:
        return self.catalog.hours

    def service(self, service_id: str) -> Service | None:
        return self.catalog.service(service_id)


def load_settings() -> Settings:
    # ENV_FILE позволяет запустить второй экземпляр, например тестового бота: ENV_FILE=.env.test
    env_file = os.getenv("ENV_FILE", ".env")
    load_dotenv(PROJECT_ROOT / env_file)

    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError(f"Не задан BOT_TOKEN в {env_file}. Впишите токен от @BotFather.")

    admin_ids = frozenset(
        int(part) for part in os.getenv("ADMIN_IDS", "").replace(" ", "").split(",") if part
    )
    if not admin_ids and not _flag("DEMO_MODE"):
        # Без администратора можно работать только в демо: там сторону владельца видит любой.
        raise RuntimeError("Не задан ADMIN_IDS: укажите Telegram ID администратора.")

    return Settings(
        bot_token=token,
        admin_ids=admin_ids,
        tz=ZoneInfo(os.getenv("TIMEZONE", "Europe/Moscow")),
        db_path=PROJECT_ROOT / os.getenv("DB_PATH", "bookings.sqlite3"),
        catalog=load_catalog(PROJECT_ROOT / os.getenv("SERVICES_FILE", "services.json")),
        demo_mode=_flag("DEMO_MODE"),
        widgets=_flag("WIDGETS"),
        test_server=_flag("TEST_SERVER"),
    )


def _flag(name: str) -> bool:
    return os.getenv(name, "0").strip().lower() in {"1", "true", "yes"}
