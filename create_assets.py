"""
create_assets.py — Generate hound_idle.png and hound_running.png
================================================================
Run once to create the image assets used by atlas_ui.py.
Renders the QPainter Cyber-Hound into 300×300 PNGs saved to ./assets/.

Usage:
    python3 create_assets.py
"""

import sys
from pathlib import Path

from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QColor, QPainter, QImage
from PyQt6.QtWidgets import QApplication


def _draw_hound(painter, rect, running=False, eye_color=None):
    """Same geometry as atlas_ui.py — kept in sync manually."""
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import (
        QBrush, QPainterPath, QPen,
    )

    C_VOID     = QColor("#121212")
    C_NAVY     = QColor("#2C3E50")
    C_AMETHYST = QColor("#6C5B7B")
    C_LEATHER  = QColor("#5D4037")

    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    w = rect.width()
    h = rect.height()

    def px(x): return rect.left() + x * w
    def py(y): return rect.top()  + y * h

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(C_NAVY))
    painter.drawRoundedRect(QRectF(px(0.30), py(0.25), w*0.40, h*0.30), w*0.05, w*0.05)
    painter.setPen(QPen(C_LEATHER, max(1.0, w*0.008)))
    painter.drawLine(QPointF(px(0.37), py(0.30)), QPointF(px(0.37), py(0.50)))

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(C_NAVY))
    painter.drawRoundedRect(QRectF(px(0.33), py(0.09), w*0.14, h*0.19), w*0.03, w*0.03)
    painter.setBrush(QBrush(C_LEATHER))
    painter.drawRoundedRect(QRectF(px(0.44), py(0.18), w*0.10, h*0.07), w*0.02, w*0.02)

    eye_c = eye_color or C_AMETHYST
    painter.setBrush(QBrush(eye_c))
    painter.drawEllipse(QPointF(px(0.395), py(0.16)), w*0.025, w*0.025)

    painter.setBrush(QBrush(QColor("#3A3A3A")))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRect(QRectF(px(0.36), py(0.26), w*0.08, h*0.03))
    painter.setPen(QPen(C_LEATHER.lighter(120), max(1.5, w*0.007)))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(QRectF(px(0.345), py(0.255), w*0.09, h*0.022), 3, 3)

    tail = QPainterPath()
    if running:
        tail.moveTo(QPointF(px(0.30), py(0.30)))
        tail.cubicTo(QPointF(px(0.18), py(0.20)), QPointF(px(0.12), py(0.10)), QPointF(px(0.22), py(0.05)))
    else:
        tail.moveTo(QPointF(px(0.30), py(0.38)))
        tail.cubicTo(QPointF(px(0.20), py(0.42)), QPointF(px(0.15), py(0.52)), QPointF(px(0.18), py(0.60)))
    painter.setPen(QPen(C_LEATHER, max(2.0, w*0.012), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(tail)

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(C_AMETHYST))
    lw, lh = w*0.06, h*0.22
    legs = (
        [QRectF(px(0.31), py(0.52), lw, lh*0.7), QRectF(px(0.44), py(0.52), lw, lh*0.7),
         QRectF(px(0.28), py(0.55), lw*0.9, lh*0.8), QRectF(px(0.47), py(0.55), lw*0.9, lh*0.8)]
        if running else
        [QRectF(px(0.32), py(0.55), lw, lh), QRectF(px(0.44), py(0.55), lw, lh),
         QRectF(px(0.32), py(0.55), lw, lh), QRectF(px(0.44), py(0.55), lw, lh)]
    )
    for leg in legs:
        painter.drawRoundedRect(leg, lw*0.4, lw*0.4)
    painter.setBrush(QBrush(C_AMETHYST.darker(130)))
    for leg in legs[:2]:
        painter.drawRoundedRect(QRectF(leg.left()-1, leg.bottom()-lw*0.6, lw+2, lw*0.6), 2, 2)


def render_hound(running: bool, size: int = 300) -> QImage:
    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    _draw_hound(p, QRectF(0, 0, size, size), running=running)
    p.end()
    return img


def main():
    app = QApplication(sys.argv)
    out = Path(__file__).parent / "assets"
    out.mkdir(exist_ok=True)

    idle_img    = render_hound(running=False)
    running_img = render_hound(running=True)

    idle_path    = out / "hound_idle.png"
    running_path = out / "hound_running.png"

    idle_img.save(str(idle_path))
    running_img.save(str(running_path))

    print(f"Created: {idle_path}")
    print(f"Created: {running_path}")
    print(
        "\nTo use custom art instead, replace these PNGs with your own\n"
        "300×300 transparent-background images and re-launch Atlas."
    )


if __name__ == "__main__":
    main()
