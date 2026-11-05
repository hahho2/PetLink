import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import tempfile
from pathlib import Path
import unittest
from PySide6.QtCore import QPointF, QSettings
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication
from petlink.character_art import paint_character
from petlink.expressions import pose, notification_icon
from petlink.pet_window import PetKind, PetState, PetWindow


class ExpressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def render(self, kind, state, t=3, reduced=False):
        image = QImage(240,268,QImage.Format.Format_ARGB32)
        image.fill(0)
        p = QPainter(image)
        paint_character(p,kind,state,t,QPointF(),0,0,False,5,9,reduced=reduced,
                        sleepy=state=="sleepy",state_age=.35)
        p.end()
        return image

    def test_each_character_has_visually_distinct_states(self):
        for kind in PetKind:
            states = [self.render(kind.value,state.value) for state in PetState]
            for i, first in enumerate(states):
                for other in states[i+1:]:
                    self.assertNotEqual(first,other)

    def test_reduced_motion_removes_time_driven_pose_and_effect_movement(self):
        for kind in PetKind:
            for state in PetState:
                self.assertEqual(self.render(kind.value,state.value,1,True),
                                 self.render(kind.value,state.value,6,True))

    def test_badges_change_with_pet_and_retain_clickable_notification_state(self):
        with tempfile.TemporaryDirectory() as folder:
            pet = PetWindow(settings=QSettings(str(Path(folder)/"settings.ini"),QSettings.Format.IniFormat))
            pet.set_notification_count(3)
            images = []
            for kind in PetKind:
                pet.set_pet_kind(kind)
                self.assertFalse(pet.badge.isHidden())
                self.assertIn("3 unread",pet.badge.accessibleName())
                images.append(notification_icon(kind.value).pixmap(36,36).toImage())
            self.assertNotEqual(images[0],images[1])
            self.assertNotEqual(images[1],images[2])
            self.assertIn("Lola's bell",pet.badge.toolTip())
            pet.set_notification_count(0)
            self.assertTrue(pet.badge.isHidden())
            pet.close()

    def test_character_hops_differ_and_busy_state_cancels_transient_reaction(self):
        heights = [pose(kind.value,"happy",.35,1)["jump"] for kind in PetKind]
        self.assertEqual(len(set(heights)),3)
        self.assertTrue(all(height>0 for height in heights))
        with tempfile.TemporaryDirectory() as folder:
            pet=PetWindow(settings=QSettings(str(Path(folder)/"s.ini"),QSettings.Format.IniFormat))
            pet.react("task_confirmed")
            self.assertTrue(pet._expression_timer.isActive())
            pet.react("thinking")
            self.assertFalse(pet._expression_timer.isActive())
            self.assertEqual(pet.state,PetState.THINKING)
            pet.react("confused")
            self.assertEqual(pet.state,PetState.CONFUSED)
            pet.close()


if __name__ == "__main__":
    unittest.main()
