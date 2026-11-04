from pathlib import Path
import tempfile
import unittest
from sqlalchemy import text
from petlink.database import Database


def create(title="Study session"):
    return dict(kind="create", values=dict(title=title, description="Plan focused work",
        priority="normal", status="pending", due_date="2026-11-05"))


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = Path(self.folder.name) / "petlink.sqlite3"
        self.db = Database(self.path)

    def tearDown(self):
        self.db.close()
        self.folder.cleanup()

    def test_drafts_survive_restart_without_creating_tasks(self):
        pending = self.db.propose([create()])
        self.db.close()
        self.db = Database(self.path)
        self.assertEqual(self.db.pending()[0]["id"], pending)
        self.assertEqual(self.db.tasks(), [])
        self.db.confirm(pending, 1)
        self.assertEqual(len(self.db.tasks()), 1)
        with self.db.engine.connect() as conn:
            self.assertEqual(conn.execute(text("SELECT version_num FROM alembic_version")).scalar(), "003")

    def test_revision_invalidates_old_confirmation_and_prevents_duplicates(self):
        pending = self.db.propose([create("Five questions")])
        self.db.revise(pending, 1, [create("Three questions")])
        with self.assertRaises(ValueError):
            self.db.confirm(pending, 1)
        self.assertEqual(self.db.tasks(), [])
        self.db.confirm(pending, 2)
        self.assertEqual(self.db.tasks()[0]["title"], "Three questions")
        with self.assertRaises(ValueError):
            self.db.confirm(pending, 2)

    def test_multi_action_failure_rolls_back_tasks_and_audit(self):
        pending = self.db.propose([create(), dict(kind="delete", task_id=999, version=1)])
        with self.assertRaises(ValueError):
            self.db.confirm(pending, 1)
        self.assertEqual(self.db.tasks(), [])
        self.assertEqual(len(self.db.pending()), 1)
        with self.db.engine.connect() as conn:
            self.assertEqual(conn.execute(text("SELECT COUNT(*) FROM audit_events")).scalar(), 0)

    def test_edit_remove_and_stale_version(self):
        self.db.confirm(self.db.propose([create()]), 1)
        task = self.db.tasks()[0]
        update = dict(kind="update", task_id=task["id"], version=1,
                      values={**create()["values"], "status": "done"})
        stale = self.db.propose([update])
        self.db.confirm(self.db.propose([update]), 1)
        with self.assertRaises(ValueError):
            self.db.confirm(stale, 1)
        self.assertEqual(self.db.tasks()[0]["status"], "done")
        removal = self.db.propose([dict(kind="delete", task_id=task["id"], version=2)])
        self.assertEqual(len(self.db.tasks()), 1)
        self.db.confirm(removal, 1)
        self.assertEqual(self.db.tasks(), [])
        with self.db.engine.connect() as conn:
            self.assertIsNotNone(conn.execute(text("SELECT deleted_at FROM tasks")).scalar())
            self.assertEqual(conn.execute(text("SELECT COUNT(*) FROM audit_events")).scalar(), 3)

    def test_conversations_drafts_and_foreign_keys(self):
        conversation = self.db.conversation()
        self.db.save_chat_draft(conversation, "Uns ent idea")
        self.assertEqual(self.db.chat_draft(conversation), "Uns ent idea")
        self.db.add_message(conversation, "user", "Help me study")
        self.assertEqual(self.db.chat_draft(conversation), "")
        self.db.add_message(conversation, "assistant", "partial", "incomplete")
        self.db.close()
        self.db = Database(self.path)
        self.assertEqual(self.db.conversation(), conversation)
        self.assertEqual(self.db.messages(conversation)[-1]["status"], "incomplete")
        with self.db.engine.connect() as conn:
            self.assertEqual(conn.execute(text("PRAGMA foreign_keys")).scalar(), 1)

    def test_validation_and_discard(self):
        for value in ("2026-02-30", "tomorrow", "20261105"):
            action = create()
            action["values"]["due_date"] = value
            with self.assertRaises(ValueError):
                self.db.propose([action])
        pending = self.db.propose([create()])
        self.db.discard(pending, 1)
        self.assertEqual(self.db.pending(), [])
        self.assertEqual(self.db.tasks(), [])


if __name__ == "__main__":
    unittest.main()
