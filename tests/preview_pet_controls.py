"""Fixture-only rendering of the pet toolbar, typed draft and alert inbox."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from datetime import date
from pathlib import Path
import tempfile
from PySide6.QtCore import QSettings
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from petlink.database import Database
from petlink.chat_window import CompanionController
from petlink.pet_window import PetWindow

app = QApplication([])
font = Path("C:/Windows/Fonts/segoeui.ttf")
if font.exists():
    QFontDatabase.addApplicationFont(str(font))
with tempfile.TemporaryDirectory() as folder:
    db = Database(Path(folder) / "preview.sqlite3")
    values = dict(title="Read one chapter", description="", status="pending", priority="normal", due_date=date.today().isoformat())
    db.confirm(db.propose([dict(kind="create", values=values)]), 1)
    pet = PetWindow(settings=QSettings(str(Path(folder) / "preview.ini"), QSettings.Format.IniFormat))
    controller = CompanionController(pet, database=db)
    controller.check_notifications()
    while controller._notification_running:
        QTest.qWait(10)
    pet.controls.show_text("Help me plan my study session")
    pet.show()
    app.processEvents()
    pet.grab().save("pet-controls-preview.png")
    controller.show_notifications()
    app.processEvents()
    controller.notifications.grab().save("pet-notifications-preview.png")
    controller.stop_notifications()
    controller.voice.shutdown()
    controller.chat.shutdown()
    pet.hide()
    controller.notifications.hide()
    db.close()
