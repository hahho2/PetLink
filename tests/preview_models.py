"""Render model settings with dummy values; no network or saved credentials."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path
import tempfile
from types import SimpleNamespace
from PySide6.QtCore import QSettings
from PySide6.QtGui import QFontDatabase, QFont
from PySide6.QtWidgets import QApplication
from petlink.model_settings import ModelSettings, PROVIDERS

app = QApplication.instance() or QApplication([])
QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
app.setFont(QFont("Segoe UI", 10))
with tempfile.TemporaryDirectory() as folder:
    settings = QSettings(str(Path(folder) / "settings.ini"), QSettings.Format.IniFormat)
    current = dict(provider="openai", address=PROVIDERS["openai"][1],
        model="your-model-id", key="dummy-preview-key", consent=True, remember=False)
    dialog = ModelSettings(settings, current, store=SimpleNamespace(read=lambda provider: ""))
    dialog.show()
    app.processEvents()
    output = Path(__file__).resolve().parents[1] / "model-settings-preview.png"
    dialog.grab().save(str(output))
    dialog.hide()
    print(output)
