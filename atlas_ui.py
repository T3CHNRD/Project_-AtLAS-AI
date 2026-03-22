"""
atlas_ui.py — The Floating Disc  |  Atlas AI
=============================================
A frameless superellipse floating above the desktop.
The Cyber-Hound Sentinel is painted entirely in QPainter —
no external image assets required.

Requires:  pip install PyQt6 requests pymupdf python-docx
"""

import sys, math
from pathlib import Path

import requests
from PyQt6.QtCore import (
    Qt, QPoint, QPointF, QRectF, QTimer, QThread, QPropertyAnimation,
    QEasingCurve, pyqtSignal, pyqtProperty,
)
from PyQt6.QtGui import (
    QBrush, QColor, QFont, QPainter, QPainterPath, QPen,
    QRadialGradient, QLinearGradient, QPalette,
    QDragEnterEvent, QDropEvent, QTextCursor, QTextCharFormat,
)
from PyQt6.QtWidgets import (
    QApplication, QWidget, QGraphicsDropShadowEffect,
    QTextEdit, QVBoxLayout, QHBoxLayout, QLabel,
)

# ── Palette ────────────────────────────────────────────────────────────────────
C_VOID     = QColor("#121212")   # Charcoal Black
C_NAVY     = QColor("#2C3E50")   # Grey-Blue
C_AMETHYST = QColor("#6C5B7B")   # Muted Amethyst
C_LEATHER  = QColor("#5D4037")   # Burnished Leather
C_PAPER    = QColor("#F4ECD8")   # Antique Paper White
C_MUTED    = QColor("#7A6A5A")
C_DIM      = QColor("#2A2A2A")
C_DANGER   = QColor("#C0392B")

FONT_MONO = "Menlo, Courier New, monospace"

DISC_D = 420          # diameter of the main disc
BUBBLE_W = 340        # summary bubble width
BUBBLE_H = 160        # summary bubble height

OLLAMA_URL   = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.2"

CLERK_PROMPT = (
    "You are Atlas, a sharp, sophisticated Court Clerk. "
    "Summarize this file in exactly 2 sentences. "
    "Instruct your Cyber-Hound to archive it in the correct folder within "
    "/Active_2025_2026/. Use high-end professional wit. End with [Click-Whir]."
)
OFFLINE_MSG = (
    "The Hound and I are momentarily indisposed. "
    "Ensure Ollama is running at localhost:11434."
)


# ── Text extraction ────────────────────────────────────────────────────────────
def extract_text(path: str) -> str:
    ext = Path(path).suffix.lower()
    try:
        if ext == ".pdf":
            import fitz
            return "\n".join(p.get_text() for p in fitz.open(path))
        if ext in (".docx", ".doc"):
            import docx
            return "\n".join(p.text for p in docx.Document(path).paragraphs)
        if ext in (".txt", ".md", ".csv", ".json", ".yaml", ".yml", ".log"):
            return Path(path).read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return f"[extraction error: {exc}]"
    return ""


# ── Workers ────────────────────────────────────────────────────────────────────
class ClerkWorker(QThread):
    status_update = pyqtSignal(str)
    result_ready  = pyqtSignal(str)
    error         = pyqtSignal(str)

    def __init__(self, file_path: str, parent=None):
        super().__init__(parent)
        self._path = file_path

    def run(self):
        name = Path(self._path).name
        self.status_update.emit(f"Reading {name}...")
        raw = extract_text(self._path)
        if not raw.strip() or raw.startswith("[extraction error"):
            self.error.emit(
                f"Objection — could not read '{name}'. "
                "Accepted: PDF, DOCX, TXT, MD, CSV, JSON, YAML. [Click-Whir]"
            )
            return
        self.status_update.emit("The Clerk is deliberating...")
        prompt = f"{CLERK_PROMPT}\n\nDocument:\n{raw[:2000]}"
        try:
            resp = requests.post(
                OLLAMA_URL,
                json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
                timeout=120,
            )
            resp.raise_for_status()
            self.result_ready.emit(resp.json().get("response", "").strip())
        except requests.exceptions.ConnectionError:
            self.error.emit(OFFLINE_MSG)
        except Exception as exc:
            self.error.emit(str(exc))


