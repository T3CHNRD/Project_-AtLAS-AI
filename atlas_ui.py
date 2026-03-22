"""
atlas_ui.py — The Floating Disc  |  Atlas AI v3
================================================
Frameless circular disc. Cyber-Hound sentinel with QPainter fallback.
Flask summoning server on port 8020 for Tailscale remote activation.

Requires:
    pip install PyQt6 requests pymupdf python-docx flask

Assets (optional — QPainter fallback used if absent):
    assets/hound_idle.png
    assets/hound_running.png
    Run  python3 create_assets.py  to generate them automatically.

Come Atlas (add to ~/.zshrc):
    alias comeatlas="python3 /path/to/atlas_ui.py"

Tailscale summon:
    curl http://<mac-tailscale-ip>:8020/come
    iOS Shortcut: GET http://<mac-tailscale-ip>:8020/come
"""

import sys
import math
import logging
import threading
from pathlib import Path

import requests
from PyQt6.QtCore import (
    Qt, QPoint, QPointF, QRectF, QTimer, QThread,
    QPropertyAnimation, QEasingCurve,
    pyqtSignal, pyqtProperty,
)
from PyQt6.QtGui import (
    QBrush, QColor, QFont, QPainter, QPainterPath, QPen, QPixmap,
    QRadialGradient, QPalette, QDragEnterEvent, QDropEvent,
    QTextCursor, QTextCharFormat,
)
from PyQt6.QtWidgets import (
    QApplication, QWidget, QGraphicsDropShadowEffect,
    QTextEdit, QVBoxLayout,
)

# ── Palette ────────────────────────────────────────────────────────────────────
C_VOID     = QColor("#121212")
C_NAVY     = QColor("#2C3E50")
C_AMETHYST = QColor("#6C5B7B")
C_LEATHER  = QColor("#5D4037")
C_PAPER    = QColor("#F4ECD8")
C_MUTED    = QColor("#7A6A5A")
C_DIM      = QColor("#2A2A2A")
C_DANGER   = QColor("#C0392B")

FONT_MONO  = "Menlo, Courier New, monospace"
DISC_D     = 420
BUBBLE_W   = 360
BUBBLE_H   = 190
ASSETS     = Path(__file__).parent / "assets"

OLLAMA_URL   = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.2"
SUMMON_PORT  = 8020

CLERK_PROMPT = (
    "You are Atlas, a sharp, witty Court Clerk. "
    "Summarize this document in 2 sentences. "
    "Direct your Cyber-Hound Spot to file it in the correct "
    "/Active_2025_2026/ subfolder based on context. "
    "End with [Click-Whir] [Arf!]."
)
OFFLINE_MSG = (
    "[Atlas]: The archives are locked. "
    "Ensure the Docker brain is humming. [Click-Whir]"
)

# ── Thread-safe summon flag ────────────────────────────────────────────────────
_SUMMON_FLAG = threading.Event()


def _start_summon_server(port: int = SUMMON_PORT) -> None:
    """Start a Flask daemon on `port` for Tailscale /come summoning."""
    try:
        from flask import Flask, jsonify
    except ImportError:
        print(
            "[Atlas] Flask not installed — Tailscale summoning disabled.\n"
            "        pip install flask  to enable /come route on port 8020."
        )
        return

    logging.getLogger("werkzeug").setLevel(logging.ERROR)

    flask_app = Flask("atlas_summon")

    @flask_app.route("/come")
    def come():
        _SUMMON_FLAG.set()
        return jsonify({"status": "summoned", "message": "The Clerk is on his way."})

    @flask_app.route("/status")
    def status():
        return jsonify({"status": "active", "agent": "Atlas v3", "port": port})

    threading.Thread(
        target=lambda: flask_app.run(
            host="0.0.0.0", port=port, debug=False, use_reloader=False
        ),
        daemon=True,
        name="atlas-summon",
    ).start()
    print(f"[Atlas] Summoning server active → http://0.0.0.0:{port}/come")


