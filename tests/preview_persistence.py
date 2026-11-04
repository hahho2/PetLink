"""Render fixture-only task screens; never touch the user's app-data database."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path
import tempfile
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication
from petlink.database import Database
from petlink.task_window import TaskEditor, TaskWindow

app = QApplication([])
font = Path("C:/Windows/Fonts/segoeui.ttf")
if font.exists():
    QFontDatabase.addApplicationFont(str(font))
with tempfile.TemporaryDirectory() as folder:
    db = Database(Path(folder) / "preview.sqlite3")
    editor = TaskEditor(db)
    editor.title.setText("Read one chapter")
    editor.description.setPlainText("A quiet 25-minute study session.")
    editor.due.setText("2026-11-05")
    editor.show()
    app.processEvents()
    editor.grab().save("task-editor-preview.png")
    editor.submit()
    tasks = TaskWindow(db)
    tasks.show()
    tasks.tabs.setCurrentIndex(1)
    tasks.pending.setCurrentRow(0)
    app.processEvents()
    tasks.grab().save("tasks-pending-preview.png")
    tasks.resize(390, 570)
    app.processEvents()
    tasks.grab().save("tasks-narrow-preview.png")
    tasks.hide()
    editor.hide()
    db.close()
