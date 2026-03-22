"""
atlas_ui.py — The Modern Archive  |  Atlas AI
==============================================
Charcoal black, muted amethyst, burnished leather.
A floating panel for the Court Clerk and his Cyber-Hound.

Requires:
    pip install PyQt6 requests pymupdf python-docx

Come Atlas  (add to ~/.zshrc):
    alias comeatlas="python3 /path/to/atlas_ui.py"
    # Then type:  comeatlas
    # Or for a packaged .app:
    # alias comeatlas="open -a Atlas"
"""

import sys
from pathlib import Path

import requests
from PyQt6.QtCore import Qt, QPoint, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QColor, QPalette, QFont, QTextCharFormat,
    QDragEnterEvent, QDropEvent, QTextCursor,
)
from PyQt6.QtWidgets import (
    QApplication, QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QTextEdit, QPushButton, QLineEdit, QSizePolicy,
    QGraphicsDropShadowEffect,
)

# ── Design tokens ─────────────────────────────────────────────────────────────
BG_BASE      = "#121212"   # Charcoal Black
BG_SURFACE   = "#1C1C1C"
BG_ELEVATED  = "#2C3E50"   # Deep Navy / Grey-Blue
ACCENT       = "#6C5B7B"   # Muted Amethyst Purple
ACCENT_DIM   = "#4A3F57"   # dimmed purple
LEATHER      = "#5D4037"   # Burnished Leather Brown
LEATHER_DIM  = "#3E2723"
TEXT_PRIMARY = "#F4ECD8"   # Antique Paper White
TEXT_MUTED   = "#8A7A6A"
DANGER       = "#C0392B"
FONT_MONO    = "Menlo, Courier New, monospace"

WINDOW_W, WINDOW_H = 460, 600
CORNER_R           = 18
PORT_SIZE          = 158   # diameter of the circular Archive Port

OLLAMA_URL   = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.2"

CLERK_SYSTEM_PROMPT = (
    "You are Atlas, a sharp, sophisticated Court Clerk. "
    "Summarize this file in 2 sentences. "
    "Instruct your Cyber-Hound to archive it in the correct folder within "
    "/Active_2025_2026/ based on content. "
    "Use a tone of high-end professional wit. End with [Click-Whir]."
)
COFFEE_BREAK_MSG = (
    "The Hound and I are momentarily indisposed. "
    "Ensure Ollama is running at http://localhost:11434."
)

# Minimal mechanical glyphs — the Cyber-Hound
HOUND_IDLE    = "\u2699"        # ⚙
HOUND_HOVER   = "\u2699\u2191"  # ⚙↑
HOUND_RUNNING = "\u2699\u2026"  # ⚙…
HOUND_DONE    = "\u2699\u2713"  # ⚙✓
HOUND_ERROR   = "\u26a0"        # ⚠


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


# ── ClerkWorker ────────────────────────────────────────────────────────────────
class ClerkWorker(QThread):
    """Off-thread: extract text -> query Ollama.

    Signals
    -------
    status_update(str) : progress messages
    result_ready(str)  : final Ollama response
    error(str)         : user-facing error message
    """

    status_update = pyqtSignal(str)
    result_ready  = pyqtSignal(str)
    error         = pyqtSignal(str)

    def __init__(self, file_path: str, parent=None):
        super().__init__(parent)
        self._file_path = file_path

    def run(self):
        name = Path(self._file_path).name
        self.status_update.emit(f"Reviewing {name}...")

        raw = extract_text(self._file_path)
        if not raw.strip() or raw.startswith("[extraction error"):
            self.error.emit(
                f"Objection — could not read '{name}'. "
                "Accepted: PDF, DOCX, TXT, MD, CSV, JSON, YAML. [Click-Whir]"
            )
            return

        self.status_update.emit("The Clerk is deliberating...")
        prompt = f"{CLERK_SYSTEM_PROMPT}\n\nDocument:\n{raw[:2000]}"

        try:
            resp = requests.post(
                OLLAMA_URL,
                json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
                timeout=120,
            )
            resp.raise_for_status()
            self.result_ready.emit(resp.json().get("response", "").strip())
        except requests.exceptions.ConnectionError:
            self.error.emit(COFFEE_BREAK_MSG)
        except Exception as exc:
            self.error.emit(str(exc))


# ── ChatWorker ─────────────────────────────────────────────────────────────────
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
            self.error.emit(COFFEE_BREAK_MSG)
        except Exception as exc:
            self.error.emit(str(exc))


