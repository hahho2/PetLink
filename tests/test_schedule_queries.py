import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
from sqlalchemy.exc import SQLAlchemyError
from petlink.chat_window import ChatWindow
from petlink.database import Database
from petlink.models import ChatMessage
from petlink.schedule_queries import task_query, overview_reply
from petlink.scheduling import DEFAULT_SCHEDULE


def forbidden_provider(config):
    raise AssertionError("A saved-task question must never build a model provider")


class ScheduleQueryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.folder.name) / "queries.sqlite3")
        self.chat = ChatWindow(database=self.db, provider_factory=forbidden_provider,
            settings=QSettings(str(Path(self.folder.name) / "settings.ini"), QSettings.Format.IniFormat))

    def tearDown(self):
        self.chat.shutdown()
        self.chat.hide()
        self.chat.deleteLater()
        self.db.close()
        self.folder.cleanup()

    def propose(self, title="Make a cake", **changes):
        values = dict(title=title, description="", priority="normal", status="pending", due_date="2026-11-06",
            schedule={**DEFAULT_SCHEDULE, "reminder_time": "13:00"})
        values.update(changes)
        return self.db.propose([dict(kind="create", values=values)])

    def test_supported_queries_are_explicit_and_not_mutations_or_date_filters(self):
        for query, kind in (("Are there any schedules for me?", "schedules"), ("Do I have any tasks?", "tasks"),
                            ("Please show my reminders", "reminders"), ("What's on my schedule?", "schedules")):
            self.assertEqual(task_query(query), kind)
        for query in ("Delete my tasks", "Show my schedules then remove them", "What tasks do I have tomorrow?", "Explain a schedule"):
            self.assertIsNone(task_query(query))

    def test_exact_question_answers_from_empty_database_with_no_model(self):
        self.chat.composer.setPlainText("Are there any schedules for me?")
        self.chat.send()
        self.assertFalse(self.chat._busy)
        self.assertIn("no confirmed, unfinished schedules", self.chat._reply_label.text())
        self.assertIn("No model call", self.chat.status.text())
        self.assertEqual([m["role"] for m in self.db.messages(self.chat.conversation_id)], ["user", "assistant"])
        self.assertEqual(self.db.tasks(), [])
        self.assertEqual(self.db.pending(), [])

    def test_confirmed_schedules_and_pending_drafts_are_separate(self):
        self.db.confirm(self.propose(), 1)
        self.propose("Not yet confirmed")
        before = self.db.pending()
        self.chat.composer.setPlainText("Show my reminders")
        self.chat.send()
        reply = self.chat._reply_label.text()
        self.assertIn("Make a cake", reply)
        self.assertIn("2026-11-06", reply)
        self.assertIn("13:00", reply)
        self.assertIn("awaiting confirmation: 1", reply)
        self.assertNotIn("Not yet confirmed", reply)
        self.assertEqual(self.db.pending(), before)
        self.assertEqual(self.db.unread_notifications(), 0)

    def test_done_deleted_and_undated_tasks_have_correct_query_scope(self):
        self.db.confirm(self.propose("Finished", status="done"), 1)
        self.db.confirm(self.propose("Undated", due_date=None, schedule=dict(DEFAULT_SCHEDULE)), 1)
        self.db.confirm(self.propose("Date only", schedule=dict(DEFAULT_SCHEDULE)), 1)
        self.assertEqual(len(self.db.task_overview("tasks")["records"]), 2)
        self.assertEqual(len(self.db.task_overview("schedules")["records"]), 1)
        self.assertEqual(len(self.db.task_overview("reminders")["records"]), 0)
        task = next(t for t in self.db.tasks() if t["title"] == "Date only")
        self.db.confirm(self.db.propose([dict(kind="delete", task_id=task["id"], version=task["version"])]), 1)
        self.assertEqual(self.db.task_overview("schedules")["records"], [])

    def test_results_are_bounded_and_series_end_is_visible(self):
        for i in range(21):
            self.db.confirm(self.propose(f"Study {i}", schedule={**DEFAULT_SCHEDULE, "frequency": "daily", "end_date": "2026-11-12"}), 1)
        reply = overview_reply(self.db, "schedules")
        self.assertIn("first 20", reply)
        self.assertIn("Ends: 2026-11-12", reply)
        self.assertEqual(len(self.db.task_overview("schedules")["records"]), 20)
        with self.assertRaises(ValueError):
            self.db.task_overview("unknown")

    def test_read_failure_preserves_question_and_does_not_claim_no_schedules(self):
        question = "Are there any schedules for me?"
        self.chat.composer.setPlainText(question)
        with patch.object(self.db, "task_overview", side_effect=SQLAlchemyError()):
            self.chat.send()
        self.assertEqual(self.chat.composer.toPlainText(), question)
        self.assertIn("Could not read", self.chat.status.text())
        self.assertEqual(self.chat.history, [])

    def test_reply_save_retry_does_not_repeat_question_or_lookup(self):
        self.chat.composer.setPlainText("Show my schedules")
        original = self.db.add_message
        def fail_reply(conversation, role, content, status="complete"):
            if role == "assistant":
                raise SQLAlchemyError()
            return original(conversation, role, content, status)
        with patch.object(self.db, "add_message", side_effect=fail_reply):
            self.chat.send()
        self.assertIsNotNone(self.chat._pending_save)
        with patch.object(self.db, "task_overview", side_effect=AssertionError("Do not regenerate for Retry save")):
            self.chat.retry_last()
        self.assertIsNone(self.chat._pending_save)
        self.assertEqual(len(self.db.messages(self.chat.conversation_id)), 2)

    def test_retry_of_old_failed_question_keeps_parked_task_and_next_message(self):
        question = "Are there any schedules for me?"
        self.db.add_message(self.chat.conversation_id, "user", question)
        self.chat.history = [ChatMessage("user", question)]
        self.chat._retry_text = question
        self.chat._task_context = dict(date="2026-11-05", messages=[], action=None, pending=None, question="Which subject?")
        before = deepcopy(self.chat._task_context)
        self.chat.composer.setPlainText("My next message")
        self.chat.send(retry=True)
        self.assertEqual(len(self.db.messages(self.chat.conversation_id)), 2)
        self.assertEqual(self.chat.composer.toPlainText(), "My next message")
        self.assertEqual(self.chat._task_context, before)


if __name__ == "__main__":
    unittest.main()
