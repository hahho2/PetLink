"""Contact sheet of actual Qt-rendered expressions; no model or user data."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QImage, QPainter
from PySide6.QtWidgets import QApplication
from petlink.character_art import paint_character
from petlink.expressions import notification_icon

app = QApplication.instance() or QApplication([])
font = Path("C:/Windows/Fonts/segoeui.ttf")
if font.exists():
    QFontDatabase.addApplicationFont(str(font))
states = ("thinking", "confused", "happy", "sleepy", "reminder")
sheet = QImage(240*len(states), 300*3, QImage.Format.Format_ARGB32)
sheet.fill(QColor("#242333"))
p = QPainter(sheet)
p.setRenderHint(QPainter.RenderHint.Antialiasing)
for row, (kind, name) in enumerate((("anime_azure", "Ishu"), ("anime_coral", "Coral"), ("animal_cat", "Lola"))):
    for col, state in enumerate(states):
        p.save()
        p.translate(col*240, row*300)
        p.setClipRect(0, 0, 240, 300)
        paint_character(p, kind, state, 3.5, QPointF(1,-1), 0, 0, False, 5, 9,
                        sleepy=state == "sleepy", state_age=.35)
        if state == "reminder":
            p.drawPixmap(195, 3, notification_icon(kind).pixmap(36,36))
        p.setFont(QFont("Segoe UI", 11))
        p.setPen(QColor("#F4EFFA"))
        p.drawText(0, 266, 240, 28, Qt.AlignmentFlag.AlignCenter, name+" · "+state.title())
        p.restore()
p.end()
sheet.save("expressions-preview.png")