# ── Asset helpers ──────────────────────────────────────────────────────────────
def _load_pixmap(name: str) -> "QPixmap | None":
    p = ASSETS / name
    if p.exists():
        pm = QPixmap(str(p))
        return pm if not pm.isNull() else None
    return None


# ── Text extraction ────────────────────────────────────────────────────────────
def extract_text(path: str) -> str:
    ext = Path(path).suffix.lower()
    try:
        if ext == ".pdf":
            import fitz
            return "\n".join(pg.get_text() for pg in fitz.open(path))
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
    """
    Signals
    -------
    dog_state(str)     : "running" | "done" | "error"
    summary_ready(str) : Ollama response
    error(str)         : user-facing error message
    """

    dog_state     = pyqtSignal(str)
    summary_ready = pyqtSignal(str)
    error         = pyqtSignal(str)

    def __init__(self, file_path: str, parent=None):
        super().__init__(parent)
        self._path = file_path

    def run(self):
        self.dog_state.emit("running")
        name = Path(self._path).name
        raw  = extract_text(self._path)

        if not raw.strip() or raw.startswith("[extraction error"):
            self.dog_state.emit("error")
            self.error.emit(
                f"Objection — could not process '{name}'. "
                "Accepted: PDF, DOCX, TXT, MD, CSV, JSON, YAML. [Click-Whir]"
            )
            return

        prompt = f"{CLERK_PROMPT}\n\nDocument:\n{raw[:2000]}"
        try:
            resp = requests.post(
                OLLAMA_URL,
                json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
                timeout=120,
            )
            resp.raise_for_status()
            text = resp.json().get("response", "").strip()
            self.dog_state.emit("done")
            self.summary_ready.emit(text)
        except requests.exceptions.ConnectionError:
            self.dog_state.emit("error")
            self.error.emit(OFFLINE_MSG)
        except Exception as exc:
            self.dog_state.emit("error")
            self.error.emit(str(exc))


class ChatWorker(QThread):
    response_ready = pyqtSignal(str)
    error          = pyqtSignal(str)

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
            self.response_ready.emit(resp.json().get("response", "").strip())
        except requests.exceptions.ConnectionError:
            self.error.emit(OFFLINE_MSG)
        except Exception as exc:
            self.error.emit(str(exc))