class ChatWorker(QThread):
    result_ready = pyqtSignal(str)
    error        = pyqtSignal(str)

    def __init__(self, prompt: str, parent=None):
        super().__init__(parent)
        self._prompt = prompt

    def run(self):
        try:
            resp = requests.post(
                OLLAMA_URL,
                json={"model": OLLAMA_MODEL, "prompt": self._prompt, "stream": False},
                timeout=120,
            )
            resp.raise_for_status()
            self.result_ready.emit(resp.json().get("response", "").strip())
        except requests.exceptions.ConnectionError:
            self.error.emit(OFFLINE_MSG)
        except Exception as exc:
            self.error.emit(str(exc))


# ── Hound painter helper ───────────────────────────────────────────────────────
def _draw_hound(painter: QPainter, rect: QRectF, running: bool = False,
                eye_color: QColor | None = None):
    """
    Draw a minimalist mechanical sentinel hound inside `rect`.
    All geometry is proportional to rect.width().
    """
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    w  = rect.width()
    h  = rect.height()
    cx = rect.center().x()
    cy = rect.center().y()

    unit  = w / 10.0         # base unit
    body_color  = C_NAVY
    leg_color   = C_AMETHYST
    detail_color = C_LEATHER
    eye_c       = eye_color if eye_color else C_AMETHYST

    def px(x): return rect.left() + x * w
    def py(y): return rect.top()  + y * h

    # ── Torso
    torso = QRectF(px(0.30), py(0.25), px(0.40) - px(0.30), py(0.55) - py(0.25))
    painter.setBrush(QBrush(body_color))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(torso, unit * 0.5, unit * 0.5)

    # Torso detail line (panel seam)
    pen = QPen(detail_color, max(1.0, w * 0.008))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.drawLine(
        QPointF(px(0.37), py(0.30)),
        QPointF(px(0.37), py(0.50)),
    )

    # ── Head
    head = QRectF(px(0.33), py(0.10), px(0.34) - px(0.33), py(0.28) - py(0.10))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(body_color))
    painter.drawRoundedRect(head, unit * 0.3, unit * 0.3)

    # Snout
    snout = QRectF(px(0.44), py(0.19), px(0.54) - px(0.44), py(0.26) - py(0.19))
    painter.setBrush(QBrush(detail_color))
    painter.drawRoundedRect(snout, unit * 0.2, unit * 0.2)

    # Eye
    eye_cx = px(0.395)
    eye_cy = py(0.17)
    eye_r  = w * 0.025
    painter.setBrush(QBrush(eye_c))
    painter.drawEllipse(QPointF(eye_cx, eye_cy), eye_r, eye_r)

    # ── Neck connector
    neck = QRectF(px(0.36), py(0.26), px(0.44) - px(0.36), py(0.29) - py(0.26))
    painter.setBrush(QBrush(C_DIM.lighter(140)))
    painter.drawRect(neck)

    # ── Tail (up or tucked depending on running)
    tail_path = QPainterPath()
    if running:
        tail_path.moveTo(px(0.30), py(0.30))
        tail_path.cubicTo(
            QPointF(px(0.18), py(0.20)),
            QPointF(px(0.12), py(0.10)),
            QPointF(px(0.22), py(0.05)),
        )
    else:
        tail_path.moveTo(px(0.30), py(0.38))
        tail_path.cubicTo(
            QPointF(px(0.20), py(0.42)),
            QPointF(px(0.15), py(0.52)),
            QPointF(px(0.18), py(0.60)),
        )
    painter.setPen(QPen(detail_color, max(2.0, w * 0.012), Qt.PenStyle.SolidLine,
                        Qt.PenCapStyle.RoundCap))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(tail_path)

    # ── Legs
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(leg_color))
    leg_w = w * 0.06
    leg_h = h * 0.22

    if running:
        # Extended stride
        legs = [
            QRectF(px(0.31), py(0.52), leg_w, leg_h * 0.7),
            QRectF(px(0.44), py(0.52), leg_w, leg_h * 0.7),
            QRectF(px(0.28), py(0.55), leg_w * 0.9, leg_h * 0.8),
            QRectF(px(0.47), py(0.55), leg_w * 0.9, leg_h * 0.8),
        ]
    else:
        legs = [
            QRectF(px(0.32), py(0.55), leg_w, leg_h),
            QRectF(px(0.44), py(0.55), leg_w, leg_h),
            QRectF(px(0.32), py(0.55), leg_w, leg_h),
            QRectF(px(0.44), py(0.55), leg_w, leg_h),
        ]

    for leg in legs:
        painter.drawRoundedRect(leg, leg_w * 0.4, leg_w * 0.4)

    # Paw joints
    painter.setBrush(QBrush(C_AMETHYST.darker(130)))
    for leg in legs[:2]:
        paw = QRectF(leg.left() - 1, leg.bottom() - leg_w * 0.6,
                     leg_w + 2, leg_w * 0.6)
        painter.drawRoundedRect(paw, 2, 2)

    # ── Collar ring
    collar = QRectF(px(0.345), py(0.255), px(0.435) - px(0.345), w * 0.03)
    pen2 = QPen(C_LEATHER.lighter(120), max(1.5, w * 0.007))
    painter.setPen(pen2)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(collar, 3, 3)