# ── CyberHound ─────────────────────────────────────────────────────────────────
class CyberHound(QLabel):
    """Minimalist mechanical glyph indicator."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._base_px = 40
        font = QFont()
        font.setPixelSize(self._base_px)
        self.setFont(font)
        self.setStyleSheet(
            f"color:{TEXT_MUTED}; background:transparent; letter-spacing:4px;"
        )
        self.set_idle()

    def _set(self, glyph: str, color: str = TEXT_MUTED, scale: float = 1.0):
        self.setText(glyph)
        font = self.font()
        font.setPixelSize(int(self._base_px * scale))
        self.setFont(font)
        self.setStyleSheet(
            f"color:{color}; background:transparent; letter-spacing:4px;"
        )

    def set_idle(self):    self._set(HOUND_IDLE,    TEXT_MUTED,   1.00)
    def set_hover(self):   self._set(HOUND_HOVER,   ACCENT,       1.20)
    def set_running(self): self._set(HOUND_RUNNING, LEATHER,      1.00)
    def set_done(self):    self._set(HOUND_DONE,    TEXT_PRIMARY, 1.00)
    def set_error(self):   self._set(HOUND_ERROR,   DANGER,       1.00)


# ── ArchivePort (circular drag-drop zone) ──────────────────────────────────────
class ArchivePort(QWidget):
    """Circular drop zone — the Hound sits at its centre."""

    _PULSE = [LEATHER, "#7D5547", LEATHER, LEATHER_DIM]

    def __init__(self, chat: "ArchiveChat", parent=None):
        super().__init__(parent)
        self._chat    = chat
        self._workers: list = []
        self._pulse_idx   = 0
        self._pulse_timer = QTimer(self)
        self._pulse_timer.timeout.connect(self._pulse_tick)

        self.setAcceptDrops(True)
        self.setFixedSize(PORT_SIZE, PORT_SIZE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self._hound = CyberHound()
        self._label = QLabel("archive port")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setStyleSheet(
            f"color:{TEXT_MUTED}; font-family:{FONT_MONO}; font-size:9px;"
            " background:transparent; letter-spacing:3px;"
        )

        layout.addStretch()
        layout.addWidget(self._hound)
        layout.addWidget(self._label)
        layout.addStretch()

        self._set_ss(ACCENT_DIM)

    def _set_ss(self, border_color: str, border_width: int = 1):
        self.setStyleSheet(
            f"ArchivePort{{"
            f"background:{BG_ELEVATED};"
            f"border:{border_width}px solid {border_color};"
            f"border-radius:{PORT_SIZE // 2}px;}}"
        )

    def _start_pulse(self):
        self._pulse_idx = 0
        self._pulse_timer.start(280)

    def _stop_pulse(self):
        self._pulse_timer.stop()
        self._set_ss(ACCENT_DIM)

    def _pulse_tick(self):
        c = self._PULSE[self._pulse_idx % len(self._PULSE)]
        w = 2 if self._pulse_idx % 2 == 0 else 1
        self._set_ss(c, w)
        self._pulse_idx += 1

    # ── Drag events ────────────────────────────────────────────────────────
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._set_ss(ACCENT, 2)
            self._hound.set_hover()
            self._label.setText("present to the Hound")
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self._reset()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        if not urls:
            self._reset()
            return
        for url in urls:
            path = url.toLocalFile()
            if path:
                self._dispatch(path)
        event.acceptProposedAction()

    def _reset(self):
        self._stop_pulse()
        self._hound.set_idle()
        self._label.setText("archive port")

    def _dispatch(self, path: str):
        self._hound.set_running()
        self._label.setText("processing...")
        self._chat.append_thinking()
        self._start_pulse()

        worker = ClerkWorker(path)
        worker.status_update.connect(self._chat.print_system)
        worker.result_ready.connect(self._on_result)
        worker.error.connect(self._on_error)
        worker.finished.connect(
            lambda: self._workers.remove(worker) if worker in self._workers else None
        )
        self._workers.append(worker)
        worker.start()

    def _on_result(self, text: str):
        self._stop_pulse()
        self._chat.typewrite_replace(text)
        self._hound.set_done()
        self._label.setText("archived \u2014 present another?")

    def _on_error(self, msg: str):
        self._stop_pulse()
        self._chat.typewrite_replace(f"[!] {msg}")
        self._hound.set_error()
        self._label.setText("error \u2014 retry")

    @property
    def hound(self) -> CyberHound:
        return self._hound


# ── ArchiveChat ────────────────────────────────────────────────────────────────
class ArchiveChat(QTextEdit):
    """Rich-text terminal pane with typewriter effect for Atlas responses."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thinking_anchor = -1
        self._tw_chars: list  = []
        self._tw_pos          = 0
        self._tw_timer        = QTimer(self)
        self._tw_timer.timeout.connect(self._tw_tick)

        self.setReadOnly(True)
        self.setStyleSheet(
            f"QTextEdit {{"
            f"background-color: rgba(18,18,18,230);"
            f"color: {TEXT_PRIMARY};"
            f"border: 1px solid {ACCENT_DIM};"
            f"border-radius: 8px;"
            f"padding: 10px 12px;"
            f"font-family: {FONT_MONO};"
            f"font-size: 12px;"
            f"selection-background-color: {ACCENT_DIM};}}"
            f"QScrollBar:vertical {{"
            f"background: transparent; width: 4px; border-radius: 2px;}}"
            f"QScrollBar::handle:vertical {{"
            f"background: {LEATHER_DIM}; border-radius: 2px; min-height: 20px;}}"
            f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{height: 0;}}"
        )
        font = QFont()
        font.setFamilies(["Menlo", "Courier New", "Courier"])
        font.setPixelSize(12)
        self.setFont(font)

    def _bottom(self):
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())

    def print_line(self, prefix: str, text: str, prefix_color: str = ACCENT):
        html = (
            f'<span style="color:{prefix_color};font-weight:700;">{prefix}</span>'
            f'<span style="color:{TEXT_PRIMARY};"> {text}</span>'
        )
        self.append(html)
        self._bottom()

    def print_system(self, msg: str):
        html = f'<span style="color:{TEXT_MUTED};font-style:italic;">{msg}</span>'
        self.append(html)
        self._bottom()

    def append_thinking(self):
        cursor = QTextCursor(self.document())
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self._thinking_anchor = cursor.position()
        html = (
            f'<span style="color:{ACCENT};font-weight:700;">[Atlas]</span>'
            f'<span style="color:{TEXT_MUTED};font-style:italic;"> deliberating...</span>'
        )
        self.append(html)
        self._bottom()

    def typewrite_replace(self, text: str, interval_ms: int = 16):
        """Replace the 'deliberating...' placeholder with a typewriter effect."""
        self._tw_timer.stop()
        if self._thinking_anchor != -1:
            cursor = QTextCursor(self.document())
            cursor.setPosition(self._thinking_anchor)
            cursor.movePosition(
                QTextCursor.MoveOperation.End,
                QTextCursor.MoveMode.KeepAnchor,
            )
            cursor.removeSelectedText()
            self._thinking_anchor = -1

        # Insert the coloured [Atlas] prefix immediately
        cursor = QTextCursor(self.document())
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertHtml(
            f'<span style="color:{ACCENT};font-weight:700;">[Atlas] </span>'
        )

        # Queue the body for character-by-character typewriter output
        self._tw_chars = list(text)
        self._tw_pos   = 0
        self._tw_timer.start(interval_ms)

    def _tw_tick(self):
        if self._tw_pos >= len(self._tw_chars):
            self._tw_timer.stop()
            self._bottom()
            return
        batch = self._tw_chars[self._tw_pos : self._tw_pos + 3]
        cursor = QTextCursor(self.document())
        cursor.movePosition(QTextCursor.MoveOperation.End)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(TEXT_PRIMARY))
        cursor.setCharFormat(fmt)
        cursor.insertText("".join(batch))
        self._tw_pos += 3
        self._bottom()

    def replace_thinking(self, text: str):
        """Alias used by ChatWorker — delegates to typewrite_replace."""
        self.typewrite_replace(text)


