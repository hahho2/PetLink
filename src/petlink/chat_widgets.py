"""Small native chat components sharing PetLink's visual language."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QGridLayout, QLabel, QPushButton, QVBoxLayout
from .ui_theme import COLORS


class WrappedMessage(QLabel):
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.setMinimumHeight(max(20,self.heightForWidth(max(80,event.size().width()))))

    def setText(self, text):
        super().setText(text)
        self.setMinimumHeight(max(20,self.heightForWidth(max(80,self.width()))))


class MessageBubble(QFrame):
    def __init__(self, speaker, text, parent=None):
        super().__init__(parent)
        self.setMaximumWidth(720)
        self.setObjectName("userBubble" if speaker == "You" else "assistantBubble")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        heading = QHBoxLayout()
        name = QLabel(speaker)
        name.setObjectName("speaker")
        heading.addWidget(name, 1)
        copy = QPushButton("Copy")
        copy.setObjectName("quiet")
        copy.setAccessibleName(f"Copy {speaker} message")
        heading.addWidget(copy)
        layout.addLayout(heading)
        self.text = WrappedMessage(text)
        self.text.setTextFormat(Qt.TextFormat.PlainText)
        self.text.setWordWrap(True)
        self.text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard)
        self.text.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.text.setAccessibleName(speaker + " message")
        copy.clicked.connect(lambda: QApplication.clipboard().setText(self.text.text()))
        layout.addWidget(self.text)


class StatusText(QLabel):
    changed = Signal(str)

    def setText(self, text):
        super().setText(text)
        self.changed.emit(text)


class Feedback(QFrame):
    def __init__(self, text, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        row = QHBoxLayout()
        self.summary = QLabel()
        self.summary.setTextFormat(Qt.TextFormat.PlainText)
        self.summary.setWordWrap(True)
        self.summary.setObjectName("muted")
        self.details = QPushButton("Details")
        self.details.setCheckable(True)
        self.details.setObjectName("quiet")
        row.addWidget(self.summary,1)
        row.addWidget(self.details)
        layout.addLayout(row)
        self.full = StatusText()
        self.full.setWordWrap(True)
        self.full.hide()
        layout.addWidget(self.full)
        self.details.toggled.connect(self.full.setVisible)
        self.full.changed.connect(self.update_text)
        self.full.setText(text)

    def update_text(self, text):
        error = any(word in text for word in ("did not finish", "no answer", "Could not", "Cannot reach", "failed"))
        self.summary.setStyleSheet(f"color:{COLORS['error']};" if error else "")
        if "did not finish" in text or "no answer text" in text:
            summary = "No complete answer received. Retry, or check your model in Settings."
        elif "Could not save" in text:
            summary = "Could not save your changes. Keep this window open and retry."
        else:
            summary = text if len(text)<140 else text.split(". ")[0]+"."
        self.summary.setText(("Error · " if error else "") + summary)
        self.details.setVisible(summary != text)


class TaskDraftCard(QFrame):
    edit_requested = Signal()
    pending_requested = Signal()
    confirm_requested = Signal()
    cancel_requested = Signal()

    def __init__(self, action, parent=None):
        super().__init__(parent)
        self.setObjectName("draftCard")
        values = action["values"]
        layout = QVBoxLayout(self)
        eyebrow = QLabel("TASK DRAFT · Not active yet")
        eyebrow.setObjectName("muted")
        layout.addWidget(eyebrow)
        title = QLabel(values["title"])
        title.setTextFormat(Qt.TextFormat.PlainText)
        title.setWordWrap(True)
        title.setObjectName("cardTitle")
        layout.addWidget(title)
        schedule = values["schedule"]
        from .task_window import summary
        detail = QLabel("\n".join(summary([action]).splitlines()[1:]))
        detail.setTextFormat(Qt.TextFormat.PlainText)
        detail.setWordWrap(True)
        layout.addWidget(detail)
        actions = QGridLayout()
        for i,(label, signal) in enumerate((("Edit", self.edit_requested), ("Confirm", self.confirm_requested), ("Save as Pending", self.pending_requested), ("Cancel", self.cancel_requested))):
            button = QPushButton(label)
            if signal == self.confirm_requested:
                button.setObjectName("primary")
            button.clicked.connect(signal.emit)
            actions.addWidget(button,i//2,i%2)
        layout.addLayout(actions)