# ── HoundDisc — the central painted widget ────────────────────────────────────
class HoundDisc(QWidget):
    """
    Circular drag-drop zone that paints the hound sentinel.
    States: idle | hover | processing | done | error
    """

    # animatable property for glow alpha
    def _get_glow(self): return self._glow_alpha
    def _set_glow(self, v):
        self._glow_alpha = v
        self.update()
    glowAlpha = pyqtProperty(float, _get_glow, _set_glow)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(DISC_D, DISC_D)
        self.setAcceptDrops(True)
        self._state        = "idle"
        self._glow_alpha   = 0.35
        self._running_frame = 0

        # idle glow pulse
        self._idle_anim = QPropertyAnimation(self, b"glowAlpha", self)
        self._idle_anim.setStartValue(0.18)
        self._idle_anim.setEndValue(0.55)
        self._idle_anim.setDuration(1800)
        self._idle_anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._idle_anim.setLoopCount(-1)
        self._idle_anim.start()

        # running frame ticker
        self._run_timer = QTimer(self)
        self._run_timer.timeout.connect(self._next_run_frame)

        # eye-flash timer
        self._eye_flash   = False
        self._eye_timer   = QTimer(self)
        self._eye_timer.setSingleShot(True)
        self._eye_timer.timeout.connect(self._end_eye_flash)

        # workers
        self._workers: list = []

    # ── State changes ──────────────────────────────────────────────────────
    def set_idle(self):
        self._state = "idle"
        self._run_timer.stop()
        self._idle_anim.start()
        self.update()

    def set_hover(self):
        self._state = "hover"
        self._idle_anim.stop()
        self._glow_alpha = 0.70
        self.update()

    def set_processing(self):
        self._state = "processing"
        self._idle_anim.stop()
        self._run_timer.start(120)
        self.update()

    def set_done(self):
        self._state = "done"
        self._run_timer.stop()
        # eye flash: blue-grey
        self._eye_flash = True
        self._eye_timer.start(600)
        self._glow_alpha = 0.70
        self.update()

    def set_error(self):
        self._state = "error"
        self._run_timer.stop()
        self._idle_anim.stop()
        self._glow_alpha = 0.60
        self.update()

    def _next_run_frame(self):
        self._running_frame = (self._running_frame + 1) % 8
        # pulse leather glow
        phase = math.sin(self._running_frame * math.pi / 4)
        self._glow_alpha = 0.35 + 0.35 * ((phase + 1) / 2)
        self.update()

    def _end_eye_flash(self):
        self._eye_flash = False
        self.set_idle()

    # ── Drag events ────────────────────────────────────────────────────────
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.set_hover()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.set_idle()

    def dropEvent(self, event: QDropEvent):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path:
                self._dispatch(path)
        event.acceptProposedAction()

    def _dispatch(self, path: str):
        self.set_processing()
        if self.parent():
            self.parent().show_bubble("Processing…", status=True)
        w = ClerkWorker(path)
        w.status_update.connect(self._on_status)
        w.result_ready.connect(self._on_result)
        w.error.connect(self._on_error)
        w.finished.connect(lambda: self._workers.remove(w) if w in self._workers else None)
        self._workers.append(w)
        w.start()

    def _on_status(self, msg: str):
        if self.parent():
            self.parent().show_bubble(msg, status=True)

    def _on_result(self, text: str):
        self.set_done()
        if self.parent():
            self.parent().show_bubble(text)

    def _on_error(self, msg: str):
        self.set_error()
        if self.parent():
            self.parent().show_bubble(f"[!] {msg}", error=True)

    # ── Paint ──────────────────────────────────────────────────────────────
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = float(DISC_D / 2)
        cx, cy = r, r

        # -- Disc background
        disc_path = QPainterPath()
        disc_path.addEllipse(QPointF(cx, cy), r - 1, r - 1)
        p.setClipPath(disc_path)
        p.fillPath(disc_path, QBrush(C_VOID))

        # -- Radial glow
        if self._state in ("idle", "hover", "done"):
            glow_color = QColor(C_AMETHYST)
        elif self._state == "processing":
            glow_color = QColor(C_LEATHER)
        else:  # error
            glow_color = QColor(C_DANGER)

        grad = QRadialGradient(QPointF(cx, cy), r * 0.85)
        g0 = QColor(glow_color)
        g0.setAlphaF(self._glow_alpha * 0.45)
        g1 = QColor(glow_color)
        g1.setAlphaF(0.0)
        grad.setColorAt(0.0, g0)
        grad.setColorAt(1.0, g1)
        p.fillPath(disc_path, QBrush(grad))

        # -- Outer ring
        ring_pen = QPen(QColor(C_NAVY), 1.5)
        if self._state == "hover":
            ring_pen = QPen(QColor(C_AMETHYST), 2.0)
        elif self._state == "processing":
            ring_pen = QPen(QColor(C_LEATHER), 2.0)
        p.setPen(ring_pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(cx, cy), r - 2, r - 2)

        # -- Inner subtle ring
        inner_pen = QPen(QColor(C_DIM.lighter(160)), 0.8)
        p.setPen(inner_pen)
        p.drawEllipse(QPointF(cx, cy), r * 0.92, r * 0.92)

        # -- Hound silhouette
        is_running = (self._state == "processing")
        eye_c = QColor(C_NAVY).lighter(160) if self._eye_flash else None
        hound_size = DISC_D * 0.62
        hound_rect = QRectF(
            cx - hound_size / 2,
            cy - hound_size / 2,
            hound_size,
            hound_size,
        )
        _draw_hound(p, hound_rect, running=is_running, eye_color=eye_c)

        # -- Idle label under hound
        if self._state == "idle":
            p.setPen(QPen(C_MUTED))
            font = QFont()
            font.setFamilies(["Menlo", "Courier New"])
            font.setPixelSize(9)
            font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 3)
            p.setFont(font)
            label_rect = QRectF(cx - 90, cy + hound_size / 2 * 0.68, 180, 20)
            p.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, "PRESENT DOCUMENT")

        elif self._state == "hover":
            p.setPen(QPen(C_PAPER))
            font = QFont()
            font.setFamilies(["Menlo", "Courier New"])
            font.setPixelSize(10)
            p.setFont(font)
            label_rect = QRectF(cx - 90, cy + hound_size / 2 * 0.68, 180, 20)
            p.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, "RELEASE TO FILE")

        p.end()


