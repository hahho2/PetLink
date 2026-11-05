import os
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
from pathlib import Path
import tempfile
from PySide6.QtCore import QSettings
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication
from petlink.chat_window import ChatWindow
from petlink.model_settings import ModelSettings
from petlink.chat_widgets import TaskDraftCard
from petlink.task_interpretation import direct_reminder
from petlink.database import Database

app=QApplication([])
QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
with tempfile.TemporaryDirectory() as folder:
    settings=QSettings(str(Path(folder)/"settings.ini"),QSettings.Format.IniFormat)
    for key,value in {"provider":"local","local/model":"qwen3.5:2b-q4_K_M","local/address":"http://127.0.0.1:11434","local/skip_thinking":True}.items():
        settings.setValue("models/"+key,value)
    db=Database(Path(folder)/"preview.sqlite3")
    chat=ChatWindow(database=db,settings=settings)
    chat.welcome.parentWidget().hide()
    chat._bubble("You","Create a task to do some workout tomorrow at 13:00")
    chat._bubble("Ishu","Your workout draft is ready. Check the details, then confirm when you’re ready.")
    action=direct_reminder("create a task to do some workout tomorrow at 13:00")
    card=TaskDraftCard(action)
    chat.message_layout.insertWidget(chat.message_layout.count()-1,card)
    chat.resize(620,900)
    chat.show()
    app.processEvents();app.processEvents()
    chat.grab().save("redesign-desktop.png")
    chat.resize(380,760)
    app.processEvents();app.processEvents()
    chat.grab().save("redesign-narrow.png")
    dialog=ModelSettings(settings,chat.connection)
    dialog.show()
    app.processEvents();app.processEvents()
    dialog.grab().save("redesign-settings.png")
    dialog.reject()
    chat.shutdown();chat.hide();db.close()
