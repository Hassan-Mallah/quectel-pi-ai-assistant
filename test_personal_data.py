import tempfile
import unittest
from pathlib import Path

from personal_data import TodoNotesStore


class TodoNotesStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = TodoNotesStore(Path(self.temp_dir.name) / "assistant.db")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_todo_can_be_added_listed_and_completed(self):
        todo_id = self.store.add_todo("Buy tea")

        self.assertEqual(self.store.list_todos()[0]["title"], "Buy tea")
        self.assertTrue(self.store.complete_todo(todo_id))
        self.assertEqual(self.store.list_todos(), [])
        self.assertEqual(self.store.list_todos("completed")[0]["id"], todo_id)
        self.assertFalse(self.store.complete_todo(todo_id))

    def test_notes_can_be_saved_listed_and_searched(self):
        note_id = self.store.add_note("Router", "The admin address is 192.0.2.1")

        self.assertEqual(self.store.list_notes()[0]["id"], note_id)
        matches = self.store.search_notes("ADMIN ADDRESS")
        self.assertEqual([note["id"] for note in matches], [note_id])
        self.assertEqual(self.store.search_notes("not present"), [])

    def test_empty_note_content_is_rejected(self):
        with self.assertRaises(ValueError):
            self.store.add_note("Empty", "  ")


if __name__ == "__main__":
    unittest.main()