# ── Summary Bubble ─────────────────────────────────────────────────────────────
class SummaryBubble(QWidget):
    """
    Slides out to the right of the disc to display the Clerk's response.
    """

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(BUBBLE_W, BUBBLE_H)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)

        self._text = QTextEdit()
        self._text.setReadOnly(True)
        self._text.setStyleSheet(
            f"QTextEdit {{"
            f"background: transparent;"
            f"color: {C_PAPER.name()};"
            f"border: none;"
            f"font-family: {FONT_MONO};"
            f"font-size: 11px;"
            f"selection-background-color: {C_AMETHYST.name()};}}"
            f"QScrollBar:vertical {{ width: 3px; background: transparent; }}"
            f"QScrollBar::handle:vertical {{ background: {C_AMETHYST.name()}; border-radius:1px; }}"
            f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}"
        )
        font = QFont()
        font.setFamilies(["Menlo", "Courier New"])
        font.setPixelSize(11)
        self._text.setFont(font)

        layout.addWidget(self._text)

        self._tw_chars: list = []
        self._tw_pos  = 0
        self._tw_timer = QTimer(self)
        self._tw_timer.timeout.connect(self._tw_tick)

        # slide animation (x offset)
        self._slide_anim = QPropertyAnimation(self, b"pos", self)
        self._slide_anim.setDuration(320)
        self._slide_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        # auto-dismiss timer
        self._dismiss_timer = QTimer(self)
        self._dismiss_timer.setSingleShot(True)
        self._dismiss_timer.timeout.connect(self._slide_out)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 12, 12)
        bg = QColor(C_VOID)
        bg.setAlpha(230)
        p.fillPath(path, QBrush(bg))
        p.setPen(QPen(QColor(C_AMETHYST), 1.0))
        p.drawPath(path)
        p.end()

    def show_text(self, text: str, *, status: bool = False, error: bool = False):
        self._tw_timer.stop()
        self._dismiss_timer.stop()
        self._text.clear()
        if status:
            html = f'<span style="color:{C_MUTED.name()};font-style:italic;">{text}</span>'
            self._text.setHtml(html)
            return
        prefix_color = C_DANGER.name() if error else C_AMETHYST.name()
        prefix = "[!]" if error else "[Atlas]"
        self._text.setHtml(
            f'<span style="color:{prefix_color};font-weight:700;">{prefix} </span>'
        )
        self._tw_chars = list(text)
        self._tw_pos   = 0
        self._tw_timer.start(14)

    def _tw_tick(self):
        if self._tw_pos >= len(self._tw_chars):
            self._tw_timer.stop()
            self._dismiss_timer.start(12000)  # auto-dismiss after 12 s
            return
        cursor = self._text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(C_PAPER))
        cursor.setCharFormat(fmt)
        cursor.insertText("".join(self._tw_chars[self._tw_pos : self._tw_pos + 4]))
        self._tw_pos += 4
        self._text.setTextCursor(cursor)
        self._text.verticalScrollBar().setValue(
            self._text.verticalScrollBar().maximum()
        )

    def slide_in(self, anchor: QPoint):
        """Slide in from the right edge of the disc."""
        start = QPoint(anchor.x() + BUBBLE_W + 20, anchor.y())
        end   = QPoint(anchor.x() + 12, anchor.y())
        self.move(start)
        self.show()
        self.raise_()
        self._slide_anim.setStartValue(start)
        self._slide_anim.setEndValue(end)
        self._slide_anim.start()

    def _slide_out(self):
        current = self.pos()
        end     = QPoint(current.x() + BUBBLE_W + 20, current.y())
        self._slide_anim.setStartValue(current)
        self._slide_anim.setEndValue(end)
        self._slide_anim.finished.connect(self.hide)
        self._slide_anim.start()


