import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from sqlalchemy.exc import SQLAlchemyError
from PySide6.QtCore import QSettings
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from petlink.chat_window import ChatWindow
from petlink.database import Database
from petlink.task_window import TaskEditor, TaskWindow


class Provider:
    def __init__(self, config):
        pass

    def stream(self, history):
        yield "A focused work session is a good start."


class PersistenceUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.folder.name) / "ui.sqlite3")
        self.settings = QSettings(str(Path(self.folder.name) / "settings.ini"), QSettings.Format.IniFormat)

    def tearDown(self):
        self.db.close()
        self.folder.cleanup()

    def test_review_before_confirm_and_task_edit(self):
        editor = TaskEditor(self.db)
        editor.title.setText("Read a chapter")
        editor.submit()
        self.assertEqual(self.db.tasks(), [])
        window = TaskWindow(self.db)
        window.pending.setCurrentRow(0)
        self.assertIn("Read a chapter", window.preview.toPlainText())
        window.confirm.click()
        self.assertEqual(self.db.tasks()[0]["title"], "Read a chapter")
        window.tasks.setCurrentRow(0)
        window.delete_task()
        self.assertEqual(len(self.db.tasks()), 1)
        window.confirm.click()
        self.assertEqual(self.db.tasks(), [])
        window.hide()
        window.deleteLater()
        editor.deleteLater()

    def test_chat_and_unsent_input_restore(self):
        chat = ChatWindow(database=self.db, provider_factory=Provider, settings=self.settings)
        chat.model.setText("fixture")
        chat.composer.setPlainText("Help me study")
        chat.send()
        deadline = time.monotonic() + 3
        while chat._busy and time.monotonic() < deadline:
            QTest.qWait(10)
        self.assertFalse(chat._busy)
        chat.composer.setPlainText("Next idea")
        chat.shutdown()
        restored = ChatWindow(database=self.db, settings=self.settings)
        self.assertEqual([m.role for m in restored.history], ["user", "assistant"])
        self.assertEqual(restored.composer.toPlainText(), "Next idea")
        restored.shutdown()
        chat.hide()
        restored.hide()
        chat.deleteLater()
        restored.deleteLater()

    def test_failed_user_save_does_not_send_or_lose_input(self):
        chat = ChatWindow(database=self.db, provider_factory=Provider, settings=self.settings)
        chat.model.setText("fixture")
        chat.composer.setPlainText("Keep this text")
        with patch.object(self.db, "add_message", side_effect=SQLAlchemyError()):
            chat.send()
        self.assertFalse(chat._busy)
        self.assertEqual(chat.composer.toPlainText(), "Keep this text")
        self.assertEqual(chat.history, [])
        chat.shutdown()
        chat.deleteLater()

    def test_reply_save_can_retry_without_generating_again(self):
        chat = ChatWindow(database=self.db, provider_factory=Provider, settings=self.settings)
        chat.model.setText("fixture")
        chat.composer.setPlainText("Help me study")
        original = self.db.add_message
        def save(conversation, role, content, status="complete"):
            if role == "assistant":
                raise SQLAlchemyError()
            return original(conversation, role, content, status)
        with patch.object(self.db, "add_message", side_effect=save):
            chat.send()
            deadline = time.monotonic() + 3
            while chat._busy and time.monotonic() < deadline:
                QTest.qWait(10)
        self.assertIsNotNone(chat._pending_save)
        chat.retry_last()
        self.assertIsNone(chat._pending_save)
        records = self.db.messages(chat.conversation_id)
        self.assertEqual([r["role"] for r in records], ["user", "assistant"])
        chat.shutdown()
        chat.deleteLater()


if __name__ == "__main__":
    unittest.main()
