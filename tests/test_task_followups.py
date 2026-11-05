import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from PySide6.QtCore import QSettings
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from alembic import command
from alembic.config import Config

from petlink.chat_window import ChatWindow
from petlink.database import Database
from petlink.task_interpretation import parse_draft
from petlink.task_window import TaskEditor
from test_task_interpretation import DraftProvider, output


class FollowupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = Path(self.folder.name) / "followup.sqlite3"
        self.db = Database(self.path)
        self.settings = QSettings(str(Path(self.folder.name) / "settings.ini"), QSettings.Format.IniFormat)
        self.chat = ChatWindow(database=self.db, settings=self.settings, provider_factory=DraftProvider)
        self.chat.model.setText("test-model")
        DraftProvider.calls = 0

    def tearDown(self):
        self.chat.shutdown()
        self.wait_idle()
        self.chat.hide()
        self.chat.deleteLater()
        self.db.close()
        self.folder.cleanup()

    def wait_idle(self):
        deadline = time.monotonic() + 3
        while self.chat._busy and time.monotonic() < deadline:
            QTest.qWait(10)
        self.assertFalse(self.chat._busy)

    def ask(self, request, response):
        self.chat.composer.setPlainText(request)
        DraftProvider.response = response
        self.chat.draft_task()
        self.wait_idle()

    def test_clarification_survives_restart_and_ordinary_chat_is_separate(self):
        self.ask("Tomorrow solve 5 questions", '{"question":"Which subject?"}')
        reference_date = self.chat._task_context["date"]
        self.chat.shutdown()
        self.chat.hide()
        self.chat.deleteLater()
        self.db.close()
        self.db = Database(self.path)
        self.chat = ChatWindow(database=self.db, settings=self.settings, provider_factory=DraftProvider)
        self.chat.model.setText("test-model")
        self.assertEqual(self.chat._task_context["question"], "Which subject?")
        self.assertEqual(self.chat.draft_button.text(), "Continue task draft")
        before = deepcopy(self.chat._task_context)
        self.chat.composer.setPlainText("Help me plan lunch")
        DraftProvider.response = "Take a lunch break."
        self.chat.send()
        self.wait_idle()
        self.assertEqual(self.chat._task_context, before)
        self.ask("Algebra", output())
        contents = "\n".join(m.content for m in DraftProvider.messages)
        self.assertIn("Tomorrow solve 5 questions", contents)
        self.assertIn("Which subject?", contents)
        self.assertIn(reference_date, contents)
        self.assertNotIn("plan lunch", contents)
        self.assertEqual(DraftProvider.messages[-1].content, "Algebra")
        self.assertEqual(self.db.tasks(), [])
        self.assertEqual(self.db.pending(), [])

    def test_correction_merges_fields_and_revises_same_pending_draft(self):
        initial = json.loads(output())
        initial["task"].update(title="Solve 5 algebra questions", priority="high")
        initial["task"]["schedule"].update(frequency="daily", reminder_time="18:30", end_date="2026-11-30")
        self.ask("Solve 5 algebra questions daily", json.dumps(initial))
        original = deepcopy(self.chat._task_context["action"])
        editor = TaskEditor(self.db, action=original)
        editor.submit()
        self.chat.attach_task_pending(editor.saved_pending)
        pending = self.db.pending()[0]
        self.ask("make it 3", '{"changes":{"title":"Solve 3 algebra questions"}}')
        action = self.chat._task_context["action"]
        self.assertEqual(action["values"]["title"], "Solve 3 algebra questions")
        for key in ("description", "due_date", "priority", "schedule", "status"):
            self.assertEqual(action["values"][key], original["values"][key])
        self.assertIn("Solve 5 algebra questions", self.db.pending()[0]["payload"])
        editor = TaskEditor(self.db, action=action, pending=pending)
        editor.submit()
        self.chat.attach_task_pending(editor.saved_pending)
        revised = self.db.pending()[0]
        self.assertEqual(len(self.db.pending()), 1)
        self.assertEqual(revised["id"], pending["id"])
        self.assertEqual(revised["revision"], 2)
        self.assertFalse(self.db.tasks())
        self.db.confirm(revised["id"], revised["revision"])
        self.assertEqual(self.db.tasks()[0]["title"], "Solve 3 algebra questions")
        calls = DraftProvider.calls
        self.ask("make it 2", '{"changes":{"title":"Solve 2 algebra questions"}}')
        self.assertEqual(DraftProvider.calls, calls)
        self.assertIn("confirmed or discarded", self.chat.status.text())

    def test_new_request_keeps_saved_pending_and_does_not_forward_old_context(self):
        self.ask("Algebra tomorrow", output())
        editor = TaskEditor(self.db, action=self.chat._task_context["action"])
        editor.submit()
        self.chat.attach_task_pending(editor.saved_pending)
        self.chat.reset_task_context()
        self.assertEqual(self.db.task_context(self.chat.conversation_id), {})
        self.assertEqual(len(self.db.pending()), 1)
        self.assertEqual(self.chat.draft_button.text(), "Draft task from message")
        self.ask("Read meeting notes", '{"question":"Which meeting?"}')
        self.assertNotIn("Algebra tomorrow", "\n".join(m.content for m in DraftProvider.messages))

    def test_bad_correction_and_storage_failure_preserve_previous_context(self):
        self.ask("Algebra tomorrow", output())
        before = deepcopy(self.chat._task_context)
        for response in ('{"changes":{"status":"done"}}', '{"changes":{"schedule":{"frequency":"monthly"}}}', output()):
            self.ask("mark done", response)
            self.assertEqual(self.chat._task_context, before)
        with patch.object(self.db, "save_task_context", side_effect=SQLAlchemyError()):
            self.ask("make it 2", '{"changes":{"title":"Solve 2 algebra questions"}}')
        self.assertEqual(self.chat._task_context, before)
        self.assertEqual(self.db.task_context(self.chat.conversation_id), before)
        self.assertEqual(self.db.pending(), [])
        self.assertEqual(self.db.tasks(), [])

    def test_schedule_patch_preserves_omitted_fields_and_rejects_commands(self):
        current = parse_draft(output())
        current["values"]["schedule"].update(frequency="daily", reminder_time="18:30", end_date="2026-11-30")
        corrected = parse_draft('{"changes":{"schedule":{"reminder_time":"19:00"}}}', current=current)
        self.assertEqual(corrected["values"]["schedule"], {**current["values"]["schedule"], "reminder_time":"19:00"})
        for bad in ('{"changes":{"task_id":4}}', '{"changes":{}}', '{"changes":{"schedule":{"execute":true}}}'):
            with self.assertRaises(ValueError):
                parse_draft(bad, current=current)

    def test_v004_upgrade_preserves_chat_and_pending(self):
        import petlink.database as module
        legacy = Path(self.folder.name) / "legacy.sqlite3"
        engine = create_engine("sqlite:///" + legacy.as_posix())
        config = Config()
        config.set_main_option("script_location", str(Path(module.__file__).parent / "migrations"))
        with engine.begin() as conn:
            config.attributes["connection"] = conn
            command.upgrade(config, "004")
            conn.execute(text("INSERT INTO conversations(id,created_at,draft) VALUES(1,'now','keep this text')"))
            conn.execute(text("INSERT INTO pending_actions(payload,revision,status,created_at) VALUES('[]',1,'pending','now')"))
        engine.dispose()
        upgraded = Database(legacy)
        try:
            self.assertEqual(upgraded.chat_draft(1), "keep this text")
            self.assertEqual(upgraded.task_context(1), {})
            self.assertEqual(len(upgraded.pending()), 1)
        finally:
            upgraded.close()

    def test_controller_tracks_manual_review_and_cancelled_correction(self):
        from PySide6.QtWidgets import QSystemTrayIcon
        from petlink.pet_window import PetWindow
        from petlink.chat_window import CompanionController
        pet = PetWindow(settings=self.settings)
        with patch.object(QSystemTrayIcon, "isSystemTrayAvailable", return_value=False):
            controller = CompanionController(pet, chat=self.chat, database=self.db)
        def review(action, pending=None):
            editor = TaskEditor(self.db, action=action, pending=pending)
            editor.priority.setCurrentText("high")
            editor.submit()
            return editor.saved_pending
        try:
            with patch.object(controller.tasks, "_open_editor", side_effect=review):
                self.ask("Algebra tomorrow", output())
                controller.draft_card.findChildren(QPushButton)[0].click()
            pending = self.db.pending()[0]
            self.assertEqual(self.chat._task_context["pending"], dict(id=pending["id"], revision=1))
            self.assertEqual(self.chat._task_context["action"]["values"]["priority"], "high")
            with patch.object(controller.tasks, "_open_editor", return_value=None):
                self.ask("make it 2", '{"changes":{"title":"Solve 2 algebra questions"}}')
                controller.draft_card.findChildren(QPushButton)[0].click()
            self.assertEqual(self.chat._task_context["action"]["values"]["title"], "Solve 3 algebra questions")
            self.assertEqual(self.db.pending()[0]["revision"], 1)
            with patch.object(controller.tasks, "_open_editor", side_effect=review):
                self.ask("make it 4", '{"changes":{"title":"Solve 4 algebra questions"}}')
                controller.draft_card.findChildren(QPushButton)[0].click()
            self.assertEqual(self.db.pending()[0]["id"], pending["id"])
            self.assertEqual(self.db.pending()[0]["revision"], 2)
            self.assertFalse(self.db.tasks())
        finally:
            controller.stop_notifications()
            controller.voice.shutdown()
            controller.tasks.hide()
            controller.notifications.hide()
            pet.hide()


if __name__ == "__main__":
    unittest.main()