# ── ArchiveInput ───────────────────────────────────────────────────────────────
class ArchiveInput(QLineEdit):
    message_sent = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPlaceholderText("> address the Clerk...")
        self.returnPressed.connect(self._send)
        self.setStyleSheet(
            f"QLineEdit {{"
            f"background-color: {BG_ELEVATED};"
            f"color: {TEXT_PRIMARY};"
            f"border: 1px solid {ACCENT_DIM};"
            f"border-radius: 6px;"
            f"padding: 8px 12px;"
            f"font-family: {FONT_MONO};"
            f"font-size: 12px;}}"
            f"QLineEdit:focus {{ border-color: {ACCENT}; }}"
        )
        font = QFont()
        font.setFamilies(["Menlo", "Courier New", "Courier"])
        font.setPixelSize(12)
        self.setFont(font)

    def _send(self):
        text = self.text().strip()
        if text:
            self.message_sent.emit(text)
            self.clear()


# ── TopBar ─────────────────────────────────────────────────────────────────────
class TopBar(QWidget):
    def __init__(self, on_close, parent=None):
        super().__init__(parent)
        self.setFixedHeight(40)
        self.setStyleSheet("background:transparent;")

        row = QHBoxLayout(self)
        row.setContentsMargins(16, 0, 12, 0)
        row.setSpacing(0)

        title = QLabel("A T L A S  \u2014  T H E  A R C H I V E")
        title.setStyleSheet(
            f"color:{TEXT_MUTED}; font-family:{FONT_MONO}; font-size:9px;"
            " font-weight:400; letter-spacing:3px; background:transparent;"
        )

        close_btn = QPushButton("\u00d7")   # ×
        close_btn.setFixedSize(22, 22)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(on_close)
        close_btn.setStyleSheet(
            f"QPushButton {{color:{TEXT_MUTED}; background:transparent;"
            f"border:1px solid {TEXT_MUTED}; border-radius:11px;"
            f"font-size:11px; font-weight:700;}}"
            f"QPushButton:hover {{ color:{DANGER}; border-color:{DANGER}; }}"
        )

        row.addWidget(title)
        row.addStretch()
        row.addWidget(close_btn)


