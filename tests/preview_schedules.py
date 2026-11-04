"""Render schedule form and occurrence completion preview from disposable data."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from datetime import datetime, timezone
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
    database = Database(Path(folder) / "preview.sqlite3")
    editor = TaskEditor(database)
    editor.title.setText("Read a chapter")
    editor.due.setText("2026-11-04")
    editor.frequency.setCurrentIndex(editor.frequency.findData("daily"))
    editor.reminder_time.setText("18:30")
    editor.show()
    app.processEvents()
    editor.grab().save("schedule-editor-preview.png")
    editor.submit()
    database.confirm(database.pending()[0]["id"], 1)
    database.poll_reminders(datetime(2026, 11, 5, 13, tzinfo=timezone.utc))
    window = TaskWindow(database)
    window.tabs.setCurrentIndex(2)
    window.show()
    app.processEvents()
    window.grab().save("occurrences-preview.png")
    window.occurrences.setCurrentRow(0)
    window.complete_occurrence()
    app.processEvents()
    window.grab().save("occurrence-confirm-preview.png")
    window.hide()
    editor.hide()
    database.close()
