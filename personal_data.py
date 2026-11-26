import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from reminders import DEFAULT_DB_PATH


class TodoNotesStore:
    def __init__(self, db_path=DEFAULT_DB_PATH):
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
                CREATE TABLE IF NOT EXISTS todos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at_utc TEXT NOT NULL,
                    completed_at_utc TEXT
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL
                )
                """
            )

    @staticmethod
    def _required_text(value: str, field: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError(f"{field} cannot be empty")
        return text

    def add_todo(self, title: str) -> int:
        title = self._required_text(title, "To-do")
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO todos (title, created_at_utc) VALUES (?, ?)",
                (title, datetime.now(timezone.utc).isoformat()),
            )
            return int(cursor.lastrowid)

    def list_todos(self, status: str = "pending") -> list[dict]:
        if status not in {"pending", "completed", "all"}:
            raise ValueError("To-do status must be pending, completed, or all")
        query = "SELECT id, title, status FROM todos"
        parameters = ()
        if status != "all":
            query += " WHERE status = ?"
            parameters = (status,)
        query += " ORDER BY id"
        with self._connect() as connection:
            return [
                dict(row)
                for row in connection.execute(query, parameters).fetchall()
            ]

    def complete_todo(self, todo_id: int) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE todos
                SET status = 'completed', completed_at_utc = ?
                WHERE id = ? AND status = 'pending'
                """,
                (datetime.now(timezone.utc).isoformat(), todo_id),
            )
            return cursor.rowcount > 0

    def add_note(self, title: str, content: str) -> int:
        title = self._required_text(title, "Note title")
        content = self._required_text(content, "Note content")
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO notes (title, content, created_at_utc)
                VALUES (?, ?, ?)
                """,
                (title, content, datetime.now(timezone.utc).isoformat()),
            )
            return int(cursor.lastrowid)

    def list_notes(self, limit: int = 10) -> list[dict]:
        if not 1 <= limit <= 50:
            raise ValueError("Note list limit must be between 1 and 50")
        with self._connect() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT id, title, content, created_at_utc
                    FROM notes
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            ]

    def search_notes(self, query: str) -> list[dict]:
        query = self._required_text(query, "Search query")
        with self._connect() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT id, title, content, created_at_utc
                    FROM notes
                    WHERE instr(lower(title), lower(?)) > 0
                       OR instr(lower(content), lower(?)) > 0
                    ORDER BY id DESC
                    LIMIT 10
                    """,
                    (query, query),
                ).fetchall()
            ]