# ── RoundedWindow ──────────────────────────────────────────────────────────────
class RoundedWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(WINDOW_W, WINDOW_H)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(40)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(0, 0, 0, 180))
        self.setGraphicsEffect(shadow)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 14, 14, 14)

        self._inner = QWidget()
        self._inner.setObjectName("inner")
        self._inner.setStyleSheet(
            f"#inner{{background:{BG_BASE};"
            f"border:1px solid {ACCENT_DIM};"
            f"border-radius:{CORNER_R}px;}}"
        )
        outer.addWidget(self._inner)

        self._drag_pos = QPoint()

        screen = QApplication.primaryScreen().availableGeometry()
        self.move(
            (screen.width()  - WINDOW_W) // 2,
            (screen.height() - WINDOW_H) // 2,
        )

    @property
    def inner(self) -> QWidget:
        return self._inner

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )

    def mouseMoveEvent(self, event):
        if (
            event.buttons() == Qt.MouseButton.LeftButton
            and not self._drag_pos.isNull()
        ):
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)


# ── AtlasWindow ────────────────────────────────────────────────────────────────
class AtlasWindow(RoundedWindow):
    def __init__(self):
        super().__init__()
        self._workers: list = []
        self._build_ui()

    # ── "Come Atlas" summoning ─────────────────────────────────────────────
    def show_atlas(self):
        """Bring the panel to the foreground from any context.

        Add to ~/.zshrc:
            alias comeatlas="python3 /path/to/atlas_ui.py"
        Then simply type:
            comeatlas
        """
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _build_ui(self):
        root = QVBoxLayout(self._inner)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(TopBar(on_close=self.close))

        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background:{LEATHER_DIM};")
        root.addWidget(sep)

        content = QWidget()
        content.setStyleSheet("background:transparent;")
        cl = QVBoxLayout(content)
        cl.setContentsMargins(16, 14, 16, 16)
        cl.setSpacing(12)
        root.addWidget(content)

        # Build ArchiveChat first so ArchivePort can reference it
        self._chat = ArchiveChat()
        self._chat.print_line(
            "[Atlas]",
            "The archive is open. Present a document to the Hound "
            "and I shall have it properly catalogued. [Click-Whir]",
        )

        # Centre the circular Archive Port
        port_row = QHBoxLayout()
        port_row.setContentsMargins(0, 0, 0, 0)
        self._port = ArchivePort(self._chat)
        port_row.addStretch()
        port_row.addWidget(self._port)
        port_row.addStretch()
        cl.addLayout(port_row)

        cl.addWidget(self._chat, stretch=1)

        self._input = ArchiveInput()
        self._input.message_sent.connect(self._on_message_sent)
        cl.addWidget(self._input)

    def _on_message_sent(self, text: str):
        self._chat.print_line("[You]", text, prefix_color=TEXT_MUTED)
        self._chat.append_thinking()
        worker = ChatWorker(text)
        worker.result_ready.connect(self._chat.typewrite_replace)
        worker.error.connect(
            lambda e: self._chat.typewrite_replace(f"[!] {e}")
        )
        worker.finished.connect(
            lambda: self._workers.remove(worker) if worker in self._workers else None
        )
        self._workers.append(worker)
        worker.start()


# ── Entry point ────────────────────────────────────────────────────────────────
def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Atlas")
    app.setStyle("Fusion")

    p = QPalette()
    p.setColor(QPalette.ColorRole.Window,          QColor(BG_BASE))
    p.setColor(QPalette.ColorRole.WindowText,      QColor(TEXT_PRIMARY))
    p.setColor(QPalette.ColorRole.Base,            QColor(BG_SURFACE))
    p.setColor(QPalette.ColorRole.AlternateBase,   QColor(BG_ELEVATED))
    p.setColor(QPalette.ColorRole.Text,            QColor(TEXT_PRIMARY))
    p.setColor(QPalette.ColorRole.Button,          QColor(BG_ELEVATED))
    p.setColor(QPalette.ColorRole.ButtonText,      QColor(TEXT_PRIMARY))
    p.setColor(QPalette.ColorRole.Highlight,       QColor(ACCENT))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor(BG_BASE))
    app.setPalette(p)

    window = AtlasWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
