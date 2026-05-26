"""Monochrome vector (line-art) icons drawn with QPainter.

Replaces the emoji glyphs in the UI with crisp, theme-coloured line icons that
match the HUD aesthetic. Every icon is drawn inside a unit box (0..1) and scaled
to the requested rect/size, so it stays sharp at any resolution and takes the
colour it's given.

Usage:
    icons.paint_icon(painter, "mic", QRectF(...), "#00d4ff")   # into a painter
    btn.setIcon(icons.make_icon("mic_off", "#ff4444", 18))     # for a QPushButton
    label.setPixmap(icons.make_pixmap("audio", "#cc44ff", 40)) # for a QLabel
"""
from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (
    QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF,
)

# Category/concept -> drawing key, so callers can use friendly names.
_ALIASES = {
    "word": "doc", "pdf": "doc", "text": "doc",
    "excel": "grid", "sheet": "grid",
    "pptx": "slides",
    "unknown": "file", "default": "file",
}


def _qcol(c) -> QColor:
    return c if isinstance(c, QColor) else QColor(c)


def paint_icon(p: QPainter, name: str, rect: QRectF, color, stroke: float = 1.6):
    """Draw line-art icon ``name`` inside ``rect`` with ``color``."""
    name = _ALIASES.get(name, name)
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(_qcol(color), stroke)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)

    # Normalise to a padded unit box.
    pad = min(rect.width(), rect.height()) * 0.16
    x = rect.x() + pad
    y = rect.y() + pad
    w = rect.width() - 2 * pad
    h = rect.height() - 2 * pad

    def Pt(ux, uy):
        return QPointF(x + ux * w, y + uy * h)

    def Rc(ux, uy, uw, uh):
        return QRectF(x + ux * w, y + uy * h, uw * w, uh * h)

    def line(ax, ay, bx, by):
        p.drawLine(Pt(ax, ay), Pt(bx, by))

    def poly(pts, close=False):
        pp = QPainterPath(Pt(*pts[0]))
        for ux, uy in pts[1:]:
            pp.lineTo(Pt(ux, uy))
        if close:
            pp.closeSubpath()
        p.drawPath(pp)

    fn = _ICONS.get(name, _ICONS["file"])
    fn(p, Pt, Rc, line, poly)
    p.restore()


# ── individual icons (each draws into the unit box) ─────────────────────────
def _mic(p, Pt, Rc, line, poly):
    p.drawRoundedRect(Rc(0.34, 0.04, 0.32, 0.52), Pt(0.16, 0).x() - Pt(0, 0).x() + 6, 6)
    # cradle arc under the capsule
    p.drawArc(Rc(0.22, 0.16, 0.56, 0.5), 180 * 16, 180 * 16)
    line(0.5, 0.68, 0.5, 0.86)          # stem
    line(0.36, 0.88, 0.64, 0.88)        # base


def _mic_off(p, Pt, Rc, line, poly):
    _mic(p, Pt, Rc, line, poly)
    line(0.12, 0.1, 0.88, 0.9)          # slash


def _fullscreen(p, Pt, Rc, line, poly):
    poly([(0.1, 0.34), (0.1, 0.1), (0.34, 0.1)])
    poly([(0.66, 0.1), (0.9, 0.1), (0.9, 0.34)])
    poly([(0.1, 0.66), (0.1, 0.9), (0.34, 0.9)])
    poly([(0.9, 0.66), (0.9, 0.9), (0.66, 0.9)])


def _file(p, Pt, Rc, line, poly):
    poly([(0.24, 0.06), (0.62, 0.06), (0.78, 0.24), (0.78, 0.94),
          (0.24, 0.94)], close=True)
    poly([(0.62, 0.06), (0.62, 0.24), (0.78, 0.24)])   # folded corner


def _doc(p, Pt, Rc, line, poly):
    _file(p, Pt, Rc, line, poly)
    line(0.34, 0.5, 0.68, 0.5)
    line(0.34, 0.62, 0.68, 0.62)
    line(0.34, 0.74, 0.6, 0.74)


def _image(p, Pt, Rc, line, poly):
    p.drawRoundedRect(Rc(0.12, 0.2, 0.76, 0.6), 4, 4)
    p.drawEllipse(Rc(0.28, 0.3, 0.13, 0.13))           # sun
    poly([(0.16, 0.76), (0.4, 0.5), (0.56, 0.66)])     # hill 1
    poly([(0.5, 0.76), (0.66, 0.56), (0.84, 0.76)])    # hill 2


def _video(p, Pt, Rc, line, poly):
    p.drawRoundedRect(Rc(0.12, 0.24, 0.76, 0.52), 4, 4)
    poly([(0.42, 0.38), (0.42, 0.62), (0.62, 0.5)], close=True)  # play


def _audio(p, Pt, Rc, line, poly):
    p.drawEllipse(Rc(0.26, 0.66, 0.2, 0.15))           # note head
    line(0.45, 0.74, 0.45, 0.26)                       # stem
    poly([(0.45, 0.26), (0.7, 0.34), (0.7, 0.46)])     # flag
    line(0.45, 0.38, 0.7, 0.46)


