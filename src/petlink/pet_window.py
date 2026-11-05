"""Floating companion with independent animation channels and persistent preferences."""

from __future__ import annotations

import math
import random
import time
from enum import Enum

from PySide6.QtCore import QPoint, QPointF, QSettings, QTimer, Qt, Signal
from PySide6.QtGui import QActionGroup, QCursor, QPainter
from PySide6.QtWidgets import QApplication, QMenu, QToolButton, QWidget


class PetState(str, Enum):
    IDLE = "idle"
    TALKING = "talking"
    LISTENING = "listening"
    THINKING = "thinking"
    CURIOUS = "curious"
    CONFUSED = "confused"
    HAPPY = "happy"
    SLEEPY = "sleepy"
    REMINDER = "reminder"


class PetKind(str, Enum):
    ANIME_CORAL = "anime_coral"
    ANIME_AZURE = "anime_azure"
    ANIMAL_CAT = "animal_cat"


class PetWindow(QWidget):
    """Transparent, draggable pet with cached artwork and no model dependency."""

    clicked = Signal()
    double_clicked = Signal()
    chat_requested = Signal()
    voice_setup_requested = Signal()
    quit_requested = Signal()
    hide_requested = Signal()
    pet_kind_changed = Signal(PetKind)

    def __init__(self, pet_kind: PetKind = PetKind.ANIME_AZURE, *, settings=None, idle_intervals=None) -> None:
        super().__init__()
        self.settings = settings if settings is not None else QSettings("PetLink", "Companion")
        self._state = PetState.IDLE
        try:
            self._pet_kind = PetKind(self.settings.value("pet", pet_kind.value))
        except ValueError:
            self._pet_kind = pet_kind
        self._clock = time.monotonic()
        self._state_started = self._clock
        self._notification_count = 0
        self.tray_available = False
        self._speech_level = None
        self._last_activity = self._clock
        self._blink_at = self._wink_at = self._ear_at = self._reaction_at = -100.0
        self._glance = self._tilt = self._angle = 0.0
        self._gaze = QPointF()
        self._reduced = self.settings.value("reduced_motion", False, type=bool)
        self._intervals = {"blink": (3, 7), "wink": (20, 45), "glance": (6, 15), "tilt": (8, 18), "ear": (5, 12)}
        if idle_intervals:
            for name, bounds in idle_intervals.items():
                if name not in self._intervals or len(bounds) != 2 or not 0 < bounds[0] <= bounds[1]:
                    raise ValueError("Idle timing must name an existing channel with positive ordered bounds")
                self._intervals[name] = tuple(bounds)
        self._next = {name: random.uniform(*bounds) for name, bounds in self._intervals.items()}
        self._press = None
        self._dragged = False
        self._hovered = False
        self._drag_offset: QPoint | None = None
        self.setFixedSize(240, 400)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        from .pet_controls import PetControls
        self.controls = PetControls(self)
        self.badge = QToolButton(self)
        self.badge.setGeometry(195, 3, 36, 36)
        from PySide6.QtCore import QSize
        self.badge.setIconSize(QSize(36, 36))
        self.badge.setStyleSheet("QToolButton { background:transparent; border:none; } QToolButton:focus { border:2px solid #C9B4F4; border-radius:10px; }")
        self.badge.setAccessibleName("Unread task notifications")
        self.badge.setCursor(Qt.CursorShape.PointingHandCursor)
        self.badge.clicked.connect(self.controls.notification_requested.emit)
        self.set_notification_count(0)

        self._expression_timer = QTimer(self)
        self._expression_timer.setSingleShot(True)
        self._expression_timer.timeout.connect(lambda: self.set_state(PetState.IDLE))

        self._animation = QTimer(self)
        self._animation.setTimerType(Qt.TimerType.PreciseTimer)
        self._animation.timeout.connect(self._tick)
        self._animation.start(100 if self._reduced else 33)
        self._click_timer = QTimer(self)
        self._click_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._click_timer.setSingleShot(True)
        self._click_timer.timeout.connect(self._click)
        position = self.settings.value("position", QPoint(80, 80), type=QPoint)
        screen = next((screen for screen in QApplication.screens() if screen.availableGeometry().contains(position)), QApplication.primaryScreen())
        area = screen.availableGeometry()
        position = QPoint(max(area.left(), min(position.x(), area.right() - self.width() + 1)),
                          max(area.top(), min(position.y(), area.bottom() - self.height() + 1)))
        self.move(position)

    @property
    def state(self) -> PetState:
        return self._state

    @property
    def pet_kind(self) -> PetKind:
        return self._pet_kind

    def set_pet_kind(self, pet_kind: PetKind) -> None:
        if pet_kind == self._pet_kind:
            return
        self._pet_kind = pet_kind
        self.settings.setValue("pet", pet_kind.value)
        self.set_notification_count(self._notification_count)
        self.update()
        self.pet_kind_changed.emit(pet_kind)

    def set_state(self, state: PetState) -> None:
        self._expression_timer.stop()
        self._state = PetState(state)
        self._last_activity = self._state_started = time.monotonic()
        if self._state == PetState.HAPPY:
            self._reaction_at = time.monotonic() - self._clock
        self.setAccessibleName(f"PetLink companion · {self._state.value}")
        self.setToolTip(f"{self._state.value.title()} · Single click to type, double-click to open chat")
        self.update()

    def set_talking(self, talking: bool) -> None:
        self.set_state(PetState.TALKING if talking else PetState.IDLE)

    def set_speech_level(self, level: float | None):
        """Optional audio envelope from a future TTS player; None previews motion."""
        self._speech_level = None if level is None else max(0.0, min(1.0, level))
        self.update()

    def react(self, event: str):
        """Integration hook; call from Qt's UI thread when app events occur."""
        states = {"chat_opened": PetState.CURIOUS, "typing": PetState.CURIOUS,
                  "microphone_on": PetState.LISTENING, "thinking": PetState.THINKING,
                  "task_completed": PetState.HAPPY, "task_confirmed": PetState.HAPPY,
                  "reminder": PetState.REMINDER, "confused": PetState.CONFUSED,
                  "error": PetState.CONFUSED,
                  "finished": PetState.IDLE}
        self.set_state(states[event])
        if event in ("task_completed", "task_confirmed", "reminder", "confused", "error"):
            self._expression_timer.start(3200 if event == "reminder" else 2600)

    def _tick(self) -> None:
        t = time.monotonic() - self._clock
        for name, deadline in self._next.items():
            if t >= deadline:
                if name in ("blink", "wink", "ear"):
                    setattr(self, "_" + name + "_at", t)
                elif name == "glance":
                    self._glance = random.uniform(-4, 4)
                else:
                    self._tilt = random.uniform(-5, 5)
                self._next[name] = t + random.uniform(*self._intervals[name])
        if self._hovered:
            cursor = self.mapFromGlobal(QCursor.pos())
            target = QPointF(max(-4, min(4, (cursor.x() - 120) / 15)), max(-3, min(3, (cursor.y() - 100) / 20)))
        else:
            target = QPointF(self._glance, 0)
        if self._state == PetState.THINKING:
            target = QPointF(math.sin(t * .7) * 3, -3)
        elif self._state == PetState.LISTENING:
            target = QPointF(0, -1)
        elif self._state == PetState.SLEEPY:
            target = QPointF(0, 0)
        elif self._state == PetState.CONFUSED:
            target = QPointF(math.sin((t - (self._state_started-self._clock))*2)*2, -1)
        self._gaze += (target - self._gaze) * .12
        target_angle = self._gaze.x() if self._hovered else self._tilt
        if self._state == PetState.CURIOUS:
            target_angle = 7
        elif self._state == PetState.LISTENING:
            target_angle = -3
        if self._dragged:
            target_angle = 7
        self._angle += (target_angle - self._angle) * .08
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        from .character_art import paint_character
        t = time.monotonic() - self._clock
        blink_age = t - self._blink_at
        closure = max(0, 1 - abs(blink_age - .14) / .14)
        paint_character(
            painter, self._pet_kind.value, self._state.value, t,
            self._gaze, self._angle, closure, 0 <= t - self._wink_at < .5,
            t - self._ear_at, t - self._reaction_at,
            self._hovered, self._reduced,
            self._state == PetState.SLEEPY or (
                self._state == PetState.IDLE and time.monotonic() - self._last_activity > 120),
            self._speech_level,
            state_age=time.monotonic()-self._state_started,
        )
        painter.end()

    def _click(self):
        self._wink_at = time.monotonic() - self._clock
        self.clicked.emit()

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._press = event.globalPosition().toPoint()
            self._dragged = False
            self._last_activity = time.monotonic()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt API name
        self._last_activity = time.monotonic()
        if self._press is not None and event.buttons() & Qt.MouseButton.LeftButton:
            if (event.globalPosition().toPoint() - self._press).manhattanLength() >= QApplication.startDragDistance():
                self._dragged = True
                self._click_timer.stop()
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
                self.move(event.globalPosition().toPoint() - self._drag_offset)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if event.button() == Qt.MouseButton.LeftButton and self._press is not None:
            if self._dragged:
                self._reaction_at = time.monotonic() - self._clock
                area = self.screen().availableGeometry()
                self.move(max(area.left(), min(self.x(), area.right() - self.width() + 1)),
                          max(area.top(), min(self.y(), area.bottom() - self.height() + 1)))
                self.settings.setValue("position", self.pos())
            else:
                self._click_timer.start(QApplication.doubleClickInterval())
        self._press = None
        self._dragged = False
        self._drag_offset = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        self._click_timer.stop()
        self._reaction_at = time.monotonic() - self._clock
        self._press = None
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit()

    def set_notification_count(self, count):
        from .expressions import notification_icon
        self._notification_count = max(0, int(count))
        self.badge.setIcon(notification_icon(self._pet_kind.value))
        self.badge.setVisible(self._notification_count > 0)
        names = {PetKind.ANIME_AZURE: "Ishu's star", PetKind.ANIME_CORAL: "Coral's flower", PetKind.ANIMAL_CAT: "Lola's bell"}
        description = f"{names[self._pet_kind]} · {self._notification_count} unread task notification(s). Click to read."
        self.badge.setToolTip(description)
        self.badge.setAccessibleName(description)
        self.controls.bell.setToolTip(f"Read notifications · {self._notification_count} unread")

    def enterEvent(self, event) -> None:  # noqa: N802 - Qt API name
        self._hovered = True
        self._last_activity = time.monotonic()
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt API name
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def contextMenuEvent(self, event) -> None:  # noqa: N802 - Qt API name
        menu = QMenu(self)
        menu.addAction("Open chat", self.chat_requested.emit)
        menu.addAction("Voice setup", self.voice_setup_requested.emit)
        if self.tray_available:
            menu.addAction("Hide pet to tray", self.hide_requested.emit)
        menu.addSeparator()
        pets = menu.addMenu("Choose pet")
        group = QActionGroup(pets)
        group.setExclusive(True)
        labels = {
            PetKind.ANIME_CORAL: "Coral",
            PetKind.ANIME_AZURE: "Ishu",
            PetKind.ANIMAL_CAT: "Lola",
        }
        for kind, label in labels.items():
            action = pets.addAction(label)
            action.setCheckable(True)
            action.setChecked(kind == self._pet_kind)
            action.triggered.connect(lambda _checked=False, selected=kind: self.set_pet_kind(selected))
            group.addAction(action)
        menu.addSeparator()
        expressions = menu.addMenu("Preview expression")
        for state in PetState:
            expressions.addAction(state.value.title(), lambda selected=state: self.set_state(selected))
        reduced = menu.addAction("Reduced motion")
        reduced.setCheckable(True)
        reduced.setChecked(self._reduced)
        reduced.toggled.connect(self._set_reduced)
        menu.addAction("Exit", self.close)
        menu.exec(event.globalPos())

    def _set_reduced(self, enabled):
        self._reduced = enabled
        self.settings.setValue("reduced_motion", enabled)
        self._animation.setInterval(100 if enabled else 33)

    def closeEvent(self, event):
        self.quit_requested.emit()
        super().closeEvent(event)


def run() -> int:
    """Launch the standalone pet preview."""
    app = QApplication.instance() or QApplication([])
    from .chat_window import CompanionController
    app.setQuitOnLastWindowClosed(False)
    pet = PetWindow()
    from .database import Database
    from sqlalchemy.exc import SQLAlchemyError
    try:
        database = Database()
        controller = CompanionController(pet, database=database)
    except (OSError, SQLAlchemyError, RuntimeError) as error:
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.critical(None, "PetLink storage", "Could not open the local database. Check that your app-data folder is writable. Existing data has not been replaced.")
        return 1
    app.aboutToQuit.connect(database.close)
    pet.quit_requested.connect(app.quit)
    pet.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(run())
