import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path
import tempfile
import time
import unittest

from PySide6.QtCore import QSettings, QTimer, Qt
from PySide6.QtGui import QInputMethodEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from petlink.chat_window import ChatWindow, CompanionController, local_config
from petlink.models import ModelError
from petlink.pet_window import PetKind, PetState, PetWindow


class FakeProvider:
    fail = False
    calls = 0
    last_history = []

    def __init__(self, config):
        self.config = config

    def health_check(self):
        return True

    def stream(self, history):
        type(self).last_history = list(history)
        type(self).calls += 1
        time.sleep(.1)
        if self.fail:
            raise ModelError("Offline")
        yield "Try a focused "
        yield "25-minute work session."


class ChatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        settings = QSettings(str(Path(self.folder.name) / "settings.ini"), QSettings.Format.IniFormat)
        self.chat = ChatWindow(provider_factory=FakeProvider, settings=settings)
        self.chat.model.setText("test-model")
        FakeProvider.fail, FakeProvider.calls = False, 0

    def tearDown(self):
        self.chat.shutdown()
        self.wait_idle()
        self.chat.hide()
        self.chat.deleteLater()

    def wait_idle(self):
        deadline = time.monotonic() + 3
        while self.chat._busy and time.monotonic() < deadline:
            QTest.qWait(10)
        self.assertFalse(self.chat._busy)

    def test_local_endpoint_validation(self):
        config = local_config("http://127.0.0.1:11434/v1/", "test")
        self.assertEqual(config.base_url, "http://127.0.0.1:11434")
        for address in ("https://api.example.com", "http://localhost@evil.com", "http://localhost/foo", "http://localhost:bad"):
            with self.assertRaises(ValueError):
                local_config(address, "test")

    def test_streaming_does_not_block_gui_and_prevents_duplicates(self):
        self.chat.composer.setPlainText("Help me study")
        heartbeat = []
        QTimer.singleShot(20, lambda: heartbeat.append(True))
        self.chat.send()
        self.chat.send()
        self.wait_idle()
        self.assertTrue(heartbeat)
        self.assertEqual(FakeProvider.calls, 1)
        self.assertEqual(self.chat.history[-1].role, "assistant")
        self.assertIn("25-minute", self.chat._reply_label.text())

    def test_error_retry_keeps_one_user_turn(self):
        FakeProvider.fail = True
        self.chat.composer.setPlainText("Help me focus")
        self.chat.send()
        self.wait_idle()
        self.assertIn("did not finish", self.chat.status.text())
        FakeProvider.fail = False
        self.chat.send(retry=True)
        self.wait_idle()
        self.assertEqual([m.role for m in self.chat.history], ["user", "assistant"])

    def test_stop_does_not_commit_partial_reply(self):
        self.chat.composer.setPlainText("A plan please")
        self.chat.send()
        self.chat.stop()
        self.wait_idle()
        self.assertEqual([m.role for m in self.chat.history], ["user"])
        self.assertIn("stopped", self.chat.status.text())

    def test_connection_and_missing_model_feedback(self):
        self.chat.model.clear()
        self.chat.composer.setPlainText("hello")
        self.chat.send()
        self.assertEqual(FakeProvider.calls, 0)
        self.assertEqual(self.chat.composer.toPlainText(), "hello")
        self.chat.model.setText("test")
        self.chat.test_connection()
        self.wait_idle()
        self.assertIn("reachable", self.chat.status.text())

    def test_local_prompt_is_bounded_for_small_models(self):
        from petlink.models import ChatMessage
        self.chat.history = [ChatMessage("user" if i % 2 == 0 else "assistant", "x" * 1800) for i in range(16)]
        self.chat.composer.setPlainText("Give a short tip")
        self.chat.send()
        self.wait_idle()
        self.assertLessEqual(len(FakeProvider.last_history), 9)  # system + eight recent messages
        self.assertLessEqual(sum(len(m.content) for m in FakeProvider.last_history[1:]), 8000)
        self.assertIn("Draft task from message", FakeProvider.last_history[0].content)

    def test_input_method_enter_does_not_send_during_composition(self):
        self.chat.composer.setPlainText("Study")
        QApplication.sendEvent(self.chat.composer, QInputMethodEvent("pending", []))
        QTest.keyClick(self.chat.composer, Qt.Key.Key_Return)
        self.assertEqual(FakeProvider.calls, 0)
        QApplication.sendEvent(self.chat.composer, QInputMethodEvent("", []))

    def test_keyboard_and_pet_lifecycle(self):
        with tempfile.TemporaryDirectory() as folder:
            settings = QSettings(str(Path(folder) / "settings.ini"), QSettings.Format.IniFormat)
            pet = PetWindow(settings=settings)
            controller = CompanionController(pet, chat=self.chat)
            pet.show()
            controller.show_chat()
            pet.set_pet_kind(PetKind.ANIMAL_CAT)
            self.assertEqual(self.chat.title.text(), "Chat with Lola")
            QTest.keyClicks(self.chat.composer, "Study")
            QTest.keyClick(self.chat.composer, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
            self.assertIn("\n", self.chat.composer.toPlainText())
            QTest.keyClick(self.chat.composer, Qt.Key.Key_Return)
            self.wait_idle()
            self.chat.close()
            self.assertFalse(self.chat.isVisible())
            self.assertTrue(pet.isVisible())
            self.assertEqual(pet.state, PetState.IDLE)
            pet.close()


if __name__ == "__main__":
    unittest.main()
