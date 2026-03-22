import sys
from pathlib import Path

import requests
from PyQt6.QtCore import Qt, QPoint, QThread, pyqtSignal
from PyQt6.QtGui import (
    QColor, QPalette, QFont, QDragEnterEvent, QDropEvent, QTextCursor,
)
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QHBoxLayout, QVBoxLayout,
    QLabel, QTextEdit, QLineEdit,
)

# ─── Colour Palette ───────────────────────────────────────────────────────────
BG_PRIMARY    = "#121212"
BG_SECONDARY  = "#1E1E1E"
BG_INPUT      = "#2A2A2A"
BORDER_DASHED = "#3A3A3A"
ACCENT        = "#7C6AF7"       # soft violet
TEXT_PRIMARY  = "#E8E8E8"
TEXT_MUTED    = "#6B6B6B"
FONT_FAMILY   = "SF Pro Text, Helvetica Neue, Arial, sans-serif"

WELCOME_MSG = (
    "Good morning. Court is in session. "
    "Hand Spot a file and I'll have it catalogued, stamped, and filed "
    "before you can say 'motion granted.'"
)

OLLAMA_URL   = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.2"

CLERK_SYSTEM_PROMPT = (
    "You are Atlas, a witty, sharp, professional Court Clerk. "
    "Summarize this text in 2 precise sentences and recommend which folder "
    "inside /Active_2025_2026/ it belongs in. "
    "Add a robotic barking sound effect at the end like [Arf!]."
)

COFFEE_BREAK_MSG = (
    "Spot and I are on a coffee break. \u2615 "
    "Make sure Ollama is running at http://localhost:11434."
)


# ─── Text Extraction ──────────────────────────────────────────────────────────