# ── QPainter hound — fallback when no image assets present ────────────────────
def _draw_hound(
    painter: QPainter,
    rect: QRectF,
    running: bool = False,
    eye_color: "QColor | None" = None,
) -> None:
    """Minimalist mechanical sentinel hound, vector-drawn."""
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    w = rect.width()
    h = rect.height()

    def px(x): return rect.left() + x * w
    def py(y): return rect.top()  + y * h

    # Torso
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(C_NAVY))
    painter.drawRoundedRect(
        QRectF(px(0.30), py(0.25), w * 0.40, h * 0.30), w * 0.05, w * 0.05
    )
    # Panel seam
    painter.setPen(QPen(C_LEATHER, max(1.0, w * 0.008)))
    painter.drawLine(QPointF(px(0.37), py(0.30)), QPointF(px(0.37), py(0.50)))

    # Head
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(C_NAVY))
    painter.drawRoundedRect(
        QRectF(px(0.33), py(0.09), w * 0.14, h * 0.19), w * 0.03, w * 0.03
    )
    # Snout
    painter.setBrush(QBrush(C_LEATHER))
    painter.drawRoundedRect(
        QRectF(px(0.44), py(0.18), w * 0.10, h * 0.07), w * 0.02, w * 0.02
    )
    # Eye
    eye_c = eye_color if eye_color else C_AMETHYST
    painter.setBrush(QBrush(eye_c))
    painter.drawEllipse(QPointF(px(0.395), py(0.16)), w * 0.025, w * 0.025)

    # Neck connector
    painter.setBrush(QBrush(QColor("#3A3A3A")))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRect(QRectF(px(0.36), py(0.26), w * 0.08, h * 0.03))

    # Collar ring
    painter.setPen(QPen(C_LEATHER.lighter(120), max(1.5, w * 0.007)))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(QRectF(px(0.345), py(0.255), w * 0.09, h * 0.022), 3, 3)

    # Tail
    tail = QPainterPath()
    if running:
        tail.moveTo(QPointF(px(0.30), py(0.30)))
        tail.cubicTo(
            QPointF(px(0.18), py(0.20)),
            QPointF(px(0.12), py(0.10)),
            QPointF(px(0.22), py(0.05)),
        )
    else:
        tail.moveTo(QPointF(px(0.30), py(0.38)))
        tail.cubicTo(
            QPointF(px(0.20), py(0.42)),
            QPointF(px(0.15), py(0.52)),
            QPointF(px(0.18), py(0.60)),
        )
    painter.setPen(
        QPen(C_LEATHER, max(2.0, w * 0.012), Qt.PenStyle.SolidLine,
             Qt.PenCapStyle.RoundCap)
    )
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(tail)

    # Legs
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(C_AMETHYST))
    lw, lh = w * 0.06, h * 0.22
    legs = (
        [
            QRectF(px(0.31), py(0.52), lw, lh * 0.7),
            QRectF(px(0.44), py(0.52), lw, lh * 0.7),
            QRectF(px(0.28), py(0.55), lw * 0.9, lh * 0.8),
            QRectF(px(0.47), py(0.55), lw * 0.9, lh * 0.8),
        ]
        if running else
        [
            QRectF(px(0.32), py(0.55), lw, lh),
            QRectF(px(0.44), py(0.55), lw, lh),
            QRectF(px(0.32), py(0.55), lw, lh),
            QRectF(px(0.44), py(0.55), lw, lh),
        ]
    )
    for leg in legs:
        painter.drawRoundedRect(leg, lw * 0.4, lw * 0.4)
    # Paw joints
    painter.setBrush(QBrush(C_AMETHYST.darker(130)))
    for leg in legs[:2]:
        painter.drawRoundedRect(
            QRectF(leg.left() - 1, leg.bottom() - lw * 0.6, lw + 2, lw * 0.6), 2, 2
        )


