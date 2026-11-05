"""Character-specific motion and vector expression symbols, independent of AI."""
from functools import lru_cache
import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF

PROFILES = {
    "anime_azure": dict(accent="#B6DFFF", highlight="#D4BBFF", hop=17, rhythm=2.0, tilt=4),
    "anime_coral": dict(accent="#FFC0D4", highlight="#BEEBD5", hop=8, rhythm=1.5, tilt=7),
    "animal_cat": dict(accent="#FFDA83", highlight="#CDEBF6", hop=13, rhythm=2.5, tilt=5),
}
INK = "#514267"


def pose(kind, state, age, t, reduced=False):
    profile = PROFILES[kind]
    motion = 0 if reduced else 1
    happy = state == "happy"
    # Two cheerful hops, then settle; an expressive preview need not bounce forever.
    jump = abs(math.sin(age * math.pi * profile["rhythm"])) * max(0, 1 - age / 2) if happy and age < 2 else 0
    sleep = state == "sleepy"
    lean = math.sin(t * .8) * .7
    if state == "confused":
        lean = math.sin(age * 3) * profile["tilt"]
    elif state == "curious":
        lean = profile["tilt"]
    elif state == "thinking":
        lean = -profile["tilt"] * .5
    elif sleep:
        lean = 6 if kind == "anime_coral" else -4
    return dict(jump=profile["hop"] * jump * motion,
                lean=lean * motion,
                crouch=(4 if sleep else 0) * motion,
                squash=(1 - jump * .06) if motion else 1,
                wave=(math.sin(age * 6) * (15 if kind == "anime_azure" else 10)
                      if state in ("happy", "reminder") else math.sin(t) * 1.5) * motion)


def star(p, x, y, radius, fill, points=5):
    vertices = [QPointF(x + math.sin(i * math.pi / points) * radius * (1 if i % 2 == 0 else .45),
                       y - math.cos(i * math.pi / points) * radius * (1 if i % 2 == 0 else .45)) for i in range(points * 2)]
    p.setBrush(QColor(fill))
    p.drawPolygon(QPolygonF(vertices))


def heart(p, x, y, size, fill):
    path = QPainterPath(QPointF(x, y + size))
    path.cubicTo(x-size*2, y, x-size, y-size, x, y-size*.25)
    path.cubicTo(x+size, y-size, x+size*2, y, x, y+size)
    p.setBrush(QColor(fill))
    p.drawPath(path)


