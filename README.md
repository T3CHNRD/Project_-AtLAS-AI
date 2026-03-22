# Atlas AI

> **Privacy-first. Fully local. Radically organized.**

Atlas is an autonomous AI file organizer for macOS that acts as your personal *Head Librarian* — reading, classifying, and organizing your files entirely on-device. No cloud uploads. No telemetry. Your data never leaves your machine.

---

## What Atlas Does

Atlas watches your filesystem and uses a locally-running LLM (via Ollama) to understand the *content* of your files — not just their names — and intelligently organizes them into a coherent, human-readable archive structure. You interact with it through a sleek, minimal desktop UI and can ask it questions about your own files in plain language.

---

## Core Principles

| Principle | Description |
|---|---|
| **Privacy-first** | All inference runs locally via Ollama. Nothing is sent to external APIs. |
| **Autonomous** | Drop files in; Atlas handles the rest. Rules are learned, not hardcoded. |
| **Transparent** | Every action Atlas takes is logged and explainable via the chat interface. |
| **Non-destructive** | Atlas never deletes files — it copies or moves them with your confirmation. |

---

## Tech Stack

### UI Layer
- **[PyQt6](https://pypi.org/project/PyQt6/)** — Native macOS desktop interface, frameless dark-themed window
- Drag-and-drop file ingestion with real-time chat feedback

### AI / Backend Layer
- **[Ollama](https://ollama.com/)** — Local LLM runtime (Dockerized). Runs models like `llama3`, `mistral`, or `phi3` entirely on-device
- **[OpenClaw](https://github.com/OpenClaw)** — Local document parsing and semantic extraction pipeline, Dockerized alongside Ollama

### Sync & Storage
- **iCloud Drive** — Optional sync target for organized output directories (user-controlled)
- **SQLite** — Local index of classified files; no external database

### Infrastructure
- **Docker Compose** — Manages the Ollama + OpenClaw backend services as a local stack
- **Python 3.11+** — Core application runtime

---

## Architecture Overview

```
┌─────────────────────────────────────┐
│           Atlas UI (PyQt6)          │  ← Frameless macOS window
│   Drag & Drop  │  Chat Interface    │
└────────────────┬────────────────────┘
                 │ REST / local socket
┌────────────────▼────────────────────┐
│         Atlas Core (Python)         │  ← Orchestrator & file logic
│   File Watcher │ Rule Engine │ DB   │
└────────┬───────┴──────────┬─────────┘
         │                  │
┌────────▼────────┐  ┌──────▼──────────┐
│  Ollama (Docker)│  │OpenClaw (Docker) │
│  Local LLM API  │  │ Doc Parser/OCR   │
└─────────────────┘  └─────────────────┘
         │
    [iCloud Drive sync — optional]
```

---

## Project Structure (Phase 1)

```
Atlas AI/
├── atlas_ui.py          # PyQt6 desktop UI
├── README.md
├── .gitignore
└── (Phase 2+)
    ├── atlas_core/      # File watcher, classifier, rule engine
    ├── docker-compose.yml  # Ollama + OpenClaw services (gitignored locally)
    ├── models/          # Prompt templates
    └── tests/
```

---

## Getting Started

### Prerequisites
- macOS 13+ (Ventura or later recommended)
- Python 3.11+
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (for Ollama + OpenClaw backend)

### Setup

```bash
# 1. Clone the repo
git clone https://github.com/your-handle/atlas-ai.git
cd "Atlas AI"

# 2. Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install Python dependencies
pip install PyQt6

# 4. Launch the UI
python atlas_ui.py
```

> Backend services (Ollama, OpenClaw) will be configured in Phase 2 via Docker Compose.

---

## Roadmap

- [x] **Phase 1** — Foundational UI, project scaffold
- [ ] **Phase 2** — Docker backend, Ollama integration, file classification
- [ ] **Phase 3** — Autonomous file watcher, rule engine, move/copy actions
- [ ] **Phase 4** — iCloud sync output, natural language file queries
- [ ] **Phase 5** — Plugin system, custom model support

---

## Privacy Guarantee

Atlas is architecturally incapable of sending your file contents to any external service. The LLM inference layer is a local Docker container with no outbound network access required. You can run Atlas fully air-gapped.

---

## License

MIT — See `LICENSE` for details.