# ── FloatingDisc — top-level window ───────────────────────────────────────────
class FloatingDisc(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(DISC_D, DISC_D)

        # outer drop shadow
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(48)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(0, 0, 0, 200))
        self.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._disc = HoundDisc(self)
        layout.addWidget(self._disc)

        # summary bubble (child, floats alongside)
        self._bubble = SummaryBubble()

        self._drag_pos = QPoint()
        self._center_on_screen()

    def _center_on_screen(self):
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(
            (screen.width()  - DISC_D) // 2,
            (screen.height() - DISC_D) // 2,
        )

    # ── Bubble control ─────────────────────────────────────────────────────
    def show_bubble(self, text: str, *, status: bool = False, error: bool = False):
        anchor = self.mapToGlobal(QPoint(DISC_D, (DISC_D - BUBBLE_H) // 2))
        self._bubble.show_text(text, status=status, error=error)
        self._bubble.slide_in(anchor)

    # ── "Come Atlas" ───────────────────────────────────────────────────────
    def show_atlas(self):
        """Summon Atlas to the front.

        Add to ~/.zshrc:
            alias comeatlas="python3 /path/to/atlas_ui.py"
        """
        self.showNormal()
        self.raise_()
        self.activateWindow()

    # ── Window drag ────────────────────────────────────────────────────────
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )

    def mouseMoveEvent(self, event):
        if (event.buttons() == Qt.MouseButton.LeftButton
                and not self._drag_pos.isNull()):
            new_pos = event.globalPosition().toPoint() - self._drag_pos
            self.move(new_pos)
            # keep bubble attached
            anchor = self.mapToGlobal(QPoint(DISC_D, (DISC_D - BUBBLE_H) // 2))
            if self._bubble.isVisible():
                self._bubble.move(
                    QPoint(anchor.x() + 12, anchor.y())
                )

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def paintEvent(self, _):
        # The HoundDisc paints itself; this widget stays fully transparent.
        pass


# ── Entry point ────────────────────────────────────────────────────────────────
def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Atlas")
    app.setStyle("Fusion")

    p = QPalette()
    for role, color in [
        (QPalette.ColorRole.Window,          C_VOID),
        (QPalette.ColorRole.WindowText,      C_PAPER),
        (QPalette.ColorRole.Base,            QColor("#1C1C1C")),
        (QPalette.ColorRole.Text,            C_PAPER),
        (QPalette.ColorRole.Button,          QColor("#2C3E50")),
        (QPalette.ColorRole.ButtonText,      C_PAPER),
        (QPalette.ColorRole.Highlight,       C_AMETHYST),
        (QPalette.ColorRole.HighlightedText, C_VOID),
    ]:
        p.setColor(role, color)
    app.setPalette(p)

    window = FloatingDisc()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
