import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from datetime import date, datetime, timezone
from pathlib import Path
import tempfile
import unittest
import time
from threading import Event
from unittest.mock import patch
from sqlalchemy import create_engine, text
from alembic import command
from alembic.config import Config
from petlink.database import Database
from petlink.scheduling import one_month_end, task_status_label


def task_values(end="2026-11-30", start="2026-11-01", frequency="daily"):
    return dict(title="Meeting notes", description="", priority="normal", status="pending", due_date=start,
        schedule=dict(frequency=frequency, reminder_time="18:30", timezone="Asia/Kolkata", end_date=end))


class SeriesEndTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.folder.name) / "series.sqlite3")

    def tearDown(self):
        self.db.close()
        self.folder.cleanup()

    def save(self, values):
        self.db.confirm(self.db.propose([dict(kind="create", values=values)]), 1)
        return self.db.tasks()[0]

    def update(self, task, values):
        self.db.confirm(self.db.propose([dict(kind="update", task_id=task["id"], version=task["version"], values=values)]), 1)
        return self.db.tasks()[0]

    def complete(self, task, occurrence):
        self.db.confirm(self.db.propose([dict(kind="complete_occurrence", task_id=task["id"], version=task["version"], occurrence_id=occurrence["id"])]), 1)

    def test_inclusive_month_has_thirty_dates_and_stops(self):
        task = self.save(task_values())
        self.assertEqual(self.db.poll_reminders(datetime(2026, 12, 15, tzinfo=timezone.utc)), 30)
        occurrences = self.db.occurrences()
        self.assertEqual(len(occurrences), 30)
        self.assertEqual(max(o["scheduled_date"] for o in occurrences), "2026-11-30")
        self.assertEqual(self.db.poll_reminders(datetime(2027, 1, 1, tzinfo=timezone.utc)), 0)
        self.assertEqual(self.db.tasks()[0]["progress"]["planned"], 30)
        self.assertEqual(task_status_label(task, datetime(2026, 12, 1, tzinfo=timezone.utc)), "Ended series")

    def test_completion_acknowledges_only_its_own_alert(self):
        task = self.save(task_values(end="2026-11-02"))
        self.db.poll_reminders(datetime(2026, 11, 3, tzinfo=timezone.utc))
        self.assertEqual(self.db.unread_notifications(), 2)
        self.complete(task, self.db.occurrences()[0])
        self.assertEqual(self.db.unread_notifications(), 1)
        self.complete(task, self.db.occurrences()[1])
        self.assertEqual(self.db.unread_notifications(), 0)
        self.assertEqual(self.db.tasks()[0]["status"], "pending")
        self.assertEqual(self.db.tasks()[0]["progress"]["completed"], 2)

    def test_end_only_edits_preserve_completion_and_occurrence_ids(self):
        task = self.save(task_values(end="2026-11-03"))
        self.db.poll_reminders(datetime(2026, 11, 4, tzinfo=timezone.utc))
        occurrence = self.db.occurrences()[-1]
        self.complete(task, occurrence)
        shortened = self.update(task, task_values(end="2026-11-02"))
        self.assertEqual({o["scheduled_date"] for o in self.db.occurrences()}, {"2026-11-01", "2026-11-02"})
        self.assertEqual(shortened["progress"]["completed"], 1)
        extended = self.update(shortened, task_values(end="2026-11-05"))
        self.db.poll_reminders(datetime(2026, 11, 6, tzinfo=timezone.utc))
        self.assertEqual(len(self.db.occurrences()), 5)
        original = next(o for o in self.db.occurrences() if o["id"] == occurrence["id"])
        self.assertIsNotNone(original["completed_at"])
        self.assertEqual(extended["progress"]["completed"], 1)

    def test_end_date_change_waits_for_confirmation_and_rejects_old_preview(self):
        task = self.save(task_values())
        pending = self.db.propose([dict(kind="update", task_id=task["id"], version=1, values=task_values(end="2026-11-10"))])
        self.assertEqual(self.db.tasks()[0]["schedule"]["end_date"], "2026-11-30")
        self.db.revise(pending, 1, [dict(kind="update", task_id=task["id"], version=1, values=task_values(end="2026-11-15"))])
        with self.assertRaises(ValueError):
            self.db.confirm(pending, 1)
        self.db.confirm(pending, 2)
        self.assertEqual(self.db.tasks()[0]["schedule"]["end_date"], "2026-11-15")

    def test_invalid_end_dates(self):
        for end in ("2026-10-31", "tomorrow", "2026-11-31", "20261130"):
            with self.assertRaises(ValueError):
                self.db.propose([dict(kind="create", values=task_values(end=end))])
        with self.assertRaises(ValueError):
            self.db.propose([dict(kind="create", values=task_values(frequency="none"))])

    def test_month_button_dates_and_status_labels(self):
        self.assertEqual(one_month_end("2026-11-01"), "2026-11-30")
        self.assertEqual(one_month_end("2026-11-04"), "2026-12-03")
        self.assertEqual(one_month_end("2026-01-31"), "2026-02-27")
        task = self.save(task_values())
        self.assertEqual(task_status_label(task, datetime(2026, 11, 5, tzinfo=timezone.utc)), "Active series")
        self.assertEqual(task_status_label(task, datetime(2026, 10, 1, tzinfo=timezone.utc)), "Scheduled series")
        stopped = self.update(task, {**task_values(), "status": "done"})
        self.assertEqual(task_status_label(stopped), "Stopped series")

    def test_old_pending_schedule_without_end_date_remains_compatible(self):
        values = task_values()
        del values["schedule"]["end_date"]
        task = self.save(values)
        self.assertIsNone(task["schedule"]["end_date"])

    def test_migration_preserves_v003_schedule_and_completion(self):
        path = Path(self.folder.name) / "v003.sqlite3"
        engine = create_engine("sqlite:///"+path.as_posix())
        config = Config()
        import petlink.database as module
        config.set_main_option("script_location", str(Path(module.__file__).parent/"migrations"))
        with engine.begin() as conn:
            config.attributes["connection"] = conn
            command.upgrade(config, "003")
            conn.execute(text("INSERT INTO tasks(id,title,description,status,priority,due_date,created_at,updated_at,version) VALUES(1,'Existing series','','pending','normal','2026-11-01','2026-11-01','2026-11-01',1)"))
            conn.execute(text("INSERT INTO task_schedules(task_id,frequency,reminder_time,timezone,revision) VALUES(1,'daily','18:30','Asia/Kolkata',1)"))
            conn.execute(text("INSERT INTO task_occurrences(task_id,schedule_revision,scheduled_date,reminder_at,completed_at) VALUES(1,1,'2026-11-01','2026-11-01T13:00:00+00:00','2026-11-01T14:00:00+00:00')"))
        engine.dispose()
        upgraded = Database(path)
        self.assertEqual(upgraded.tasks()[0]["schedule"]["frequency"], "daily")
        self.assertIsNone(upgraded.tasks()[0]["schedule"]["end_date"])
        self.assertEqual(upgraded.tasks()[0]["progress"]["completed"], 1)
        upgraded.close()

    def test_one_month_editor_uses_explicit_reviewed_dates(self):
        from PySide6.QtWidgets import QApplication
        from petlink.task_window import TaskEditor
        app = QApplication.instance() or QApplication([])
        editor = TaskEditor(self.db)
        editor.title.setText("Meeting notes")
        editor.due.setText("2026-11-01")
        editor.frequency.setCurrentIndex(editor.frequency.findData("daily"))
        editor.month.click()
        self.assertEqual(editor.end_date.text(), "2026-11-30")
        self.assertEqual(editor.status.itemText(0), "Active series")
        editor.submit()
        self.assertEqual(self.db.tasks(), [])
        self.db.confirm(self.db.pending()[0]["id"], 1)
        self.assertEqual(self.db.tasks()[0]["schedule"]["end_date"], "2026-11-30")
        editor.deleteLater()

    def test_alert_acknowledgement_rechecks_an_inflight_badge_snapshot(self):
        from PySide6.QtCore import QSettings
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication
        from petlink.pet_window import PetWindow
        from petlink.chat_window import ChatWindow, CompanionController
        app = QApplication.instance() or QApplication([])
        values = task_values(end=None, start=date.today().isoformat(), frequency="none")
        values["schedule"]["reminder_time"] = None
        task = self.save(values)
        pet = PetWindow(settings=QSettings(str(Path(self.folder.name)/"pet.ini"), QSettings.Format.IniFormat))
        chat = ChatWindow(database=self.db, settings=pet.settings)
        controller = CompanionController(pet, chat=chat, database=self.db)
        held, release = Event(), Event()
        reads = []
        original = self.db.unread_notifications
        def snapshot():
            result = original()
            reads.append(result)
            if len(reads) == 1:
                held.set()
                release.wait(2)
            return result
        try:
            with patch.object(self.db, "unread_notifications", side_effect=snapshot):
                controller.check_notifications()
                deadline = time.monotonic()+3
                while not held.is_set() and time.monotonic()<deadline:
                    QTest.qWait(10)
                self.assertTrue(held.is_set())
                self.update(task, {**values, "status": "done"})
                controller.check_notifications()
                release.set()
                while (len(reads)<2 or controller._notification_running or controller._notification_recheck) and time.monotonic()<deadline:
                    QTest.qWait(10)
                self.assertGreaterEqual(len(reads), 2)
                self.assertTrue(pet.badge.isHidden())
        finally:
            release.set()
            controller.stop_notifications()
            controller.voice.shutdown()
            chat.shutdown()
            pet.close()
            chat.hide()
            chat.deleteLater()
            pet.deleteLater()


if __name__ == "__main__":
    unittest.main()
