"""Хранение записей в SQLite.

Время хранится в UTC в формате ISO 8601, поэтому строки можно сравнивать прямо в SQL.
Занятость считается по мастеру: у разных мастеров одно и то же время свободно независимо.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS bookings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    user_name   TEXT    NOT NULL,
    phone       TEXT    NOT NULL,
    service_id  TEXT    NOT NULL,
    starts_at   TEXT    NOT NULL,
    ends_at     TEXT    NOT NULL,
    status      TEXT    NOT NULL DEFAULT 'active',
    reminded    INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_bookings_time ON bookings (status, starts_at);
CREATE INDEX IF NOT EXISTS idx_bookings_user ON bookings (user_id, status);
CREATE TABLE IF NOT EXISTS demo_users (
    user_id     INTEGER PRIMARY KEY
);
"""


def _to_db(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("Нужна дата с часовым поясом")
    return value.astimezone(UTC).isoformat(timespec="seconds")


def _from_db(value: str) -> datetime:
    return datetime.fromisoformat(value)


@dataclass(frozen=True)
class Booking:
    id: int
    user_id: int
    user_name: str
    phone: str
    service_id: str
    master_id: str
    starts_at: datetime
    ends_at: datetime
    status: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Booking:
        return cls(
            id=row["id"],
            user_id=row["user_id"],
            user_name=row["user_name"],
            phone=row["phone"],
            service_id=row["service_id"],
            master_id=row["master_id"],
            starts_at=_from_db(row["starts_at"]),
            ends_at=_from_db(row["ends_at"]),
            status=row["status"],
        )


class Database:
    def __init__(self, path: Path | str, *, default_master: str = "main") -> None:
        # isolation_level=None: транзакциями управляем сами (BEGIN IMMEDIATE).
        self._conn = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._migrate(default_master)

    def _migrate(self, default_master: str) -> None:
        """Старые базы без мастеров: добавляем колонку, прежние записи — к мастеру по умолчанию."""
        columns = {r["name"] for r in self._conn.execute("PRAGMA table_info(bookings)")}
        if "master_id" not in columns:
            self._conn.execute("ALTER TABLE bookings ADD COLUMN master_id TEXT NOT NULL DEFAULT ''")
            self._conn.execute("UPDATE bookings SET master_id = ?", (default_master,))
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_bookings_master ON bookings (master_id, status, starts_at)"
        )

    def close(self) -> None:
        self._conn.close()

    # ---------- занятость ----------

    def busy_intervals(
        self, master_id: str, start: datetime, end: datetime, *, exclude_id: int | None = None
    ) -> list[tuple[datetime, datetime]]:
        """Активные записи мастера, пересекающиеся с [start, end)."""
        rows = self._conn.execute(
            "SELECT starts_at, ends_at FROM bookings "
            "WHERE status = 'active' AND master_id = ? AND starts_at < ? AND ends_at > ? AND id != ?",
            (master_id, _to_db(end), _to_db(start), exclude_id or -1),
        ).fetchall()
        return [(_from_db(r["starts_at"]), _from_db(r["ends_at"])) for r in rows]

    def _has_conflict(
        self, master_id: str, starts_at: datetime, ends_at: datetime, exclude_id: int | None = None
    ) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM bookings WHERE status = 'active' AND master_id = ? "
            "AND starts_at < ? AND ends_at > ? AND id != ?",
            (master_id, _to_db(ends_at), _to_db(starts_at), exclude_id or -1),
        ).fetchone()
        return row is not None

    # ---------- создание и изменение ----------

    def create_booking(
        self,
        *,
        user_id: int,
        user_name: str,
        phone: str,
        service_id: str,
        master_id: str,
        starts_at: datetime,
        ends_at: datetime,
    ) -> Booking | None:
        """Создаёт запись. Возвращает None, если у мастера это время уже занято."""
        conn = self._conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            if self._has_conflict(master_id, starts_at, ends_at):
                conn.execute("ROLLBACK")
                return None
            cursor = conn.execute(
                "INSERT INTO bookings "
                "(user_id, user_name, phone, service_id, master_id, starts_at, ends_at, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    user_id, user_name, phone, service_id, master_id,
                    _to_db(starts_at), _to_db(ends_at), _to_db(datetime.now(UTC)),
                ),
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        return self.get(cursor.lastrowid)

    def reschedule(
        self,
        booking_id: int,
        *,
        starts_at: datetime,
        ends_at: datetime,
        user_id: int | None = None,
    ) -> Booking | None:
        """Переносит активную запись на новое время у того же мастера.

        Возвращает None, если запись не найдена, чужая или новое время занято.
        После переноса напоминание придёт заново.
        """
        conn = self._conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            current = self.get(booking_id)
            if (
                current is None
                or current.status != "active"
                or (user_id is not None and current.user_id != user_id)
                or self._has_conflict(current.master_id, starts_at, ends_at, exclude_id=booking_id)
            ):
                conn.execute("ROLLBACK")
                return None
            conn.execute(
                "UPDATE bookings SET starts_at = ?, ends_at = ?, reminded = 0 WHERE id = ?",
                (_to_db(starts_at), _to_db(ends_at), booking_id),
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        return self.get(booking_id)

    def cancel(self, booking_id: int, *, user_id: int | None = None) -> Booking | None:
        """Отменяет активную запись. Если передан user_id, отменить можно только свою."""
        query = "UPDATE bookings SET status = 'cancelled' WHERE id = ? AND status = 'active'"
        params: tuple = (booking_id,)
        if user_id is not None:
            query += " AND user_id = ?"
            params = (booking_id, user_id)
        cursor = self._conn.execute(query, params)
        if cursor.rowcount == 0:
            return None
        return self.get(booking_id)

    # ---------- выборки ----------

    def get(self, booking_id: int) -> Booking | None:
        row = self._conn.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)).fetchone()
        return Booking.from_row(row) if row else None

    def upcoming_for_user(self, user_id: int, now: datetime) -> list[Booking]:
        rows = self._conn.execute(
            "SELECT * FROM bookings WHERE user_id = ? AND status = 'active' AND starts_at > ? "
            "ORDER BY starts_at",
            (user_id, _to_db(now)),
        ).fetchall()
        return [Booking.from_row(r) for r in rows]

    def between(self, start: datetime, end: datetime, *, user_id: int | None = None) -> list[Booking]:
        """Активные записи в периоде. user_id — только записи этого клиента (демо-режим)."""
        query = "SELECT * FROM bookings WHERE status = 'active' AND starts_at >= ? AND starts_at < ?"
        params: list = [_to_db(start), _to_db(end)]
        if user_id is not None:
            query += " AND user_id = ?"
            params.append(user_id)
        rows = self._conn.execute(query + " ORDER BY starts_at", params).fetchall()
        return [Booking.from_row(r) for r in rows]

    def due_reminders(self, now: datetime, ahead: timedelta) -> list[Booking]:
        """Активные записи, которые начнутся в ближайшие `ahead` и о которых ещё не напомнили."""
        rows = self._conn.execute(
            "SELECT * FROM bookings WHERE status = 'active' AND reminded = 0 "
            "AND starts_at > ? AND starts_at <= ? ORDER BY starts_at",
            (_to_db(now), _to_db(now + ahead)),
        ).fetchall()
        return [Booking.from_row(r) for r in rows]

    def mark_reminded(self, booking_id: int) -> None:
        self._conn.execute("UPDATE bookings SET reminded = 1 WHERE id = ?", (booking_id,))

    # ---------- демо-режим ----------

    def set_demo(self, user_id: int, enabled: bool) -> None:
        if enabled:
            self._conn.execute("INSERT OR IGNORE INTO demo_users (user_id) VALUES (?)", (user_id,))
        else:
            self._conn.execute("DELETE FROM demo_users WHERE user_id = ?", (user_id,))

    def is_demo(self, user_id: int) -> bool:
        row = self._conn.execute("SELECT 1 FROM demo_users WHERE user_id = ?", (user_id,)).fetchone()
        return row is not None
