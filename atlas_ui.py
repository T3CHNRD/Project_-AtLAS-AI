"""
atlas_ui.py — Cyber-Librarian floating panel for Atlas AI
==========================================================
Frameless macOS panel with Matrix-green accents.

Requires:
    pip install PyQt6 requests pymupdf python-docx
"""

import sys
from pathlib import Path

import requests
from PyQt6.QtCore import Qt, QPoint, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QPalette, QFont, QDragEnterEvent, QDropEvent, QTextCursor
from PyQt6.QtWidgets import (
    QApplication, QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QTextEdit, QPushButton, QLineEdit, QSizePolicy,
    QGraphicsDropShadowEffect,
)

# ── Design tokens ────────────────────────────────────────────────────────────
BG_BASE      = "#1A1A1B"
BG_SURFACE   = "#222224"
BG_ELEVATED  = "#2A2A2D"
ACCENT       = "#00FF41"
ACCENT_DIM   = "#00882A"
TEXT_PRIMARY = "#E8E8E8"
TEXT_MUTED   = "#5A5A5F"
DANGER       = "#FF453A"
FONT_MONO    = "Menlo, Courier New, monospace"

WINDOW_W, WINDOW_H = 460, 580
CORNER_R           = 16

OLLAMA_URL   = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.2"

CLERK_SYSTEM_PROMPT = (
    "You are Atlas, a meticulous Court Clerk. "
    "Summarize this in 2 witty sentences. "
    "Command your robot dog Spot to file it in a specific folder within "
    "/Active_2025_2026/ based on content. End with [Arf!]."
)
COFFEE_BREAK_MSG = (
    "Spot and I are on a coffee break. "
    "Check that Ollama is running at http://localhost:11434."
)

DOG_IDLE    = "\U0001f415"
DOG_HOVER   = "\U0001f415\u2b06"
DOG_RUNNING = "\U0001f415\U0001f4a8"
DOG_DONE    = "\U0001f415\u2705"
DOG_ERROR   = "\U0001f9ba"


# ── Text extraction ──────────────────────────────────────────────────────────
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


# ── ClerkWorker ──────────────────────────────────────────────────────────────
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
        self.status_update.emit(f"Extracting text from {name}...")

        raw = extract_text(self._file_path)
        if not raw.strip() or raw.startswith("[extraction error"):
            self.error.emit(
                f"Objection -- could not read '{name}'. "
                "Supported: PDF, DOCX, TXT, MD, CSV, JSON, YAML. [Arf!]"
            )
            return

        self.status_update.emit("Clerk Atlas is reviewing the document...")
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


# ── ChatWorker ───────────────────────────────────────────────────────────────
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