def extract_text(path: str) -> str:
    """Return plain text from PDF, DOCX, or plain-text files."""
    ext = Path(path).suffix.lower()
    try:
        if ext == ".pdf":
            import fitz  # PyMuPDF
            doc = fitz.open(path)
            return "\n".join(page.get_text() for page in doc)
        elif ext in (".docx", ".doc"):
            import docx
            document = docx.Document(path)
            return "\n".join(p.text for p in document.paragraphs)
        elif ext in (".txt", ".md", ".csv", ".json", ".yaml", ".yml", ".log"):
            return Path(path).read_text(encoding="utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        return f"[extraction error: {exc}]"
    return ""


SYSTEM_PROMPT   = CLERK_SYSTEM_PROMPT  # alias kept for ChatWorker


# ─── ClerkWorker ─────────────────────────────────────────────────────────────

class ClerkWorker(QThread):
    """Background thread that processes a dropped file through Ollama.

    Signals
    -------
    summaryReady : str  — The clerk's witty 2-sentence summary + folder rec.
    dogStatus    : str  — 'running' when work starts, 'idle' when done.
    error_occurred: str — User-facing error message (Ollama unreachable, etc.).
    """

    summaryReady   = pyqtSignal(str)
    dogStatus      = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(self, file_path: str, parent=None):
        super().__init__(parent)
        self._file_path = file_path

    def run(self):
        self.dogStatus.emit("running")

        raw = extract_text(self._file_path)
        if not raw.strip() or raw.startswith("[extraction error"):
            name = Path(self._file_path).name
            self.dogStatus.emit("idle")
            self.error_occurred.emit(
                f"Objection — I couldn\u2019t read \u2018{name}\u2019. "
                "Supported formats: PDF, DOCX, TXT, MD, CSV, JSON, YAML. [Arf!]"
            )
            return

        snippet = raw[:2000]
        prompt  = f"{CLERK_SYSTEM_PROMPT}\n\nDocument:\n{snippet}"

        try:
            resp = requests.post(
                OLLAMA_URL,
                json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
                timeout=120,
            )
            resp.raise_for_status()
            text = resp.json().get("response", "").strip()
            self.summaryReady.emit(text)
        except requests.exceptions.ConnectionError:
            self.error_occurred.emit(COFFEE_BREAK_MSG)
        except Exception as exc:  # noqa: BLE001
            self.error_occurred.emit(str(exc))
        finally:
            self.dogStatus.emit("idle")


# ─── ChatWorker ───────────────────────────────────────────────────────────────

class ChatWorker(QThread):
    """Sends a free-text question to Ollama from the chat input."""

    response_ready = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

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
            self.error_occurred.emit(COFFEE_BREAK_MSG)
        except Exception as exc:  # noqa: BLE001
            self.error_occurred.emit(str(exc))


class DragDropArea(QLabel):
    """Drag-and-drop target. Emits fileAccepted(path) for each dropped file."""

    fileAccepted = pyqtSignal(str)  # emits local file path

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setText("Drop a file for Spot to fetch\u2026")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setAcceptDrops(True)
        self.setMinimumHeight(90)
        self.setStyleSheet(f"""
            QLabel {{
                color: {TEXT_MUTED};
                border: 1px dashed {BORDER_DASHED};
                border-radius: 8px;
                background-color: {BG_SECONDARY};
                font-size: 13px;
                letter-spacing: 0.5px;
            }}
            QLabel:hover {{
                border-color: {ACCENT};
                color: {TEXT_PRIMARY};
            }}
        """)

    # ── Drag events ────────────────────────────────────────────────────────────
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setStyleSheet(self.styleSheet().replace(
                f"border: 1px dashed {BORDER_DASHED}",
                f"border: 1px dashed {ACCENT}",
            ))
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self._reset_border()

    def dropEvent(self, event: QDropEvent):
        self._reset_border()
        urls = event.mimeData().urls()
        if not urls:
            return
        for url in urls:
            path = url.toLocalFile()
            if path:
                self.fileAccepted.emit(path)
        event.acceptProposedAction()

    def _reset_border(self):
        self.setStyleSheet(self.styleSheet().replace(
            f"border: 1px dashed {ACCENT}",
            f"border: 1px dashed {BORDER_DASHED}",
        ))


class RobotDog(QLabel):
    """Spot — the Court Clerk's robotic companion. Displays state via emoji."""

    _STATES: dict[str, tuple[str, str]] = {
        "idle":    ("\U0001f415",         f"color: {TEXT_MUTED};"),          # 🐕
        "running": ("\U0001f415\U0001f4a8", f"color: {ACCENT};"),            # 🐕💨
        "error":   ("\U0001f9ba",         "color: #e05c5c;"),                # 🩺
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.setFixedWidth(44)
        font = QFont()
        font.setPixelSize(22)
        self.setFont(font)
        self.set_state("idle")

    def set_state(self, state: str):
        """Update the dog emoji and colour for the given state."""
        emoji, style = self._STATES.get(state, self._STATES["idle"])
        self.setText(emoji)
        self.setStyleSheet(style)


class ChatHistory(QTextEdit):
    """Read-only scrolling chat history area."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thinking_anchor: int = -1  # doc position before last 'Thinking…' block
        self.setReadOnly(True)
        self.setStyleSheet(f"""
            QTextEdit {{
                background-color: {BG_SECONDARY};
                color: {TEXT_PRIMARY};
                border: 1px solid {BORDER_DASHED};
                border-radius: 8px;
                padding: 10px;
                font-size: 13px;
                line-height: 1.5;
            }}
            QScrollBar:vertical {{
                background: {BG_PRIMARY};
                width: 6px;
                border-radius: 3px;
            }}
            QScrollBar::handle:vertical {{
                background: {BORDER_DASHED};
                border-radius: 3px;
                min-height: 20px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
        """)
        font = QFont()
        font.setFamilies(["SF Pro Text", "Helvetica Neue", "Arial"])
        font.setPixelSize(13)
        self.setFont(font)

    def append_message(self, sender: str, text: str):
        """Append a formatted message and scroll to the bottom."""
        colour = ACCENT if sender == "Atlas" else TEXT_MUTED
        html = (
            f'<span style="color:{colour}; font-weight:600;">{sender}:</span> '
            f'<span style="color:{TEXT_PRIMARY};">{text}</span>'
        )
        self.append(html)
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())

    def append_thinking(self):
        """Insert an italic 'Thinking…' placeholder; saves position for replacement."""
        cursor = QTextCursor(self.document())
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self._thinking_anchor = cursor.position()
        html = (
            f'<span style="color:{ACCENT}; font-weight:600;">Atlas:</span> '
            f'<span style="color:{TEXT_MUTED}; font-style:italic;">Thinking…</span>'
        )
        self.append(html)
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())

    def replace_thinking(self, text: str):
        """Replace the 'Thinking…' block with the real response."""
        if self._thinking_anchor == -1:
            self.append_message("Atlas", text)
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
            f'<span style="color:{ACCENT}; font-weight:600;">Atlas:</span> '
            f'<span style="color:{TEXT_PRIMARY};">{text}</span>'
        )
        cursor = QTextCursor(self.document())
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertHtml(html)
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())


class ChatInput(QLineEdit):
    """Single-line input field; Enter key sends the message."""

    message_sent = pyqtSignal(str)  # emits the user's text

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPlaceholderText("Ask Atlas something…")
        self.returnPressed.connect(self._send)
        self.setStyleSheet(f"""
            QLineEdit {{
                background-color: {BG_INPUT};
                color: {TEXT_PRIMARY};
                border: 1px solid {BORDER_DASHED};
                border-radius: 8px;
                padding: 10px 14px;
                font-size: 13px;
                selection-background-color: {ACCENT};
            }}
            QLineEdit:focus {{
                border-color: {ACCENT};
            }}
        """)
        font = QFont()
        font.setFamilies(["SF Pro Text", "Helvetica Neue", "Arial"])
        font.setPixelSize(13)
        self.setFont(font)

    def _send(self):
        text = self.text().strip()
        if not text:
            return
        self.message_sent.emit(text)
        self.clear()


class TitleBar(QWidget):
    """Frameless title bar: app name + role on the left, Spot on the right."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._drag_pos = QPoint()
        self.setFixedHeight(44)
        self.setStyleSheet(f"background-color: {BG_PRIMARY};")

        row = QHBoxLayout(self)
        row.setContentsMargins(14, 0, 14, 0)
        row.setSpacing(0)

        # Left column: app name + subtitle
        name_col = QWidget()
        name_col.setStyleSheet("background: transparent;")
        name_stack = QVBoxLayout(name_col)
        name_stack.setContentsMargins(0, 0, 0, 0)
        name_stack.setSpacing(0)

        title_lbl = QLabel("ATLAS")
        title_lbl.setStyleSheet(
            f"color: {ACCENT}; font-size: 12px; font-weight: 700; letter-spacing: 3px;"
        )
        sub_lbl = QLabel("Court Clerk")
        sub_lbl.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 9px; letter-spacing: 1px;"
        )
        name_stack.addWidget(title_lbl)
        name_stack.addWidget(sub_lbl)

        # Right: Robot Dog companion
        self._dog = RobotDog()

        row.addWidget(name_col)
        row.addStretch()
        row.addWidget(self._dog)

    @property
    def dog(self) -> RobotDog:
        return self._dog

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.window().frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and not self._drag_pos.isNull():
            self.window().move(event.globalPosition().toPoint() - self._drag_pos)


class AtlasWindow(QMainWindow):
    """Main Atlas application window."""

    WINDOW_WIDTH  = 450
    WINDOW_HEIGHT = 550

    def __init__(self):
        super().__init__()
        self._workers: list[QThread] = []  # keep thread refs alive until finished
        self._robot_dog: RobotDog | None = None
        self._build_window()
        self._build_ui()

    # ── Window setup ───────────────────────────────────────────────────────────
    def _build_window(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.resize(self.WINDOW_WIDTH, self.WINDOW_HEIGHT)
        self.setMinimumSize(self.WINDOW_WIDTH, self.WINDOW_HEIGHT)

        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor(BG_PRIMARY))
        self.setPalette(palette)
        self.setStyleSheet(f"background-color: {BG_PRIMARY};")

        # Centre on screen
        screen = QApplication.primaryScreen().availableGeometry()
        x = (screen.width()  - self.WINDOW_WIDTH)  // 2
        y = (screen.height() - self.WINDOW_HEIGHT) // 2
        self.move(x, y)

    # ── UI layout ──────────────────────────────────────────────────────────────
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Title bar (drag handle + Spot)
        self._title_bar = TitleBar(self)
        self._robot_dog = self._title_bar.dog
        root_layout.addWidget(self._title_bar)

        # Content area
        content = QWidget()
        content.setStyleSheet(f"background-color: {BG_PRIMARY};")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(16, 12, 16, 16)
        content_layout.setSpacing(12)
        root_layout.addWidget(content)

        # Chat history
        self._chat_history = ChatHistory()
        self._chat_history.append_message("Clerk Atlas", WELCOME_MSG)

        # Drag-and-drop area (top section)
        self._drop_area = DragDropArea()
        self._drop_area.fileAccepted.connect(self._on_file_accepted)
        content_layout.addWidget(self._drop_area)

        # Chat history (middle section)
        content_layout.addWidget(self._chat_history, stretch=1)

        # Chat input (bottom section)
        self._chat_input = ChatInput()
        self._chat_input.message_sent.connect(self._on_message_sent)
        content_layout.addWidget(self._chat_input)

    # ── Signal handlers ────────────────────────────────────────────────────────
    def _on_file_accepted(self, path: str):
        """Fires when DragDropArea.fileAccepted is emitted."""
        name = Path(path).name
        # Immediate clerk dispatch message
        self._chat_history.append_message(
            "Clerk Atlas", f"Spot! Retrieve! Scanning {name}\u2026"
        )
        self._chat_history.append_thinking()

        # Dog goes running immediately (main thread, responsive)
        self._robot_dog.set_state("running")

        worker = ClerkWorker(path)
        worker.summaryReady.connect(self._on_summary_ready)
        worker.dogStatus.connect(self._robot_dog.set_state)   # 'idle' on finish
        worker.error_occurred.connect(self._on_worker_error)
        self._start_worker(worker)

    def _on_message_sent(self, text: str):
        self._chat_history.append_message("You", text)
        self._chat_history.append_thinking()
        worker = ChatWorker(text)
        worker.response_ready.connect(self._on_summary_ready)
        worker.error_occurred.connect(self._on_worker_error)
        self._start_worker(worker)

    def _start_worker(self, worker: QThread):
        worker.finished.connect(
            lambda: self._workers.remove(worker) if worker in self._workers else None
        )
        self._workers.append(worker)
        worker.start()

    def _on_summary_ready(self, text: str):
        self._chat_history.replace_thinking(text)

    def _on_worker_error(self, error: str):
        self._robot_dog.set_state("error")
        self._chat_history.replace_thinking(f"\u26a0\ufe0f {error}")

    # ── Keyboard shortcuts ─────────────────────────────────────────────────────
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)


# ─── Entry point ──────────────────────────────────────────────────────────────
def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Atlas")
    app.setStyle("Fusion")

    # Apply a dark Fusion base palette so native widgets inherit the theme
    dark_palette = QPalette()
    dark_palette.setColor(QPalette.ColorRole.Window,          QColor(BG_PRIMARY))
    dark_palette.setColor(QPalette.ColorRole.WindowText,      QColor(TEXT_PRIMARY))
    dark_palette.setColor(QPalette.ColorRole.Base,            QColor(BG_SECONDARY))
    dark_palette.setColor(QPalette.ColorRole.AlternateBase,   QColor(BG_INPUT))
    dark_palette.setColor(QPalette.ColorRole.ToolTipBase,     QColor(TEXT_PRIMARY))
    dark_palette.setColor(QPalette.ColorRole.ToolTipText,     QColor(TEXT_PRIMARY))
    dark_palette.setColor(QPalette.ColorRole.Text,            QColor(TEXT_PRIMARY))
    dark_palette.setColor(QPalette.ColorRole.Button,          QColor(BG_SECONDARY))
    dark_palette.setColor(QPalette.ColorRole.ButtonText,      QColor(TEXT_PRIMARY))
    dark_palette.setColor(QPalette.ColorRole.Highlight,       QColor(ACCENT))
    dark_palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
    app.setPalette(dark_palette)

    window = AtlasWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
