"""Small keyboard-accessible controls painted beneath the companion."""
from .ui_theme import COLORS, stylesheet
from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QToolButton


def icon(kind):
    pix = QPixmap(28, 28)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor(COLORS["text"]), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    if kind == "mic":
        p.drawRoundedRect(QRectF(11, 4, 6, 13), 3, 3)
        p.drawArc(QRectF(7, 8, 14, 14), 180*16, 180*16)
        p.drawLine(14, 22, 14, 25)
        p.drawLine(10, 25, 18, 25)
    elif kind == "write":
        p.drawLine(7, 21, 20, 6)
        p.drawLine(10, 23, 23, 8)
        p.drawLine(7, 21, 6, 25)
        p.drawLine(6, 25, 10, 23)
    else:
        p.drawArc(QRectF(7, 5, 14, 17), 0, 180*16)
        p.drawLine(7, 13, 6, 21)
        p.drawLine(21, 13, 22, 21)
        p.drawLine(6, 21, 22, 21)
        p.drawArc(QRectF(12, 22, 4, 4), 180*16, 180*16)
    p.end()
    return QIcon(pix)


class PetControls(QFrame):
    voice_requested = Signal()
    notification_requested = Signal()
    submit = Signal(str)
    draft_changed = Signal(str)

    def __init__(self, pet):
        super().__init__(pet)
        self.setGeometry(0, 268, 240, 132)
        self.setStyleSheet(stylesheet() + f"QLabel {{ background:{COLORS['surface']}; border-radius:7px; padding:3px; font-size:11px; }}")
        row = QFrame(self)
        row.setGeometry(42, 0, 156, 40)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        self.write = self.button("write", "Type a command")
        self.mic = self.button("mic", "Start voice input; click again to stop")
        self.bell = self.button("bell", "Read pet notifications")
        for button in (self.write, self.mic, self.bell):
            layout.addWidget(button)
        self.write.clicked.connect(self.toggle_editor)
        self.mic.clicked.connect(self.voice_requested.emit)
        self.bell.clicked.connect(self.notification_requested.emit)
        self.editor = QFrame(self)
        self.editor.setGeometry(5, 46, 230, 40)
        edit_layout = QHBoxLayout(self.editor)
        edit_layout.setContentsMargins(0, 0, 0, 0)
        self.input = QLineEdit()
        self.input.setMaxLength(6000)
        self.input.setPlaceholderText("Write a command…")
        self.input.setAccessibleName("Quick command")
        send = QToolButton()
        send.setText("→")
        send.setAccessibleName("Send quick command to chat")
        send.setToolTip("Send to chat")
        send.setFixedSize(34, 34)
        edit_layout.addWidget(self.input)
        edit_layout.addWidget(send)
        send.clicked.connect(self.send)
        self.input.returnPressed.connect(self.send)
        self.input.textChanged.connect(self.draft_changed.emit)
        self.editor.hide()
        self.feedback = QLabel(self)
        self.feedback.setGeometry(5, 90, 230, 40)
        self.feedback.setWordWrap(True)
        self.feedback.setTextFormat(Qt.TextFormat.PlainText)
        self.feedback.hide()

    def button(self, kind, text):
        button = QToolButton()
        button.setFixedSize(38, 38)
        button.setIcon(icon(kind))
        button.setToolTip(text)
        button.setAccessibleName(text)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        return button

    def toggle_editor(self):
        self.editor.setVisible(not self.editor.isVisible())
        if self.editor.isVisible():
            self.input.setFocus()

    def show_text(self, text):
        self.editor.show()
        self.input.setText(text)
        self.input.setFocus()

    def send(self):
        if self.input.text().strip():
            self.submit.emit(self.input.text().strip())

    def message(self, text):
        self.feedback.setText(text)
        self.feedback.setToolTip(text.replace("<", "&lt;").replace(">", "&gt;"))
        self.feedback.setVisible(bool(text))
