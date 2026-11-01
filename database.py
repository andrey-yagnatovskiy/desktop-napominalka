"""Хранение напоминаний в SQLite. Все даты — местное время Windows."""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path


WAITING = "Ожидает"
DONE = "Готово"
OVERDUE = "Просрочено"
CANCELLED = "Отменено"
STATUSES = (WAITING, DONE, OVERDUE, CANCELLED)


def timestamp(value: datetime) -> str:
    return value.isoformat(sep=" ", timespec="seconds")


class ReminderDatabase:
    def __init__(self, path=None):
        self.path = Path(path) if path is not None else Path(__file__).with_name("reminders.db")
        self.connection = sqlite3.connect(self.path, timeout=5)
        self.connection.row_factory = sqlite3.Row
        try:
            self.initdatabase()
        except sqlite3.Error:
            self.connection.close()
            raise

    def initdatabase(self):
        with self.connection:
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL CHECK (length(trim(title)) > 0),
                    description TEXT NOT NULL DEFAULT '',
                    due_at TEXT NOT NULL,
                    created_at TEXT,
                    status TEXT NOT NULL DEFAULT 'Ожидает'
                        CHECK (status IN ('Ожидает', 'Готово', 'Просрочено', 'Отменено'))
                )
                """
            )
            columns = {row["name"] for row in self.connection.execute("PRAGMA table_info(reminders)")}
            if "created_at" not in columns:
                self.connection.execute("ALTER TABLE reminders ADD COLUMN created_at TEXT")
            self.connection.execute(
                "CREATE INDEX IF NOT EXISTS reminders_status_due ON reminders(status, due_at)"
            )

    def add_reminder(self, title: str, description: str, due_at: datetime) -> int:
        title = title.strip()
        if not title:
            raise ValueError("Укажите заголовок напоминания.")
        with self.connection:
            cursor = self.connection.execute(
                "INSERT INTO reminders(title, description, due_at, created_at) VALUES (?, ?, ?, ?)",
                (title, description.strip(), timestamp(due_at), timestamp(datetime.now())),
            )
        return cursor.lastrowid

    def get_all_reminders(self, status=None):
        return self.sort_by_due_time(status)

    def sort_by_due_time(self, status=None):
        if status is None:
            return self.connection.execute(
                "SELECT * FROM reminders ORDER BY due_at, id"
            ).fetchall()
        if status not in STATUSES:
            raise ValueError("Неизвестный статус напоминания.")
        return self.connection.execute(
            "SELECT * FROM reminders WHERE status = ? ORDER BY due_at, id", (status,)
        ).fetchall()

    def get_reminder_by_id(self, reminder_id: int):
        return self.connection.execute(
            "SELECT * FROM reminders WHERE id = ?", (reminder_id,)
        ).fetchone()

    def update_status(self, reminder_id: int, status: str):
        if status not in STATUSES:
            raise ValueError("Неизвестный статус напоминания.")
        with self.connection:
            self.connection.execute(
                "UPDATE reminders SET status = ? WHERE id = ?", (status, reminder_id)
            )

    def delete_reminder(self, reminder_id: int):
        with self.connection:
            self.connection.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))

    def get_due_reminders(self, now=None):
        now = datetime.now() if now is None else now
        return self.connection.execute(
            "SELECT * FROM reminders WHERE status = ? AND due_at <= ? ORDER BY due_at, id",
            (WAITING, timestamp(now)),
        ).fetchall()

    def mark_overdue(self, now=None):
        """Отметить ожидающие записи, срок которых прошёл не менее минуты назад."""
        now = datetime.now() if now is None else now
        with self.connection:
            self.connection.execute(
                "UPDATE reminders SET status = ? WHERE status = ? AND due_at <= ?",
                (OVERDUE, WAITING, timestamp(now - timedelta(minutes=1))),
            )

    def get_reminders_count(self):
        return self.connection.execute("SELECT COUNT(*) FROM reminders").fetchone()[0]

    def close(self):
        self.connection.close()
