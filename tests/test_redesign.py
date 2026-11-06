import os
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from PySide6.QtCore import QSettings,QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QPushButton,QGroupBox,QSystemTrayIcon
from petlink.chat_window import ChatWindow,CompanionController
from petlink.model_settings import ModelSettings,load_connection
from petlink.database import Database
from petlink.pet_window import PetWindow
from petlink.task_interpretation import direct_reminder


class RedesignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.settings=QSettings(str(Path(self.folder.name)/"settings.ini"),QSettings.Format.IniFormat)
        self.db=Database(Path(self.folder.name)/"ui.sqlite3")
        self.chat=ChatWindow(database=self.db,settings=self.settings)

    def tearDown(self):
        self.chat.shutdown()
        self.chat.hide()
        self.chat.deleteLater()
        self.db.close()
        self.folder.cleanup()

    def test_configuration_is_hidden_and_copy_copies_plain_message(self):
        self.assertTrue(self.chat.address.isHidden())
        self.assertTrue(self.chat.model.isHidden())
        self.assertIsNone(self.chat.findChild(QGroupBox))
        label=self.chat._bubble("You","<plain text>")
        label.parentWidget().findChild(QPushButton).click()
        self.assertEqual(self.app.clipboard().text(),"<plain text>")

    def test_discovery_is_background_and_cancel_does_not_apply_it(self):
        from types import SimpleNamespace
        dialog=ModelSettings(self.settings,load_connection(self.settings,SimpleNamespace(read=lambda _:"")))
        heartbeat=[]
        def slow(*args):
            time.sleep(.08)
            return {"data":[{"id":"local-test-model"}]}
        with patch("petlink.models.OpenAICompatibleProvider._request",side_effect=slow):
            QTimer.singleShot(10,lambda:heartbeat.append(True))
            dialog._connect(True)
            deadline=time.monotonic()+2
            while not dialog.refresh_button.isEnabled() and time.monotonic()<deadline:
                QTest.qWait(10)
        self.assertTrue(heartbeat)
        self.assertEqual(dialog.available.itemText(0),"local-test-model")
        dialog.reject()
        self.assertIsNone(self.settings.value("models/provider"))

    def test_card_requires_explicit_confirmation_and_ignores_second_activation(self):
        pet=PetWindow(settings=self.settings)
        with patch.object(QSystemTrayIcon,"isSystemTrayAvailable",return_value=False):
            controller=CompanionController(pet,chat=self.chat,database=self.db)
        try:
            action=direct_reminder("Remind me to study at 13:00 tomorrow")
            self.chat._task_context=dict(date="2026-11-05",messages=[],action=action,pending=None,question=None)
            controller.review_model_draft(action)
            self.assertFalse(self.db.tasks())
            button=next(b for b in controller.draft_card.findChildren(QPushButton) if b.text()=="Confirm")
            button.click()
            self.assertEqual(len(self.db.tasks()),1)
            button.click()
            self.assertEqual(len(self.db.tasks()),1)
        finally:
            controller.stop_notifications()
            controller.ui_timer.stop()
            controller.voice.shutdown()
            controller.tasks.hide()
            controller.notifications.hide()
            pet.hide()

    def test_error_summary_has_expandable_original_details(self):
        text="The model did not finish. The model used its output limit without returning answer text."
        self.chat.status.setText(text)
        self.assertNotEqual(self.chat.feedback.summary.text(),text)
        self.chat.feedback.details.click()
        self.assertFalse(self.chat.status.isHidden())
        self.assertEqual(self.chat.status.text(),text)

    def test_old_discovery_result_cannot_replace_new_connection_models(self):
        from types import SimpleNamespace
        dialog=ModelSettings(self.settings,load_connection(self.settings,SimpleNamespace(read=lambda _:"")))
        dialog._network_job=2
        current=dialog._values()
        dialog._network_ready(2,["current-model"],"Connected",current)
        dialog._network_ready(1,["old-model"],"Old response",current)
        self.assertEqual(dialog.available.itemText(0),"current-model")
        dialog.reject()
