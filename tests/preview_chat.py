"""Offline UI snapshot; no model request is made."""
import os
import tempfile
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path
from PySide6.QtCore import QSettings
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication
from petlink.chat_window import ChatWindow

app = QApplication([])
font = Path("C:/Windows/Fonts/segoeui.ttf")
if font.exists():
    QFontDatabase.addApplicationFont(str(font))
folder = tempfile.TemporaryDirectory()
chat = ChatWindow(settings=QSettings(str(Path(folder.name) / "settings.ini"), QSettings.Format.IniFormat))
chat.show()
app.processEvents()
chat.grab().save("chat-preview.png")
chat.resize(360, 560)
app.processEvents()
chat.grab().save("chat-preview-narrow.png")
chat.hide()
