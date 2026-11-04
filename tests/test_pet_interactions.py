import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from array import array
from datetime import date
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
import wave
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from PySide6.QtCore import QPoint, QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from petlink.chat_window import ChatWindow, CompanionController
from petlink.database import Database
from petlink.pet_window import PetWindow
from petlink.voice_input import pcm16_mono, transcribe, VoiceInput
from petlink.notification_window import NotificationWindow


class PetInteractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.folder.name) / "pet.sqlite3")
        self.settings = QSettings(str(Path(self.folder.name) / "settings.ini"), QSettings.Format.IniFormat)

    def tearDown(self):
        self.db.close()
        self.folder.cleanup()

    def make_task(self, title, due, status="pending"):
        values = dict(title=title, description="", status=status, priority="normal", due_date=due)
        self.db.confirm(self.db.propose([dict(kind="create", values=values)]), 1)

    def test_due_alerts_are_deduplicated_and_acknowledged(self):
        self.make_task("Due now", "2026-11-04")
        self.make_task("Tomorrow", "2026-11-05")
        self.make_task("Finished", "2026-11-03", "done")
        self.assertEqual(self.db.check_due_notifications(date(2026, 11, 4)), 1)
        self.assertEqual(self.db.check_due_notifications(date(2026, 11, 4)), 0)
        self.assertEqual(self.db.unread_notifications(), 1)
        notification = self.db.notifications()[0]
        self.assertIn("Due now", notification["statement"])
        self.db.read_notification(notification["id"])
        self.assertEqual(self.db.unread_notifications(), 0)
        self.assertEqual(self.db.check_due_notifications(date(2026, 11, 4)), 0)

    def test_notifications_survive_database_reopen(self):
        self.make_task("Overdue", "2026-11-01")
        self.db.check_due_notifications(date(2026, 11, 4))
        path = self.db.path
        self.db.close()
        self.db = Database(path)
        self.assertEqual(self.db.unread_notifications(), 1)

    def test_v001_upgrade_preserves_existing_tasks(self):
        path = Path(self.folder.name) / "old.sqlite3"
        engine = create_engine("sqlite:///" + path.as_posix())
        config = Config()
        import petlink.database as module
        config.set_main_option("script_location", str(Path(module.__file__).parent / "migrations"))
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "001")
            connection.execute(text("INSERT INTO tasks(title,description,status,priority,created_at,updated_at,version) VALUES('Keep me','','pending','normal','2026-11-04','2026-11-04',1)"))
        engine.dispose()
        upgraded = Database(path)
        self.assertEqual(upgraded.tasks()[0]["title"], "Keep me")
        self.assertEqual(upgraded.notifications(), [])
        upgraded.close()

    def test_notification_statement_and_mark_read(self):
        self.make_task("Read this full statement", "2026-11-04")
        self.db.check_due_notifications(date(2026, 11, 4))
        window = NotificationWindow(self.db)
        window.refresh()
        self.assertIn("Read this full statement", window.statement.toPlainText())
        window.read.click()
        self.assertEqual(self.db.unread_notifications(), 0)
        self.assertFalse(window.read.isEnabled())
        window.hide()
        window.deleteLater()

    def test_single_click_types_double_click_opens_app(self):
        pet = PetWindow(settings=self.settings)
        chat = ChatWindow(database=self.db)
        controller = CompanionController(pet, chat=chat, database=self.db)
        pet.show()
        QTest.mouseClick(pet, Qt.MouseButton.LeftButton, pos=QPoint(120, 105))
        deadline = time.monotonic() + 2
        while not pet.controls.editor.isVisible() and time.monotonic() < deadline:
            QTest.qWait(20)
        self.assertTrue(pet.controls.editor.isVisible())
        self.assertFalse(chat.isVisible())
        QTest.mouseDClick(pet, Qt.MouseButton.LeftButton, pos=QPoint(120, 105))
        self.assertTrue(chat.isVisible())
        controller.voice.shutdown()
        controller.stop_notifications()
        chat.shutdown()
        chat.hide()
        pet.close()
        chat.deleteLater()
        pet.deleteLater()

    def test_voice_transcript_is_draft_not_automatic_send(self):
        pet = PetWindow(settings=self.settings)
        chat = ChatWindow(database=self.db)
        controller = CompanionController(pet, chat=chat, database=self.db)
        self.assertFalse(controller.voice.recording)
        controller.voice.text.emit("Create a study task")
        self.assertEqual(chat.composer.toPlainText(), "Create a study task")
        self.assertEqual(chat.history, [])
        self.assertEqual(self.db.tasks(), [])
        pet.set_notification_count(2)
        self.assertFalse(pet.badge.isHidden())
        pet.set_notification_count(0)
        self.assertTrue(pet.badge.isHidden())
        controller.voice.shutdown()
        controller.stop_notifications()
        chat.shutdown()
        pet.close()
        chat.deleteLater()
        pet.deleteLater()

    def test_pcm_conversion_and_local_cli_protocol(self):
        raw = array("h", [16000, -16000] * 160).tobytes()
        converted = pcm16_mono(raw, 16000, 2, "Int16")
        self.assertEqual(len(converted), 320)
        self.assertTrue(all(value == 0 for value in array("h", converted)))
        paths = []
        def runner(args, **kwargs):
            recording = Path(args[args.index("-f") + 1])
            paths.append(recording)
            with wave.open(str(recording), "rb") as stream:
                self.assertEqual((stream.getnchannels(), stream.getframerate()), (1, 16000))
            self.assertIn("-otxt", args)
            Path(args[args.index("-of")+1] + ".txt").write_text("Plan my study session", encoding="utf-8")
            return SimpleNamespace(returncode=0)
        result = transcribe("whisper-cli.exe", "model.bin", converted, runner=runner)
        self.assertEqual(result, "Plan my study session")
        self.assertFalse(paths[0].exists())


if __name__ == "__main__":
    unittest.main()
