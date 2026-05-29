# ECHO Orchestrator

Deterministische KI-Entwicklungsplattform mit Human-in-the-Loop. Dieses Repo ist der **Control Layer** (Planner, Worker, Gates, Git-Steuerung). Zielprojekte liegen in separaten Verzeichnissen (`projects.json`).

## Architektur

```
PySide6 Desktop-App  ←  Primäre Benutzeroberfläche
        │
        └── FastAPI Backend  →  http://127.0.0.1:8020  (optional, Infrastruktur)
```

| Komponente | Status | Einstieg |
|---|---|---|
| **`desktop/app.py`** | **Hauptsystem** | `start_desktop.cmd` |
| `main.py` (FastAPI/uvicorn) | Infrastrukturmodul | `uv run uvicorn main:app ...` |
| `control_ui.py` (Gradio) | **DEPRECATED** | nicht verwenden |
| `launcher.py` | **DEPRECATED** | nicht verwenden |

**PySide6 ist das Hauptsystem.** FastAPI bleibt als Infrastrukturmodul für Remote-Control, externe Worker, API-Zugriffe und zukünftige verteilte Szenarien (CrewAI, Mobile, etc.) — aber nicht mehr als primäre Bedienoberfläche.

## Schnellstart

```cmd
cd /d E:\Projects\ECHO-Orchestrators\ECHO-Orchestrators
uv sync
start_desktop.cmd
```

## Dependencies

Aktive Dependencies (`uv sync`):

- `pyside6` — primäre Desktop-UI
- `fastapi` + `uvicorn` — API-Infrastruktur
- `anthropic` — KI-Backend
- `httpx`, `pydantic`, `pydantic-settings` — HTTP-Client, Validierung

Gradio ist **nicht** mehr in den aktiven Dependencies. Wer die Legacy-UI trotzdem braucht:

```cmd
uv sync --extra legacy-ui
```

## FastAPI Backend (optional)

Das Backend läuft unabhängig vom Desktop und stellt die REST-API bereit:

```cmd
uv run uvicorn main:app --host 127.0.0.1 --port 8020
```

Endpunkte: `GET /health`, `/api/v1/tasks`, `/api/v1/plan`, `/api/v1/projects`  
Docs: `http://127.0.0.1:8020/docs`

## Logs

| Pfad | Inhalt |
|---|---|
| `logs/launcher/launcher.log` | Launcher-Sessions (Legacy) |
| `logs/backend/backend.log` | uvicorn-Stdout |

## Fehlerdiagnose

| Symptom | Prüfen |
|---|---|
| Desktop startet nicht | PySide6 installiert? → `uv sync` |
| Port 8020 belegt | `netstat -ano \| findstr 8020` |
| Backend-Timeout | `logs/backend/backend.log`, `.env` prüfen |
| venv fehlt | `uv sync` im Projektordner |

## Umgebungsvariablen

| Variable | Default | Bedeutung |
|---|---|---|
| `ECHO_PROJECT_ROOT` | Skript-Verzeichnis | Pfad zum Orchestrator-Repo |
| `ECHO_API_URL` | `http://127.0.0.1:8020` | Desktop → Backend |

## Weitere Dokumentation

- `SECURITY_RUNTIME.md` — Security-Audit, Ollama-Localhost-Policy
- `DESKTOP_ARCHITECTURE_PROPOSAL.md` — Desktop-Architektur
- `SESSION_LOG.md` — Entwicklungs-Sessions
