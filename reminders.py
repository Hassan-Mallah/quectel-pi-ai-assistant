import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_DB_PATH = Path.home() / ".quectel-pi-ai-assistant" / "reminders.db"


class ReminderStore:
    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self):
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    due_at_utc TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at_utc TEXT NOT NULL,
                    triggered_at_utc TEXT
                )
                """
            )

    def create(self, title: str, due_at: datetime) -> int:
        title = title.strip()
        if not title:
            raise ValueError("Reminder title cannot be empty")

        due_at_utc = due_at.astimezone(timezone.utc)
        now_utc = datetime.now(timezone.utc)
        if due_at_utc <= now_utc:
            raise ValueError("Reminder time must be in the future")

        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO reminders
                    (title, due_at_utc, status, created_at_utc)
                VALUES (?, ?, 'pending', ?)
                """,
                (title, due_at_utc.isoformat(), now_utc.isoformat()),
            )
            return int(cursor.lastrowid)

    def get_due(self) -> list[sqlite3.Row]:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, title
                FROM reminders
                WHERE status = 'pending' AND due_at_utc <= ?
                ORDER BY due_at_utc
                """,
                (now,),
            ).fetchall()
            return rows

    def mark_triggered(self, reminder_id: int):
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE reminders
                SET status = 'triggered', triggered_at_utc = ?
                WHERE id = ? AND status = 'pending'
                """,
                (datetime.now(timezone.utc).isoformat(), reminder_id),
            )


def parse_due_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return parsed.astimezone(timezone.utc)