def _code(p, Pt, Rc, line, poly):
    poly([(0.36, 0.3), (0.18, 0.5), (0.36, 0.7)])      # <
    poly([(0.64, 0.3), (0.82, 0.5), (0.64, 0.7)])      # >
    line(0.56, 0.26, 0.44, 0.74)                       # /


def _archive(p, Pt, Rc, line, poly):
    p.drawRect(Rc(0.16, 0.26, 0.68, 0.58))
    line(0.16, 0.42, 0.84, 0.42)                       # lid seam
    p.drawRect(Rc(0.44, 0.42, 0.12, 0.12))             # latch


def _grid(p, Pt, Rc, line, poly):
    p.drawRect(Rc(0.16, 0.18, 0.68, 0.64))
    line(0.38, 0.18, 0.38, 0.82)
    line(0.61, 0.18, 0.61, 0.82)
    line(0.16, 0.39, 0.84, 0.39)
    line(0.16, 0.61, 0.84, 0.61)


def _slides(p, Pt, Rc, line, poly):
    p.drawRoundedRect(Rc(0.14, 0.18, 0.72, 0.5), 3, 3)
    line(0.5, 0.68, 0.5, 0.8)
    line(0.36, 0.82, 0.64, 0.82)
    line(0.3, 0.56, 0.3, 0.42)                         # bars
    line(0.46, 0.56, 0.46, 0.34)
    line(0.62, 0.56, 0.62, 0.46)


def _data(p, Pt, Rc, line, poly):
    p.drawEllipse(Rc(0.22, 0.16, 0.56, 0.16))          # top
    line(0.22, 0.24, 0.22, 0.76)
    line(0.78, 0.24, 0.78, 0.76)
    p.drawArc(Rc(0.22, 0.4, 0.56, 0.16), 180 * 16, 180 * 16)
    p.drawArc(Rc(0.22, 0.68, 0.56, 0.16), 180 * 16, 180 * 16)


def _windows(p, Pt, Rc, line, poly):
    p.drawRect(Rc(0.16, 0.16, 0.3, 0.3))
    p.drawRect(Rc(0.54, 0.16, 0.3, 0.3))
    p.drawRect(Rc(0.16, 0.54, 0.3, 0.3))
    p.drawRect(Rc(0.54, 0.54, 0.3, 0.3))


def _apple(p, Pt, Rc, line, poly):
    body = QPainterPath(Pt(0.5, 0.34))
    body.cubicTo(Pt(0.26, 0.2), Pt(0.1, 0.46), Pt(0.22, 0.72))
    body.cubicTo(Pt(0.32, 0.92), Pt(0.44, 0.92), Pt(0.5, 0.84))
    body.cubicTo(Pt(0.56, 0.92), Pt(0.68, 0.92), Pt(0.78, 0.72))
    body.cubicTo(Pt(0.9, 0.46), Pt(0.74, 0.2), Pt(0.5, 0.34))
    p.drawPath(body)
    leaf = QPainterPath(Pt(0.5, 0.32))                 # leaf/stem
    leaf.cubicTo(Pt(0.54, 0.16), Pt(0.66, 0.12), Pt(0.7, 0.14))
    leaf.cubicTo(Pt(0.66, 0.26), Pt(0.56, 0.3), Pt(0.5, 0.32))
    p.drawPath(leaf)


def _linux(p, Pt, Rc, line, poly):
    # Simple penguin silhouette (Tux-ish): head, body, belly, feet, beak.
    p.drawEllipse(Rc(0.36, 0.08, 0.28, 0.3))           # head
    body = QPainterPath(Pt(0.34, 0.34))
    body.cubicTo(Pt(0.26, 0.5), Pt(0.28, 0.74), Pt(0.36, 0.86))
    body.cubicTo(Pt(0.46, 0.94), Pt(0.54, 0.94), Pt(0.64, 0.86))
    body.cubicTo(Pt(0.72, 0.74), Pt(0.74, 0.5), Pt(0.66, 0.34))
    p.drawPath(body)
    p.drawEllipse(Rc(0.42, 0.16, 0.06, 0.07))          # eyes
    p.drawEllipse(Rc(0.52, 0.16, 0.06, 0.07))
    poly([(0.46, 0.26), (0.54, 0.26), (0.5, 0.33)], close=True)  # beak
    line(0.4, 0.9, 0.34, 0.96)                          # feet
    line(0.6, 0.9, 0.66, 0.96)


_ICONS = {
    "mic": _mic, "mic_off": _mic_off, "fullscreen": _fullscreen,
    "file": _file, "doc": _doc, "image": _image, "video": _video,
    "audio": _audio, "code": _code, "archive": _archive, "grid": _grid,
    "slides": _slides, "data": _data,
    "windows": _windows, "apple": _apple, "linux": _linux,
}


def make_pixmap(name: str, color, size: int = 18, stroke: float = 1.6) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    paint_icon(p, name, QRectF(0, 0, size, size), color, stroke)
    p.end()
    return pm


def make_icon(name: str, color, size: int = 18, stroke: float = 1.6) -> QIcon:
    return QIcon(make_pixmap(name, color, size, stroke))
