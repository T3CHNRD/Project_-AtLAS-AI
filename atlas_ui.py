import sys
from pathlib import Path

import requests
from PyQt6.QtCore import Qt, QPoint, QThread, pyqtSignal
from PyQt6.QtGui import (
    QColor, QPalette, QFont, QDragEnterEvent, QDropEvent, QTextCursor,
)
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
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
    "Atlas: Good morning. The archives are ready. "
    "Hand me a file, or ask me a question."
)

OLLAMA_URL  = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.2"


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


# ─── Ollama Worker ────────────────────────────────────────────────────────────

class OllamaWorker(QThread):
    """Sends a prompt to Ollama on a background thread and emits the response."""

    response_ready = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(self, prompt: str, parent=None):
        super().__init__(parent)
        self._prompt = prompt

    def run(self):
        try:
            resp = requests.post(
                OLLAMA_URL,
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": self._prompt,
                    "stream": False,
                },
                timeout=120,
            )
            resp.raise_for_status()
            text = resp.json().get("response", "").strip()
            self.response_ready.emit(text)
        except requests.exceptions.ConnectionError:
            self.error_occurred.emit(
                "Could not reach Ollama. Is it running at http://localhost:11434?"
            )
        except Exception as exc:  # noqa: BLE001
            self.error_occurred.emit(str(exc))


class DropZone(QLabel):
    """A drag-and-drop target that accepts files and reports their paths."""

    file_dropped = pyqtSignal(str)  # emits local file path

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setText("Drop files here")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setAcceptDrops(True)
        self.setMinimumHeight(100)
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
                self.file_dropped.emit(path)
        event.acceptProposedAction()

    def _reset_border(self):
        self.setStyleSheet(self.styleSheet().replace(
            f"border: 1px dashed {ACCENT}",
            f"border: 1px dashed {BORDER_DASHED}",
        ))


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
    """Custom minimal title bar that enables window dragging."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self._drag_pos = QPoint()
        self.setFixedHeight(36)
        self.setStyleSheet(f"background-color: {BG_PRIMARY};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 0, 0, 0)
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        label = QLabel("Atlas")
        label.setStyleSheet(f"""
            color: {ACCENT};
            font-size: 13px;
            font-weight: 600;
            letter-spacing: 2px;
        """)
        layout.addWidget(label)

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
        self._workers: list[OllamaWorker] = []  # keep refs alive until threads finish
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

        # Title bar (drag handle)
        self._title_bar = TitleBar(self)
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
        self._chat_history.append_message("Atlas", WELCOME_MSG.replace("Atlas: ", ""))

        # Drop zone (top section)
        self._drop_zone = DropZone()
        self._drop_zone.file_dropped.connect(self._on_file_dropped)
        content_layout.addWidget(self._drop_zone)

        # Chat history (middle section)
        content_layout.addWidget(self._chat_history, stretch=1)

        # Chat input (bottom section)
        self._chat_input = ChatInput()
        self._chat_input.message_sent.connect(self._on_message_sent)
        content_layout.addWidget(self._chat_input)

    # ── Ollama signal handlers ─────────────────────────────────────────────────
    def _on_file_dropped(self, path: str):
        name = Path(path).name
        self._chat_history.append_message("You", f"[File dropped] {name}")

        text = extract_text(path)
        if not text.strip() or text.startswith("[extraction error"):
            self._chat_history.append_message(
                "Atlas",
                f"I couldn\'t extract text from \u2018{name}\u2019. "
                "Supported formats: PDF, DOCX, TXT, MD, CSV, JSON, YAML.",
            )
            return

        snippet = text[:4000]  # keep within model context
        prompt = (
            "You are a meticulous archivist called Atlas. "
            "Summarize the following document in exactly 3 concise sentences, "
            "focusing on its key subject, purpose, and any notable details.\n\n"
            f"Document:\n{snippet}"
        )
        self._chat_history.append_thinking()
        self._dispatch_worker(prompt)

    def _on_message_sent(self, text: str):
        self._chat_history.append_message("You", text)
        self._chat_history.append_thinking()
        self._dispatch_worker(text)

    def _dispatch_worker(self, prompt: str):
        worker = OllamaWorker(prompt)
        worker.response_ready.connect(self._on_worker_response)
        worker.error_occurred.connect(self._on_worker_error)
        worker.finished.connect(lambda: self._workers.remove(worker) if worker in self._workers else None)
        self._workers.append(worker)
        worker.start()

    def _on_worker_response(self, text: str):
        self._chat_history.replace_thinking(text)

    def _on_worker_error(self, error: str):
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
