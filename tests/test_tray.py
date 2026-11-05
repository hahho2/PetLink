import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QSettings
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from petlink.chat_window import CompanionController
from petlink.database import Database
from petlink.pet_window import PetKind, PetWindow


class TrayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_hide_restore_and_unread_keep_background_work_alive(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Database(Path(folder) / "tray.sqlite3")
            draft = db.propose([dict(kind="create", values=dict(title="Read meeting notes",
                description="", priority="normal", status="pending", due_date="2020-01-01"))])
            db.confirm(draft, 1)
            db.check_due_notifications()
            settings = QSettings(str(Path(folder) / "settings.ini"), QSettings.Format.IniFormat)
            pet = PetWindow(settings=settings)
            with patch.object(QSystemTrayIcon, "isSystemTrayAvailable", return_value=True):
                controller = CompanionController(pet, database=db)
            try:
                pet.show()
                controller._notifications_ready(0, db.unread_notifications(), "", True)
                self.assertIn("1 unread", controller.tray.toolTip())
                icon = controller.tray.icon().cacheKey()
                pet.set_pet_kind(PetKind.ANIMAL_CAT)
                self.assertIn("Lola", controller.tray.toolTip())
                self.assertNotEqual(icon, controller.tray.icon().cacheKey())
                controller.chat.composer.setPlainText("Keep my draft")
                controller.toggle_pet()
                self.assertFalse(pet.isVisible())
                self.assertEqual(controller.pet_action.text(), "Show pet")
                self.assertTrue(controller.notification_timer.isActive())
                self.assertEqual(pet._notification_count, 1)
                controller._tray_activated(QSystemTrayIcon.ActivationReason.DoubleClick)
                self.assertTrue(pet.isVisible())
                self.assertTrue(controller.chat.isVisible())
                self.assertEqual(controller.chat.composer.toPlainText(), "Keep my draft")
                self.assertEqual(db.unread_notifications(), 1)
                controller.voice.active = True
                controller._sync_tray()
                self.assertFalse(controller.pet_action.isEnabled())
                controller.toggle_pet()
                self.assertTrue(pet.isVisible())
                controller.voice.active = False
                quit_spy = QSignalSpy(pet.quit_requested)
                controller.tray_menu.actions()[-1].trigger()
                self.assertEqual(quit_spy.count(), 1)
            finally:
                controller.stop_notifications()
                controller.chat.shutdown()
                controller.voice.shutdown()
                controller.tray.hide()
                for window in (controller.chat, controller.tasks, controller.notifications, pet):
                    window.hide()
                db.close()

    def test_no_tray_does_not_allow_hiding_pet(self):
        with tempfile.TemporaryDirectory() as folder:
            pet = PetWindow(settings=QSettings(str(Path(folder) / "settings.ini"), QSettings.Format.IniFormat))
            with patch.object(QSystemTrayIcon, "isSystemTrayAvailable", return_value=False):
                controller = CompanionController(pet)
            pet.show()
            controller.toggle_pet()
            self.assertTrue(pet.isVisible())
            self.assertFalse(pet.tray_available)
            controller.chat.shutdown()
            controller.voice.shutdown()
            pet.hide()


if __name__ == "__main__":
    unittest.main()