def glyph(p, text, x, y, size, color):
    font = QFont("Segoe UI", size)
    font.setBold(True)
    path = QPainterPath()
    path.addText(QPointF(x, y), font, text)
    p.setPen(QPen(QColor(INK), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    p.setBrush(QColor(color))
    p.drawPath(path)


def sleep_bubble(p, kind, t, reduced=False):
    """Nose tether and translucent bubble stay attached to the head layer."""
    radius = (9 if kind == "anime_coral" else 12) + (0 if reduced else math.sin(t * 1.5) * 2)
    p.setPen(QPen(QColor(PROFILES[kind]["accent"]), 1.7))
    p.drawLine(QPointF(123, 142), QPointF(133, 144))
    fill = QColor(PROFILES[kind]["highlight"])
    fill.setAlpha(165)
    p.setBrush(fill)
    p.drawEllipse(QRectF(140-radius, 144-radius, radius*2, radius*2))
    p.setPen(QPen(QColor("#FFFFFF"), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.drawArc(QRectF(140-radius+3, 144-radius+3, radius*1.3, radius*1.3), 40*16, 80*16)


def paint_effects(p, kind, state, age, t, reduced=False):
    profile = PROFILES[kind]
    float_y = 0 if reduced else math.sin(t * 1.4) * 2
    p.save()
    p.setPen(QPen(QColor(INK), 1.6))
    if state == "sleepy":
        # Each pet's dream has its own color and placement; no emoji font required.
        for i, letter in enumerate(("z", "z", "Z")):
            glyph(p, letter, 13+i*12, 76-i*17+float_y, 11+i*3, profile["accent"])
        if kind == "anime_coral":
            heart(p, 37, 17+float_y, 5, profile["highlight"])
    elif state == "thinking":
        p.setBrush(QColor("#FFF7FF"))
        for x, y, r in ((64, 86, 2), (57, 76, 4)):
            p.drawEllipse(QRectF(x-r, y-r, r*2, r*2))
        cloud = QPainterPath()
        cloud.setFillRule(Qt.FillRule.WindingFill)
        for x, y, w, h in ((8, 35, 34, 26), (23, 26, 31, 31), (39, 36, 25, 24), (20, 43, 32, 23)):
            cloud.addEllipse(QRectF(x, y+float_y, w, h))
        p.drawPath(cloud.simplified())
        if kind == "animal_cat":
            p.setBrush(QColor(profile["accent"]))
            p.drawEllipse(QRectF(26, 39+float_y, 23, 13))
            p.drawPolygon(QPolygonF([QPointF(26,45+float_y), QPointF(19,39+float_y), QPointF(19,52+float_y)]))
            p.setBrush(QColor(INK))
            p.drawEllipse(QRectF(42, 42+float_y, 2.5, 2.5))
        elif kind == "anime_coral":
            heart(p, 36, 45+float_y, 7, profile["accent"])
        else:
            p.setPen(Qt.PenStyle.NoPen)
            active = int(age * 2) % 3 if not reduced else 1
            for i in range(3):
                p.setBrush(QColor(profile["highlight"] if i == active else INK))
                p.drawEllipse(QRectF(23+i*11, 44+float_y, 5, 5))
    elif state in ("confused", "curious"):
        glyph(p, "??" if state == "confused" and kind == "anime_azure" else "?", 15, 64+float_y,
              24 if state == "confused" else 18, profile["accent"])
        if state == "confused" and kind == "anime_coral":
            drop = QPainterPath(QPointF(204, 85))
            drop.cubicTo(190, 99, 216, 105, 204, 85)
            p.setBrush(QColor("#B6DFFF"))
            p.drawPath(drop)
        elif state == "confused" and kind == "animal_cat":
            p.setPen(QPen(QColor(profile["accent"]), 2))
            p.drawPolyline(QPolygonF([QPointF(199,55), QPointF(206,61), QPointF(200,66), QPointF(208,72)]))
    elif state == "happy":
        if kind == "anime_coral":
            heart(p, 34, 68+float_y, 8, profile["accent"])
            heart(p, 204, 100-float_y, 5, profile["accent"])
        else:
            star(p, 31, 65+float_y, 10, profile["accent"])
            star(p, 207, 91-float_y, 6, profile["highlight"])
            if kind == "animal_cat":
                for x in (22, 31, 40):
                    p.setBrush(QColor("#F7B8C9"))
                    p.drawEllipse(QRectF(x, 89+float_y, 4, 6))
    elif state in ("listening", "talking"):
        p.setPen(QPen(QColor(profile["accent"]), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        for i in range(3):
            height = 7 + (i % 2)*7 + (0 if reduced else math.sin(t*5+i)*3)
            p.drawLine(QPointF(20+i*7, 92-height/2), QPointF(20+i*7, 92+height/2))
    elif state == "reminder":
        p.drawPixmap(15, 46, 32, 32, notification_icon(kind).pixmap(36, 36))
    p.restore()


@lru_cache(maxsize=3)
def notification_icon(kind):
    pixmap = QPixmap(36, 36)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor(INK), 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    if kind == "animal_cat":
        p.setBrush(QColor("#FFD166"))
        bell = QPainterPath(QPointF(7, 26))
        bell.cubicTo(12, 23, 8, 8, 18, 8)
        bell.cubicTo(28, 8, 24, 23, 29, 26)
        bell.closeSubpath()
        p.drawPath(bell)
        p.drawEllipse(QRectF(15, 26, 6, 6))
        p.drawEllipse(QRectF(16, 4, 4, 5))
        p.drawLine(4, 11, 3, 18)
        p.drawLine(32, 11, 33, 18)
    else:
        if kind == "anime_coral":
            p.setBrush(QColor("#FFB8D0"))
            for i in range(5):
                a = i * math.tau / 5
                p.drawEllipse(QRectF(18+math.sin(a)*9-7, 18-math.cos(a)*9-7, 14, 14))
            p.setBrush(QColor("#FFE9AD"))
            p.drawEllipse(QRectF(9,9,18,18))
        else:
            star(p, 18, 18, 16, "#FFD166")
        p.setPen(QPen(QColor(INK), 2.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(18, 11, 18, 20)
        p.setBrush(QColor(INK))
        p.drawEllipse(QRectF(17,24,2,2))
    p.end()
    return QIcon(pixmap)
