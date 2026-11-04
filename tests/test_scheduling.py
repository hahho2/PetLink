import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from datetime import date, datetime, timezone
from pathlib import Path
import tempfile
import unittest
import time as clock
from unittest.mock import patch
from PySide6.QtCore import QSettings, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from sqlalchemy import create_engine, text
from alembic import command
from alembic.config import Config
from petlink.database import Database
from petlink.scheduling import reminder_utc


def values(frequency="none", clock="18:30", zone="Asia/Kolkata", day="2026-11-04"):
    return dict(title="Study", description="", status="pending", priority="normal", due_date=day,
        schedule=dict(frequency=frequency, reminder_time=clock, timezone=zone))


def instant(value):
    return datetime.fromisoformat(value).astimezone(timezone.utc)


class SchedulingTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.folder.name) / "schedule.sqlite3")

    def tearDown(self):
        self.db.close()
        self.folder.cleanup()

    def save(self, task_values):
        self.db.confirm(self.db.propose([dict(kind="create", values=task_values)]), 1)
        return self.db.tasks()[0]

    def test_one_off_reminder_waits_for_time_and_only_fires_once(self):
        self.save(values())
        self.assertEqual(self.db.check_due_notifications(date(2026, 11, 4)), 0)
        self.assertEqual(self.db.poll_reminders(instant("2026-11-04T12:59:00+00:00")), 0)
        self.assertEqual(self.db.poll_reminders(instant("2026-11-04T13:00:00+00:00")), 1)
        self.assertEqual(self.db.poll_reminders(instant("2026-11-04T14:00:00+00:00")), 0)
        self.assertIn("18:30", self.db.notifications()[0]["statement"])

    def test_daily_occurrence_completion_does_not_complete_series(self):
        task = self.save(values("daily"))
        self.db.poll_reminders(instant("2026-11-05T13:00:00+00:00"))
        occurrences = self.db.occurrences()
        self.assertEqual({o["scheduled_date"] for o in occurrences}, {"2026-11-04", "2026-11-05"})
        occurrence = occurrences[0]
        action = dict(kind="complete_occurrence", task_id=task["id"], version=task["version"], occurrence_id=occurrence["id"])
        pending = self.db.propose([action])
        self.assertIsNone(self.db.occurrences()[0]["completed_at"])
        self.db.confirm(pending, 1)
        self.assertIsNotNone(self.db.occurrences()[0]["completed_at"])
        self.assertEqual(self.db.tasks()[0]["status"], "pending")
        self.db.poll_reminders(instant("2026-11-06T13:00:00+00:00"))
        self.assertEqual(len(self.db.occurrences()), 3)
        with self.assertRaises(ValueError):
            self.db.confirm(self.db.propose([action]), 1)

    def test_weekly_anchor_and_missed_reminder_after_restart(self):
        self.save(values("weekly"))
        path = self.db.path
        self.db.close()
        self.db = Database(path)
        self.assertEqual(self.db.poll_reminders(instant("2026-11-11T13:01:00+00:00")), 2)
        self.assertEqual({o["scheduled_date"] for o in self.db.occurrences()}, {"2026-11-04", "2026-11-11"})
        self.assertEqual(self.db.poll_reminders(instant("2026-11-11T13:02:00+00:00")), 0)

    def test_schedule_edit_needs_confirmation_and_cancels_old_pending_occurrences(self):
        task = self.save(values("daily"))
        changed = values("weekly", clock="20:00")
        action = dict(kind="update", task_id=task["id"], version=task["version"], values=changed)
        draft = self.db.propose([action])
        self.assertEqual(self.db.tasks()[0]["schedule"]["frequency"], "daily")
        self.db.confirm(draft, 1)
        self.assertEqual(self.db.tasks()[0]["schedule"]["frequency"], "weekly")
        with self.db.engine.connect() as conn:
            self.assertEqual(conn.execute(text("SELECT COUNT(*) FROM task_occurrences WHERE cancelled_at IS NOT NULL")).scalar(), 1)
        self.assertEqual(self.db.poll_reminders(instant("2026-11-04T13:00:00+00:00")), 0)
        self.assertEqual(self.db.poll_reminders(instant("2026-11-04T14:30:00+00:00")), 1)

    def test_done_or_removed_series_has_no_future_alerts(self):
        task = self.save(values("daily"))
        self.db.confirm(self.db.propose([dict(kind="update", task_id=task["id"], version=1, values={**values("daily"), "status": "done"})]), 1)
        self.assertEqual(self.db.poll_reminders(instant("2026-11-20T13:00:00+00:00")), 0)

    def test_dst_gap_and_overlap_are_deterministic(self):
        self.assertEqual(reminder_utc(date(2026, 3, 8), "02:30", "America/New_York"), "2026-03-08T07:00:00.000000+00:00")
        self.assertEqual(reminder_utc(date(2026, 11, 1), "01:30", "America/New_York"), "2026-11-01T05:30:00.000000+00:00")

    def test_invalid_schedule_and_atomic_rollback(self):
        for schedule in (dict(frequency="hourly", reminder_time=None, timezone="UTC"),
                         dict(frequency="daily", reminder_time="25:00", timezone="UTC"),
                         dict(frequency="daily", reminder_time="12:00", timezone="Unknown/Zone")):
            with self.assertRaises(ValueError):
                self.db.propose([dict(kind="create", values={**values(), "schedule": schedule})])
        with self.assertRaises(ValueError):
            self.db.propose([dict(kind="create", values=values(day=None))])
        pending = self.db.propose([dict(kind="create", values=values("daily")), dict(kind="delete", task_id=999, version=1)])
        with self.assertRaises(ValueError):
            self.db.confirm(pending, 1)
        self.assertEqual(self.db.tasks(), [])
        self.assertEqual(self.db.occurrences(), [])

    def test_v002_migration_preserves_existing_notifications_and_deduplication(self):
        path = Path(self.folder.name) / "old-v2.sqlite3"
        engine = create_engine("sqlite:///" + path.as_posix())
        config = Config()
        import petlink.database as module
        config.set_main_option("script_location", str(Path(module.__file__).parent / "migrations"))
        with engine.begin() as conn:
            config.attributes["connection"] = conn
            command.upgrade(config, "002")
            conn.execute(text("INSERT INTO tasks(id,title,description,status,priority,due_date,created_at,updated_at,version) VALUES(1,'Existing','','pending','normal','2026-11-04','2026-11-04','2026-11-04',1)"))
            conn.execute(text("INSERT INTO notifications(task_id,due_date,statement,created_at) VALUES(1,'2026-11-04','Keep this alert','2026-11-04')"))
        engine.dispose()
        upgraded = Database(path)
        self.assertEqual(upgraded.notifications()[0]["statement"], "Keep this alert")
        self.assertEqual(upgraded.check_due_notifications(date(2026, 11, 4)), 0)
        self.assertEqual(upgraded.unread_notifications(), 1)
        upgraded.close()

    def test_completed_history_is_retained_after_schedule_change(self):
        task = self.save(values("daily"))
        occurrence = self.db.occurrences()[0]
        self.db.confirm(self.db.propose([dict(kind="complete_occurrence", task_id=task["id"], version=1, occurrence_id=occurrence["id"])]), 1)
        self.db.confirm(self.db.propose([dict(kind="update", task_id=task["id"], version=1, values=values("weekly"))]), 1)
        with self.db.engine.connect() as conn:
            self.assertIsNotNone(conn.execute(text("SELECT completed_at FROM task_occurrences WHERE id=:id"), {"id": occurrence["id"]}).scalar())


class ScheduleUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.folder.name) / "ui.sqlite3")

    def tearDown(self):
        self.db.close()
        self.folder.cleanup()

    def test_schedule_and_occurrence_use_review_then_confirm(self):
        from petlink.task_window import TaskEditor, TaskWindow
        editor = TaskEditor(self.db)
        editor.title.setText("Daily reading")
        editor.due.setText("2026-11-04")
        editor.frequency.setCurrentIndex(editor.frequency.findData("daily"))
        editor.reminder_time.setText("18:30")
        editor.submit()
        self.assertEqual(self.db.tasks(), [])
        window = TaskWindow(self.db)
        window.pending.setCurrentRow(0)
        self.assertIn("18:30", window.preview.toPlainText())
        window.confirm.click()
        self.assertEqual(self.db.tasks()[0]["schedule"]["frequency"], "daily")
        window.tabs.setCurrentIndex(2)
        window.occurrences.setCurrentRow(0)
        window.complete_occurrence()
        self.assertIsNone(self.db.occurrences()[0]["completed_at"])
        window.confirm.click()
        self.assertIsNotNone(self.db.occurrences()[0]["completed_at"])
        window.hide()
        window.deleteLater()
        editor.deleteLater()

    def test_reminder_worker_leaves_gui_responsive(self):
        from petlink.pet_window import PetWindow
        from petlink.chat_window import ChatWindow, CompanionController
        settings = QSettings(str(Path(self.folder.name) / "settings.ini"), QSettings.Format.IniFormat)
        pet = PetWindow(settings=settings)
        chat = ChatWindow(database=self.db)
        controller = CompanionController(pet, chat=chat, database=self.db)
        heartbeats = []
        QTimer.singleShot(20, lambda: heartbeats.append(True))
        original = self.db.poll_reminders
        def slow():
            clock.sleep(.1)
            return original()
        with patch.object(self.db, "poll_reminders", side_effect=slow):
            start = clock.monotonic()
            controller.check_notifications()
            self.assertLess(clock.monotonic() - start, .09)
            deadline = clock.monotonic() + 3
            while controller._notification_running and clock.monotonic() < deadline:
                QTest.qWait(10)
        self.assertTrue(heartbeats)
        self.assertFalse(controller._notification_running)
        controller.stop_notifications()
        controller.voice.shutdown()
        chat.shutdown()
        pet.close()
        chat.hide()
        chat.deleteLater()
        pet.deleteLater()


if __name__ == "__main__":
    unittest.main()
