"""Run with python -m unittest discover -s tests -p test_animation.py."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tempfile
import unittest
from pathlib import Path
from PySide6.QtCore import QSettings, Qt
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication
from petlink.pet_window import PetKind, PetState, PetWindow
from petlink.character_art import layers, cat_ears


class AnimationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.settings = QSettings(str(Path(self.directory.name) / "settings.ini"), QSettings.Format.IniFormat)
        self.pet = PetWindow(settings=self.settings)

    def tearDown(self):
        self.pet.close()
        self.directory.cleanup()

    def test_every_character_and_expression_renders(self):
        for kind in PetKind:
            self.pet.set_pet_kind(kind)
            self.assertTrue(all(not part.isNull() for part in layers(kind.value)))
            for state in PetState:
                self.pet.set_state(state)
                self.pet._tick()
                self.assertFalse(self.pet.grab().isNull())
        self.assertEqual(len(cat_ears()), 2)

    def test_preferences_restore(self):
        self.pet.set_pet_kind(PetKind.ANIMAL_CAT)
        self.pet._set_reduced(True)
        other = PetWindow(settings=self.settings)
        self.assertEqual(other.pet_kind, PetKind.ANIMAL_CAT)
        self.assertTrue(other._reduced)
        other.close()

    def test_double_click_does_not_emit_single_click(self):
        self.pet.show()
        spy = QSignalSpy(self.pet.clicked)
        QTest.mouseDClick(self.pet, Qt.MouseButton.LeftButton)
        QTest.qWait(QApplication.doubleClickInterval() + 30)
        self.assertEqual(spy.count(), 0)
        self.assertGreater(self.pet._reaction_at, -1)

    def test_event_hooks_and_audio_envelope(self):
        self.pet.react("microphone_on")
        self.assertEqual(self.pet.state, PetState.LISTENING)
        self.pet.react("task_completed")
        self.assertEqual(self.pet.state, PetState.HAPPY)
        self.pet.set_speech_level(5)
        self.assertEqual(self.pet._speech_level, 1)
        self.pet.set_talking(True)
        self.assertFalse(self.pet.grab().isNull())


if __name__ == "__main__":
    unittest.main()