# ── HoundWidget — central disc ─────────────────────────────────────────────────
class HoundWidget(QWidget):
    """
    The Archive Port — drag-drop zone + animated Cyber-Hound.
    Uses hound_idle.png / hound_running.png from assets/ if present,
    otherwise falls back to the QPainter sentinel.
    """

    def _get_g(self): return self._glow
    def _set_g(self, v):
        self._glow = v
        self.update()
    glowAlpha = pyqtProperty(float, _get_g, _set_g)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(DISC_D, DISC_D)
        self.setAcceptDrops(True)

        self._state     = "idle"
        self._glow      = 0.35
        self._run_frame = 0
        self._eye_flash = False

        # try to load image assets
        self._pm_idle    = _load_pixmap("hound_idle.png")
        self._pm_running = _load_pixmap("hound_running.png")
        self._use_images = self._pm_idle is not None

        # idle glow animation
        self._idle_anim = QPropertyAnimation(self, b"glowAlpha", self)
        self._idle_anim.setStartValue(0.18)
        self._idle_anim.setEndValue(0.55)
        self._idle_anim.setDuration(1800)
        self._idle_anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._idle_anim.setLoopCount(-1)
        self._idle_anim.start()

        # running leather-pulse ticker
        self._run_timer = QTimer(self)
        self._run_timer.timeout.connect(self._tick_run)

        # eye flash (done state)
        self._eye_timer = QTimer(self)
        self._eye_timer.setSingleShot(True)
        self._eye_timer.timeout.connect(self._end_eye_flash)

        self._workers: list = []

    # ── Public state API ───────────────────────────────────────────────────
    def set_state(self, state: str) -> None:
        self._state = state
        if state == "idle":
            self._run_timer.stop()
            self._idle_anim.start()
        elif state == "hover":
            self._idle_anim.stop()
            self._glow = 0.75
        elif state == "running":
            self._idle_anim.stop()
            self._run_timer.start(100)
        elif state == "done":
            self._run_timer.stop()
            self._eye_flash = True
            self._glow = 0.70
            self._eye_timer.start(700)
        elif state == "error":
            self._run_timer.stop()
            self._idle_anim.stop()
            self._glow = 0.60
        self.update()

    def _tick_run(self) -> None:
        self._run_frame = (self._run_frame + 1) % 8
        phase = math.sin(self._run_frame * math.pi / 4)
        self._glow = 0.35 + 0.35 * ((phase + 1) / 2)
        self.update()

    def _end_eye_flash(self) -> None:
        self._eye_flash = False
        self.set_state("idle")

    # ── Drag events ────────────────────────────────────────────────────────
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.set_state("hover")
        else:
            event.ignore()

    def dragLeaveEvent(self, event) -> None:
        self.set_state("idle")

    def dropEvent(self, event: QDropEvent) -> None:
        self.set_state("idle")
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path:
                self._dispatch(path)
        event.acceptProposedAction()

    def _dispatch(self, path: str) -> None:
        if self.parent():
            self.parent().show_bubble("Reviewing document…", status=True)
        worker = ClerkWorker(path)
        worker.dog_state.connect(self.set_state)
        worker.summary_ready.connect(self._on_summary)
        worker.error.connect(self._on_error)
        worker.finished.connect(
            lambda: self._workers.remove(worker) if worker in self._workers else None
        )
        self._workers.append(worker)
        worker.start()

    def _on_summary(self, text: str) -> None:
        if self.parent():
            self.parent().show_bubble(text)

    def _on_error(self, msg: str) -> None:
        if self.parent():
            self.parent().show_bubble(msg, error=True)

    # ── Paint ──────────────────────────────────────────────────────────────
    def paintEvent(self, _) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = DISC_D / 2.0
        cx, cy = r, r

        # Circular clip
        clip = QPainterPath()
        clip.addEllipse(QPointF(cx, cy), r - 1, r - 1)
        p.setClipPath(clip)
        p.fillPath(clip, QBrush(C_VOID))

        # Radial glow
        gcolor = {
            "idle":    C_AMETHYST,
            "hover":   C_AMETHYST,
            "done":    C_NAVY,
            "running": C_LEATHER,
            "error":   C_DANGER,
        }.get(self._state, C_AMETHYST)
        grad = QRadialGradient(QPointF(cx, cy), r * 0.88)
        g0 = QColor(gcolor); g0.setAlphaF(self._glow * 0.50)
        g1 = QColor(gcolor); g1.setAlphaF(0.0)
        grad.setColorAt(0.0, g0)
        grad.setColorAt(1.0, g1)
        p.fillPath(clip, QBrush(grad))

        # Hound graphic
        hound_sz   = DISC_D * 0.60
        hound_rect = QRectF(cx - hound_sz / 2, cy - hound_sz / 2, hound_sz, hound_sz)

        if self._use_images:
            pm = (
                self._pm_running
                if self._state == "running" and self._pm_running
                else self._pm_idle
            )
            if pm:
                scaled = pm.scaled(
                    int(hound_sz), int(hound_sz),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                p.drawPixmap(
                    int(cx - scaled.width() / 2),
                    int(cy - scaled.height() / 2),
                    scaled,
                )
        else:
            eye_c = C_NAVY.lighter(180) if self._eye_flash else None
            _draw_hound(p, hound_rect, running=(self._state == "running"), eye_color=eye_c)

        # Outer ring
        if self._state == "running":
            rp = QPen(QColor(C_LEATHER), 2.5)
        elif self._state in ("hover",):
            rp = QPen(QColor(C_AMETHYST), 2.5)
        elif self._state == "error":
            rp = QPen(QColor(C_DANGER), 2.0)
        else:
            nc = QColor(C_NAVY); nc.setAlphaF(0.6)
            rp = QPen(nc, 1.5)
        p.setPen(rp)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(cx, cy), r - 2, r - 2)

        # Inner ring
        dc = QColor(C_DIM.lighter(160))
        p.setPen(QPen(dc, 0.8))
        p.drawEllipse(QPointF(cx, cy), r * 0.92, r * 0.92)

        # Status label
        lbl_map = {
            "idle":    "PRESENT DOCUMENT",
            "hover":   "RELEASE TO ARCHIVE",
            "running": "PROCESSING\u2026",
            "done":    "ARCHIVED",
            "error":   "ERROR",
        }
        lc = C_PAPER if self._state == "hover" else C_MUTED
        p.setPen(QPen(lc))
        fnt = QFont()
        fnt.setFamilies(["Menlo", "Courier New"])
        fnt.setPixelSize(9)
        fnt.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 3)
        p.setFont(fnt)
        p.drawText(
            QRectF(cx - 100, cy + hound_sz / 2 * 0.72, 200, 18),
            Qt.AlignmentFlag.AlignCenter,
            lbl_map.get(self._state, ""),
        )

        p.end()


