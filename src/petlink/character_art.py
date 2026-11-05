"""Cached PNG layers and lightweight Qt facial animation; no inference required."""
from functools import lru_cache
import math
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QPolygonF
from .expressions import paint_effects, pose, sleep_bubble

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
                    reaction_age, hovered=False, reduced=False, sleepy=False, speech_level=None,
                    state_age=None):
    head, body, accessory, limb = layers(kind)
    cat, coral = kind == "animal_cat", kind == "anime_coral"
    transient = 0 <= reaction_age < 1.6 and state in ("idle", "curious") and not sleepy
    effective = "sleepy" if sleepy else ("happy" if transient else state)
    age = reaction_age if transient else (t if state_age is None else state_age)
    movement = pose(kind, effective, age, t, reduced)
    motion = 0 if reduced else 1
    happy, sleeping = effective == "happy", effective == "sleepy"
    p.save()
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    # Leave room for hops and symbols inside the existing 240px pet surface.
    p.translate(120, 250)
    p.scale(.88, .88)
    p.translate(-120, -250)
    breathing = math.sin(t * (.7 if sleeping else 1.6))
    p.translate(math.sin(t * .8) * motion, (-breathing - movement["jump"] + movement["crouch"]) * motion)
    p.translate(120, 230)
    p.scale(1 + (1-movement["squash"])*.5, movement["squash"])
    p.translate(-120, -230)
    if cat:
        tail_speed = .5 if sleeping else (7 if happy else 1.2)
        tail_angle = math.sin(t * tail_speed) * (16 if happy else 6) * motion
        draw_part(p, limb, QRectF(145, 154 if sleeping else 152, 80, 95), tail_angle)
    draw_part(p, body, QRectF(57, 155, 126 + breathing*.8*motion, 102 + breathing*.8*motion))
    for side in (-1, 1):
        wave = movement["wave"]
        arm_y = 192 - (abs(wave) if happy or effective == "reminder" else 0)
        if coral and happy:
            arm_y = 169 + wave*.2
        if sleeping:
            arm_y = 204
        if cat:
            p.setPen(QPen(QColor("#47425E"), 2))
            p.setBrush(QColor("#363B59"))
            paw_y = arm_y - (5 if side == -1 and effective in ("happy", "reminder", "listening") else 0)
            p.drawEllipse(QRectF(120+side*49-10, paw_y, 21, 28))
            if effective in ("happy", "reminder") and side == -1:
                p.setBrush(QColor("#EDA6BC"))
                p.drawEllipse(QRectF(120+side*49-5, paw_y+12, 11, 10))
                for x in (-4, 1, 6):
                    p.drawEllipse(QRectF(120+side*49+x-2, paw_y+4, 3, 4))
        else:
            draw_part(p, limb, QRectF(120+side*(45 if coral and happy else 54)-14, arm_y-7, 28, 40),
                      wave * side if not sleeping else side*15)
    p.save()
    p.translate(120, 120)
    p.rotate((0 if sleeping else angle)*motion + movement["lean"])
    p.translate(-120, -120)
    if cat:
        for index, x in enumerate((37, 142)):
            ear = cat_ears()[index]
            ear_phase = ear_age - index*.5
            twitch = math.sin(ear_phase*20)*8 if 0 <= ear_phase < .4 and not sleeping else 0
            resting = (26 if index == 0 else -26) if sleeping else 0
            if effective == "confused":
                resting = 22 if index == 0 else -8
            elif effective == "listening":
                resting = -8 if index == 0 else 8
            draw_part(p, ear, QRectF(x, 0, 63, 97), (twitch+resting)*motion)
    draw_part(p, head, QRectF(19, 30, 202, 170) if cat else QRectF(19, 15, 202, 181))
    ink = QColor("#503750")
    iris = "#B78739" if cat else ("#389D91" if coral else "#9563CF")
    for side in (-1, 1):
        x, y = 120+side*29, 121
        openness = 0 if sleeping else 1-blink
        if wink and side == -1 and effective not in ("sleepy", "thinking", "confused", "listening"):
            openness = 0
        if happy:
            openness = 0
        p.setPen(QPen(ink, 2.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        if openness < .18:
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawArc(QRectF(x-13, y-5, 26, 12), (200 if sleeping else 15)*16, (140 if sleeping else 150)*16)
            if sleeping and not cat:
                p.drawLine(QPointF(x+10, y+4), QPointF(x+14, y+7))
        else:
            widen = 1.13 if effective == "curious" else (1.12 if side == -1 else .82) if effective == "confused" else 1
            h = (38 if coral else 42 if cat else 44)*openness*widen
            w = 30 if cat else 26 if coral else 28
            eye = QPainterPath()
            eye.addEllipse(QRectF(x-w/2, y-h/2, w, h))
            p.setBrush(QColor("#FFF9FA"))
            p.drawPath(eye)
            p.save()
            p.setClipPath(eye)
            gx = gaze.x() + (-2 if effective == "thinking" else 0)
            gy = gaze.y() - (2 if effective in ("thinking", "curious") else 0)
            gradient = QLinearGradient(x, y-h/2, x, y+h/2)
            gradient.setColorAt(0, QColor("#302745"))
            gradient.setColorAt(.65, QColor(iris))
            gradient.setColorAt(1, QColor("#F5E1FF" if not cat else "#FFE296"))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(gradient)
            p.drawEllipse(QRectF(x-11+gx, y-h*.43+gy, 22, h*.9))
            p.setBrush(QColor("#302745"))
            p.drawEllipse(QRectF(x-5+gx, y-h*.32+gy, 10, h*.65))
            p.setBrush(QColor("#FFFFFF"))
            p.drawEllipse(QRectF(x-9+gx, y-h*.4+gy, 10, h*.28))
            p.drawEllipse(QRectF(x+3+gx, y+h*.15, 5, 5))
            p.restore()
        blush = QColor("#F49EB6")
        blush.setAlpha(185 if happy else 120 if hovered or effective == "curious" else 65)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(blush)
        p.drawEllipse(QRectF(x-14, y+21, 28, 9))
        if effective in ("thinking", "curious", "confused", "listening"):
            p.setPen(QPen(ink, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            lift = -4 if effective == "confused" and side == -1 else 1
            p.drawLine(QPointF(x-10, y-29+lift), QPointF(x+8, y-31-lift))
    p.setPen(QPen(ink, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.setBrush(Qt.BrushStyle.NoBrush)
    if effective == "talking" or (happy and not cat):
        level = speech_level if speech_level is not None else (.4 if reduced else (math.sin(t*17)+1)/2)
        width = 14 if coral or cat else 20
        p.setBrush(QColor("#C56583"))
        p.drawEllipse(QRectF(120-width/2, 143, width, 6+(level*11 if effective == "talking" else (7 if coral else 11))))
    elif effective == "confused":
        p.drawPolyline(QPolygonF([QPointF(111,150), QPointF(117,147), QPointF(123,151), QPointF(129,148)]))
    elif effective in ("thinking", "curious"):
        p.setBrush(QColor("#C56583"))
        p.drawEllipse(QRectF(119 if coral else 127, 145, 5, 6))
    elif cat and not sleeping:
        p.drawArc(QRectF(108,141,12,13), 185*16, 170*16)
        p.drawArc(QRectF(120,141,12,13), 185*16, 170*16)
    else:
        p.drawArc(QRectF(110,140,16 if sleeping else 20,10), 185*16,170*16)
    if cat:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#DE9BAB"))
        p.drawEllipse(QRectF(117,135,6,4))
        p.setPen(QPen(ink,1.4,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap))
        for side in (-1,1):
            p.drawLine(QPointF(120+side*43,138),QPointF(120+side*57,135))
            p.drawLine(QPointF(120+side*43,144),QPointF(120+side*57,148))
    if sleeping:
        sleep_bubble(p, kind, t, reduced)
    p.restore()
    paint_effects(p, kind, effective, age, t, reduced)
    p.restore()
