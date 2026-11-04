"""Cached PNG layers and lightweight Qt facial animation; no inference required."""
from functools import lru_cache
import math
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter, QPen, QPixmap

ASSETS = Path(__file__).parent / "assets"
NAMES = {"anime_azure": "ishu", "anime_coral": "coral", "animal_cat": "lola"}


def trim(tile):
    """Find substantial artwork, ignoring isolated generation-edge speckles."""
    image = tile.convertToFormat(QImage.Format.Format_RGBA8888)
    data = image.constBits()
    stride = image.bytesPerLine()
    step = 3
    points = {(x, y) for y in range(0, image.height(), step)
              for x in range(0, image.width(), step) if data[y * stride + x * 4 + 3] > 180}
    groups = []
    while points:
        start = points.pop()
        group, todo = [start], [start]
        while todo:
            x, y = todo.pop()
            for neighbor in ((x-step,y), (x+step,y), (x,y-step), (x,y+step)):
                if neighbor in points:
                    points.remove(neighbor)
                    group.append(neighbor)
                    todo.append(neighbor)
        groups.append(group)
    largest = max(map(len, groups), default=0)
    substantial = [point for group in groups if len(group) >= max(8, largest * .12) for point in group]
    if not substantial:
        raise RuntimeError("Character layer contains no visible artwork")
    xs, ys = zip(*substantial)
    left, top = max(0, min(xs)-6), max(0, min(ys)-6)
    return QPixmap.fromImage(tile.copy(left, top, min(tile.width(), max(xs)+9)-left,
                                     min(tile.height(), max(ys)+9)-top))


@lru_cache(maxsize=3)
def layers(kind):
    image = QImage(str(ASSETS / (NAMES[kind] + ".png")))
    if image.isNull():
        raise RuntimeError(f"Missing character artwork: {NAMES[kind]}")
    parts = []
    split = int(image.height() * .56)
    for row in range(2):
        for col in range(2):
            top, bottom = (0, split) if row == 0 else (split, image.height())
            tile = image.copy(col * image.width() // 2, top, image.width() // 2, bottom-top)
            # Trim transparent margins once at load, never inside the frame loop.
            parts.append(trim(tile))
    return tuple(parts)


def draw_part(p, pixmap, rect, angle=0):
    fitted = pixmap.size().scaled(rect.size().toSize(), Qt.AspectRatioMode.KeepAspectRatio)
    target = QRectF(0, 0, fitted.width(), fitted.height())
    target.moveCenter(rect.center())
    p.save()
    p.translate(rect.center())
    p.rotate(angle)
    p.translate(-rect.center())
    p.drawPixmap(target, pixmap, QRectF(pixmap.rect()))
    p.restore()


@lru_cache(maxsize=1)
def cat_ears():
    ears = layers("animal_cat")[2]
    return tuple(trim(ears.toImage().copy(i * ears.width() // 2, 0,
                                        ears.width() // 2, ears.height())) for i in (0, 1))


def paint_character(p: QPainter, kind, state, t, gaze, angle, blink, wink, ear_age,
                    reaction_age, hovered=False, reduced=False, sleepy=False, speech_level=None):
    head, body, accessory, limb = layers(kind)
    cat = kind == "animal_cat"
    coral = kind == "anime_coral"
    motion = 0 if reduced else 1
    happy = state == "happy" or 0 <= reaction_age < 1.6
    bounce = math.sin(reaction_age * 10) * math.exp(-reaction_age * 3) * 9 if 0 <= reaction_age < 1.6 else 0
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    p.translate(math.sin(t * .8) * motion, (-math.sin(t * 1.6) * 1.2 - bounce) * motion)
    if cat:
        draw_part(p, limb, QRectF(145, 152, 80, 95), math.sin(t * 1.2) * 9 * motion)
    draw_part(p, body, QRectF(57, 155, 126, 102))
    wave = math.sin(t * 5) * 14 if happy or state == "listening" else math.sin(t) * 2
    for side in (-1, 1):
        p.save()
        if cat:
            p.setPen(QPen(QColor("#47425E"), 2))
            p.setBrush(QColor("#363B59"))
            p.drawEllipse(QRectF(120 + side * 49 - 10, 192 - (wave if side == -1 else 0) * motion, 21, 28))
            if happy:
                p.setBrush(QColor("#EDA6BC"))
                p.drawEllipse(QRectF(120 + side * 49 - 5, 204 - (wave if side == -1 else 0) * motion, 11, 10))
        else:
            draw_part(p, limb, QRectF(120 + side * 54 - 14, 185, 28, 40), wave * side * motion)
        p.restore()
    p.save()
    p.translate(120, 120)
    p.rotate(angle * motion)
    p.translate(-120, -120)
    if cat:
        for index, x in enumerate((37, 142)):
            ear = cat_ears()[index]
            age = ear_age - index * .5
            twitch = math.sin(age * 20) * 8 if 0 <= age < .4 else 0
            draw_part(p, ear, QRectF(x, 0, 63, 97), (twitch + (10 if sleepy else 0)) * motion)
    draw_part(p, head, QRectF(19, 30, 202, 170) if cat else QRectF(19, 15, 202, 181))
    ink = QColor("#503750")
    iris = "#B78739" if cat else ("#389D91" if coral else "#9563CF")
    # Face layers are painted independently onto the deliberately blank head art.
    for side in (-1, 1):
        x, y = 120 + side * 29, 121
        openness = .15 if sleepy else 1 - blink
        if wink and side == -1:
            openness = 0
        if state == "happy":
            openness = 0
        p.setPen(QPen(ink, 2.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        if openness < .18:
            p.drawArc(QRectF(x - 13, y - 5, 26, 12), 15 * 16, 150 * 16)
        else:
            p.setBrush(QColor("#FFF9FA"))
            p.drawEllipse(QRectF(x - 14, y - 21 * openness, 28, 40 * openness))
            gradient = QLinearGradient(x, y - 20, x, y + 20)
            gradient.setColorAt(0, QColor("#302745"))
            gradient.setColorAt(.65, QColor(iris))
            gradient.setColorAt(1, QColor("#F5E1FF" if not cat else "#FFE296"))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(gradient)
            p.drawEllipse(QRectF(x - 11 + gaze.x(), y - 17 * openness + gaze.y(), 22, 34 * openness))
            p.setBrush(QColor("#302745"))
            p.drawEllipse(QRectF(x - 5 + gaze.x(), y - 13 * openness, 10, 24 * openness))
            p.setBrush(QColor("#FFFFFF"))
            p.drawEllipse(QRectF(x - 9 + gaze.x(), y - 16 * openness, 10, 11 * openness))
            p.drawEllipse(QRectF(x + 3 + gaze.x(), y + 6 * openness, 5, 5))
        blush = QColor("#F49EB6")
        blush.setAlpha(130 if happy or hovered else 65)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(blush)
        p.drawEllipse(QRectF(x - 14, y + 21, 28, 9))
        if state in ("thinking", "curious", "listening"):
            p.setPen(QPen(ink, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawLine(QPointF(x - 10, y - 29), QPointF(x + 8, y - 31))
    p.setPen(QPen(ink, 2))
    if state == "talking" or happy:
        level = speech_level if speech_level is not None else (math.sin(t * 17) + 1) / 2
        p.setBrush(QColor("#C56583"))
        p.drawEllipse(QRectF(110, 143, 20, 6 + (level * 11 if state == "talking" else 9)))
    else:
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(QRectF(110, 140, 20, 12), 185 * 16, 170 * 16)
    p.restore()