# ── SummaryBubble — slide-out terminal pane ────────────────────────────────────
class SummaryBubble(QWidget):
    def __init__(self):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(BUBBLE_W, BUBBLE_H)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)

        self._text = QTextEdit()
        self._text.setReadOnly(True)
        self._text.setStyleSheet(
            f"QTextEdit {{background:transparent; color:{C_PAPER.name()};"
            f"border:none; font-family:{FONT_MONO}; font-size:11px;"
            f"selection-background-color:{C_AMETHYST.name()};}}"
            f"QScrollBar:vertical {{width:3px; background:transparent;}}"
            f"QScrollBar::handle:vertical {{background:{C_AMETHYST.name()};"
            f"border-radius:1px;}}"
            f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{height:0;}}"
        )
        fnt = QFont()
        fnt.setFamilies(["Menlo", "Courier New"])
        fnt.setPixelSize(11)
        self._text.setFont(fnt)
        layout.addWidget(self._text)

        self._tw_chars: list = []
        self._tw_pos  = 0
        self._tw_timer = QTimer(self)
        self._tw_timer.timeout.connect(self._tw_tick)

        self._slide = QPropertyAnimation(self, b"pos", self)
        self._slide.setDuration(300)
        self._slide.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._auto_dismiss = QTimer(self)
        self._auto_dismiss.setSingleShot(True)
        self._auto_dismiss.timeout.connect(self._slide_out)

    def paintEvent(self, _) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 12, 12)
        bg = QColor(C_VOID); bg.setAlpha(238)
        p.fillPath(path, QBrush(bg))
        p.setPen(QPen(QColor(C_AMETHYST), 1.0))
        p.drawPath(path)

    def show_text(self, text: str, *, status: bool = False, error: bool = False) -> None:
        self._tw_timer.stop()
        self._auto_dismiss.stop()
        self._text.clear()
        if status:
            self._text.setHtml(
                f'<span style="color:{C_MUTED.name()};font-style:italic;">{text}</span>'
            )
            return
        pc = C_DANGER.name() if error else C_AMETHYST.name()
        prefix = "[!]" if error else "[Atlas]"
        self._text.setHtml(f'<span style="color:{pc};font-weight:700;">{prefix} </span>')
        self._tw_chars = list(text)
        self._tw_pos   = 0
        self._tw_timer.start(14)

    def _tw_tick(self) -> None:
        if self._tw_pos >= len(self._tw_chars):
            self._tw_timer.stop()
            self._auto_dismiss.start(14000)
            return
        cur = self._text.textCursor()
        cur.movePosition(QTextCursor.MoveOperation.End)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(C_PAPER))
        cur.setCharFormat(fmt)
        cur.insertText("".join(self._tw_chars[self._tw_pos : self._tw_pos + 4]))
        self._tw_pos += 4
        self._text.setTextCursor(cur)
        self._text.verticalScrollBar().setValue(
            self._text.verticalScrollBar().maximum()
        )

    def slide_in(self, anchor: QPoint) -> None:
        start = QPoint(anchor.x() + BUBBLE_W + 20, anchor.y())
        end   = QPoint(anchor.x() + 16, anchor.y())
        self.move(start)
        self.show()
        self.raise_()
        try:
            self._slide.finished.disconnect()
        except RuntimeError:
            pass
        self._slide.setStartValue(start)
        self._slide.setEndValue(end)
        self._slide.start()

    def _slide_out(self) -> None:
        curr = self.pos()
        end  = QPoint(curr.x() + BUBBLE_W + 20, curr.y())
        try:
            self._slide.finished.disconnect()
        except RuntimeError:
            pass
        self._slide.finished.connect(self.hide)
        self._slide.setStartValue(curr)
        self._slide.setEndValue(end)
        self._slide.start()


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

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(52)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(0, 0, 0, 210))
        self.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._hound  = HoundWidget(self)
        layout.addWidget(self._hound)

        self._bubble   = SummaryBubble()
        self._drag_pos = QPoint()
        self._center_on_screen()

        # Poll _SUMMON_FLAG every 300 ms (thread-safe Qt way)
        self._summon_poll = QTimer(self)
        self._summon_poll.timeout.connect(self._check_summon)
        self._summon_poll.start(300)

    def _center_on_screen(self) -> None:
        s = QApplication.primaryScreen().availableGeometry()
        self.move((s.width() - DISC_D) // 2, (s.height() - DISC_D) // 2)

    def show_bubble(self, text: str, *, status: bool = False, error: bool = False) -> None:
        anchor = self.mapToGlobal(QPoint(DISC_D, (DISC_D - BUBBLE_H) // 2))
        self._bubble.show_text(text, status=status, error=error)
        self._bubble.slide_in(anchor)

    def _check_summon(self) -> None:
        if _SUMMON_FLAG.is_set():
            _SUMMON_FLAG.clear()
            self.show_atlas()

    def show_atlas(self) -> None:
        """Bring Atlas to the front.

        Terminal alias (add to ~/.zshrc):
            alias comeatlas="python3 /path/to/atlas_ui.py"

        Tailscale remote:
            curl http://<mac-tailscale-ip>:8020/come
        """
        self.showNormal()
        self.raise_()
        self.activateWindow()

    # ── Drag the disc ──────────────────────────────────────────────────────
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )

    def mouseMoveEvent(self, event) -> None:
        if (
            event.buttons() == Qt.MouseButton.LeftButton
            and not self._drag_pos.isNull()
        ):
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            if self._bubble.isVisible():
                anchor = self.mapToGlobal(QPoint(DISC_D, (DISC_D - BUBBLE_H) // 2))
                self._bubble.move(anchor.x() + 16, anchor.y())

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def paintEvent(self, _) -> None:
        pass  # HoundWidget paints the visible disc; this host stays transparent


# ── Entry point ────────────────────────────────────────────────────────────────
def main() -> None:
    _start_summon_server(SUMMON_PORT)

    app = QApplication(sys.argv)
    app.setApplicationName("Atlas")
    app.setStyle("Fusion")

    pal = QPalette()
    for role, color in [
        (QPalette.ColorRole.Window,          C_VOID),
        (QPalette.ColorRole.WindowText,      C_PAPER),
        (QPalette.ColorRole.Base,            QColor("#1C1C1C")),
        (QPalette.ColorRole.Text,            C_PAPER),
        (QPalette.ColorRole.Button,          C_NAVY),
        (QPalette.ColorRole.ButtonText,      C_PAPER),
        (QPalette.ColorRole.Highlight,       C_AMETHYST),
        (QPalette.ColorRole.HighlightedText, C_VOID),
    ]:
        pal.setColor(role, color)
    app.setPalette(pal)

    window = FloatingDisc()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
