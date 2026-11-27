import tempfile
import unittest
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

from reminders import ReminderStore, parse_due_time


class ReminderStoreTests(unittest.TestCase):
    def test_create_and_get_due_reminder(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ReminderStore(Path(temp_dir) / "reminders.db")
            due_at = datetime.now(timezone.utc) + timedelta(minutes=1)
            reminder_id = store.create("Test reminder", due_at)
            with closing(sqlite3.connect(store.db_path)) as connection:
                connection.execute(
                    "UPDATE reminders SET due_at_utc = ? WHERE id = ?",
                    (
                        (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
                        reminder_id,
                    ),
                )
                connection.commit()
            due = store.get_due()

            self.assertEqual([row["id"] for row in due], [reminder_id])
            store.mark_triggered(reminder_id)
            self.assertEqual(store.get_due(), [])

    def test_create_rejects_past_reminder(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ReminderStore(Path(temp_dir) / "reminders.db")
            with self.assertRaises(ValueError):
                store.create(
                    "Past reminder",
                    datetime.now(timezone.utc) - timedelta(minutes=1),
                )

    def test_parse_due_time_accepts_zulu_time(self):
        parsed = parse_due_time("2030-01-01T12:30:00Z")
        self.assertEqual(parsed.tzinfo, timezone.utc)


if __name__ == "__main__":
    unittest.main()
