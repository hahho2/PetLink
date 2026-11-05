"""Render the real task-draft controls with disposable data, without inference."""
import os
import sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path
import tempfile
from PySide6.QtCore import QSettings
from PySide6.QtGui import QFontDatabase, QFont
from PySide6.QtWidgets import QApplication
from petlink.chat_window import ChatWindow
from petlink.database import Database

app = QApplication.instance() or QApplication([])
QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
app.setFont(QFont("Segoe UI", 10))
with tempfile.TemporaryDirectory() as folder:
    db = Database(Path(folder) / "preview.sqlite3")
    chat = ChatWindow(database=db, settings=QSettings(str(Path(folder) / "settings.ini"), QSettings.Format.IniFormat))
    chat.model.setText("my-local-model")
    chat.composer.setPlainText("Tomorrow solve 3 algebra questions")
    if "--followup" in sys.argv:
        chat._task_context = dict(date="2026-11-05", messages=[], action=None, pending=None,
            question="Which subject should these questions cover?")
        chat._update_task_context_label()
        chat.composer.setPlainText("Algebra")
    chat.resize(360, 640)
    chat.show()
    app.processEvents()
    app.processEvents()  # Let child form minimum sizes propagate to the window.
    output = Path(__file__).resolve().parents[1] / ("task-followup-preview.png" if "--followup" in sys.argv else "task-draft-preview.png")
    chat.grab().save(str(output))
    chat.shutdown()
    chat.hide()
    db.close()
    print(output)