# ── RobotDog ─────────────────────────────────────────────────────────────────
class RobotDog(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._base_px = 56
        font = QFont()
        font.setPixelSize(self._base_px)
        self.setFont(font)
        self.setStyleSheet("background: transparent;")
        self.set_idle()

    def _set(self, glyph: str, scale: float = 1.0):
        self.setText(glyph)
        font = self.font()
        font.setPixelSize(int(self._base_px * scale))
        self.setFont(font)

    def set_idle(self):    self._set(DOG_IDLE,    1.00)
    def set_hover(self):   self._set(DOG_HOVER,   1.20)
    def set_running(self): self._set(DOG_RUNNING, 1.00)
    def set_done(self):    self._set(DOG_DONE,    1.00)
    def set_error(self):   self._set(DOG_ERROR,   1.00)


# ── TerminalChat ─────────────────────────────────────────────────────────────
class TerminalChat(QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._thinking_anchor = -1
        self.setReadOnly(True)
        self.setStyleSheet(
            f"QTextEdit {{"
            f"background-color: rgba(26,26,27,210);"
            f"color: {ACCENT};"
            f"border: 1px solid {ACCENT_DIM};"
            f"border-radius: 8px;"
            f"padding: 10px 12px;"
            f"font-family: {FONT_MONO};"
            f"font-size: 12px;"
            f"selection-background-color: {ACCENT_DIM};}}"
            f"QScrollBar:vertical {{"
            f"background: transparent; width: 4px; border-radius: 2px;}}"
            f"QScrollBar::handle:vertical {{"
            f"background: {ACCENT_DIM}; border-radius: 2px; min-height: 20px;}}"
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
            f'<span style="color:{TEXT_MUTED};font-style:italic;"> thinking...</span>'
        )
        self.append(html)
        self._bottom()

    def replace_thinking(self, text: str):
        if self._thinking_anchor == -1:
            self.print_line("[Atlas]", text)
            return
        cursor = QTextCursor(self.document())
        cursor.setPosition(self._thinking_anchor)
        cursor.movePosition(
            QTextCursor.MoveOperation.End,
            QTextCursor.MoveMode.KeepAnchor,
        )
        cursor.removeSelectedText()
        self._thinking_anchor = -1
        html = (
            f'<span style="color:{ACCENT};font-weight:700;">[Atlas]</span>'
            f'<span style="color:{TEXT_PRIMARY};"> {text}</span>'
        )
        cursor = QTextCursor(self.document())
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertHtml(html)
        self._bottom()


# ── ChatInput ────────────────────────────────────────────────────────────────
class ChatInput(QLineEdit):
    message_sent = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPlaceholderText("> query the archive...")
        self.returnPressed.connect(self._send)
        self.setStyleSheet(
            f"QLineEdit {{"
            f"background-color: {BG_ELEVATED};"
            f"color: {ACCENT};"
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


# ── DragDropArea ─────────────────────────────────────────────────────────────
class DragDropArea(QWidget):
    def __init__(self, chat: "TerminalChat", parent=None):
        super().__init__(parent)
        self._chat    = chat
        self._workers: list = []
        self.setAcceptDrops(True)
        self.setMinimumHeight(150)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._dog   = RobotDog()
        self._label = QLabel("drag a file to brief Spot")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setStyleSheet(
            f"color:{TEXT_MUTED}; font-family:{FONT_MONO}; font-size:11px;"
            " background:transparent;"
        )

        layout.addStretch()
        layout.addWidget(self._dog)
        layout.addWidget(self._label)
        layout.addStretch()

        self._idle_ss  = (
            f"DragDropArea{{background:{BG_ELEVATED};"
            f"border:1px dashed {ACCENT_DIM};border-radius:12px;}}"
        )
        self._hover_ss = (
            f"DragDropArea{{background:{BG_ELEVATED};"
            f"border:1px dashed {ACCENT};border-radius:12px;}}"
        )
        self.setStyleSheet(self._idle_ss)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setStyleSheet(self._hover_ss)
            self._dog.set_hover()
            self._label.setText("drop it -- Spot is ready!")
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self._reset()

    def dropEvent(self, event: QDropEvent):
        self.setStyleSheet(self._idle_ss)
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
        self.setStyleSheet(self._idle_ss)
        self._dog.set_idle()
        self._label.setText("drag a file to brief Spot")

    def _dispatch(self, path: str):
        self._dog.set_running()
        self._label.setText("Spot is on the case...")
        self._chat.append_thinking()

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
        self._chat.replace_thinking(text)
        self._dog.set_done()
        self._label.setText("filed. drop another?")

    def _on_error(self, msg: str):
        self._chat.replace_thinking(f"[!] {msg}")
        self._dog.set_error()
        self._label.setText("error -- try again")

    @property
    def dog(self) -> RobotDog:
        return self._dog


# ── TopBar ───────────────────────────────────────────────────────────────────
class TopBar(QWidget):
    def __init__(self, on_close, parent=None):
        super().__init__(parent)
        self.setFixedHeight(38)
        self.setStyleSheet("background:transparent;")

        row = QHBoxLayout(self)
        row.setContentsMargins(14, 0, 10, 0)
        row.setSpacing(0)

        title = QLabel("Atlas  //  Archives")
        title.setStyleSheet(
            f"color:{ACCENT}; font-family:{FONT_MONO}; font-size:11px;"
            " font-weight:700; letter-spacing:2px; background:transparent;"
        )

        close_btn = QPushButton("x")
        close_btn.setFixedSize(22, 22)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(on_close)
        close_btn.setStyleSheet(
            f"QPushButton {{color:{TEXT_MUTED}; background:transparent;"
            f"border:1px solid {TEXT_MUTED}; border-radius:11px;"
            f"font-size:9px; font-weight:700;}}"
            f"QPushButton:hover {{ color:{DANGER}; border-color:{DANGER}; }}"
        )

        row.addWidget(title)
        row.addStretch()
        row.addWidget(close_btn)


# ── RoundedWindow ────────────────────────────────────────────────────────────
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
        shadow.setBlurRadius(32)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 160))
        self.setGraphicsEffect(shadow)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)

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


# ── AtlasWindow ──────────────────────────────────────────────────────────────
class AtlasWindow(RoundedWindow):
    def __init__(self):
        super().__init__()
        self._workers: list = []
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self._inner)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(TopBar(on_close=self.close))

        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background:{ACCENT_DIM};")
        root.addWidget(sep)

        content = QWidget()
        content.setStyleSheet("background:transparent;")
        cl = QVBoxLayout(content)
        cl.setContentsMargins(14, 12, 14, 14)
        cl.setSpacing(10)
        root.addWidget(content)

        # Build chat widget first so DragDropArea can reference it
        self._chat = TerminalChat()
        self._chat.print_line(
            "[Atlas]",
            "Court is in session. Hand Spot a file and I will have it "
            "catalogued before you can say motion granted. [Arf!]",
        )

        self._drop_area = DragDropArea(self._chat)
        cl.addWidget(self._drop_area, stretch=3)

        cl.addWidget(self._chat, stretch=2)

        self._input = ChatInput()
        self._input.message_sent.connect(self._on_message_sent)
        cl.addWidget(self._input)

    def _on_message_sent(self, text: str):
        self._chat.print_line("[You]", text, prefix_color=TEXT_MUTED)
        self._chat.append_thinking()
        worker = ChatWorker(text)
        worker.result_ready.connect(self._chat.replace_thinking)
        worker.error.connect(
            lambda e: self._chat.replace_thinking(f"[!] {e}")
        )
        worker.finished.connect(
            lambda: self._workers.remove(worker) if worker in self._workers else None
        )
        self._workers.append(worker)
        worker.start()


# ── Entry point ──────────────────────────────────────────────────────────────
def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Atlas")
    app.setStyle("Fusion")

    p = QPalette()
    p.setColor(QPalette.ColorRole.Window,          QColor(BG_BASE))
    p.setColor(QPalette.ColorRole.WindowText,      QColor(TEXT_PRIMARY))
    p.setColor(QPalette.ColorRole.Base,            QColor(BG_SURFACE))
    p.setColor(QPalette.ColorRole.AlternateBase,   QColor(BG_ELEVATED))
    p.setColor(QPalette.ColorRole.Text,            QColor(ACCENT))
    p.setColor(QPalette.ColorRole.Button,          QColor(BG_ELEVATED))
    p.setColor(QPalette.ColorRole.ButtonText,      QColor(ACCENT))
    p.setColor(QPalette.ColorRole.Highlight,       QColor(ACCENT_DIM))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor(BG_BASE))
    app.setPalette(p)

    window = AtlasWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
