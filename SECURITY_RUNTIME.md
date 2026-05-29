# ECHO Orchestrator — Security-aware Desktop Runtime

Stand: 2026-05-29. Gilt für den PySide6-Desktop-Pfad als Zielarchitektur. Legacy-Komponenten (Launcher, Gradio, FastAPI) bleiben im Repo, sind aber für den Alltag eingefroren.

---

## Architekturregeln

### Vermeiden

- automatisches Browser-Öffnen
- versteckte Hintergrundprozesse (`CREATE_NO_WINDOW`, unsichtbare Subprozesse)
- mehrere Runtime-Prozesse (Launcher + uvicorn + Gradio)
- Port-Listener, wenn kein zwingender Grund
- Self-Recovery-Daemons und aggressive Health-Monitoring-Schleifen
- `taskkill`-Automatisierung zur Prozessbereinigung
- EXE-Packer / PyInstaller (vorerst)

### Bevorzugen

- ein Python-Hauptprozess (`python -m desktop.app`)
- PySide6-Desktop-UI
- direkte Imports (`OrchestratorService`, Worker, Planner)
- lokale JSON/JSONL-Logs unter `logs/`
- manueller Start (`start_desktop.cmd`)
- keine Netzwerkabhängigkeit außer Ollama auf `127.0.0.1` / `localhost` / `::1`

**Ziel:** Die App verhält sich wie eine normale lokale Desktop-Anwendung — ruhige, nachvollziehbare Runtime, kein DevOps-/Agent-Labor.

---

## Audit-Ergebnis (Kurz)

| Komponente | Status | Anmerkung |
|---|---|---|
| `desktop/` + `start_desktop.cmd` | **compliant** | Ein Prozess, kein HTTP-Server, direkte Imports |
| `orchestrator/service.py` | **compliant** | Kein HTTP, Gate-Logik in-process |
| `base_worker.py`, `planner.py` | **compliant** | httpx nur gegen `settings.ollama_base_url` (localhost erzwungen) |
| `config.py` | **compliant** (nach Fix) | Default `127.0.0.1`, Ollama-Validator blockiert Remote-Hosts |
| `launcher.py` | **non-compliant** | Multi-Prozess, taskkill, Browser, Monitoring — **DEPRECATED** |
| `control_ui.py` (Gradio) | **non-compliant** (Legacy) | Port 7860, httpx → FastAPI — **eingefroren** |
| `main.py` (FastAPI/uvicorn) | **non-compliant** (Legacy) | Port 8020, CORS — **eingefroren** |
| `build_launcher.py` | **non-compliant** | PyInstaller + Launcher-Deployment — **eingefroren** |
| `run_pipeline.py` | **non-compliant** (Dev-Tool) | httpx gegen ECHO-API, nicht für Desktop-Alltag |

---

## Detailtabelle

| Komponente | Prozesse | Ports | Netzwerk | Enterprise-Risiko | Empfehlung |
|---|---|---|---|---|---|
| **`start_desktop.cmd` → `desktop/app.py`** | 1× Python (+ interne `QThread` für asyncio) | keine | Ollama outbound zu localhost | **niedrig** | **Standard-Startweg** |
| **`desktop/orchestrator_bridge.py`** | In-Process-Thread, kein Subprozess | — | indirekt Ollama via Service | niedrig | beibehalten |
| **`orchestrator/service.py`** | in-process | — | Ollama via Worker/Planner | niedrig | beibehalten |
| **`base_worker.py` / `planner.py`** | in-process | — | `POST {OLLAMA_BASE_URL}/api/generate` | niedrig (bei localhost) | beibehalten; URL nicht auf Remote setzen |
| **`config.py`** | — | — | Defaults + Validator | mittel wenn `.env` mit `HOST=0.0.0.0` | `.env` auf `127.0.0.1` prüfen |
| **`launcher.py`** | 1 Launcher + 2 Kinder (uvicorn, Gradio) | 8020, 7860 | Health-Checks, Browser-Open | **hoch** — untypisches Agent-Verhalten | nicht für Alltag; nur Legacy-Debug |
| **`main.py` + uvicorn** | 1 Server | 8020 (Bind abhängig von `HOST`) | CORS, REST API | **mittel–hoch** bei `0.0.0.0` | nicht starten im Desktop-Betrieb |
| **`control_ui.py` + Gradio** | 1 Server | 7860 (`127.0.0.1`) | httpx → `:8020` | mittel | nicht starten im Desktop-Betrieb |
| **`build_launcher.py`** | PyInstaller-Build + EXE | — | deployt Launcher-Pfad | hoch (Packer + Multi-Prozess) | nicht bauen / nicht verteilen |
| **`run_pipeline.py`** | 1 Client | — | httpx → ECHO-API | niedrig (nur wenn API läuft) | reines Dev-/CI-Tool |

---

## Ollama-Bewertung

| Frage | Ergebnis |
|---|---|
| Konfigurierte URL | `OLLAMA_BASE_URL` in `.env` / `config.py` — Default **`http://127.0.0.1:11434`** |
| Code erzwingt localhost? | **Ja** — `field_validator` auf `ollama_base_url` (127.0.0.1, localhost, ::1) |
| Remote-Ollama möglich? | **Nein** — ungültige Hosts werfen `ValueError` beim Settings-Laden |
| Bindet ECHO an `0.0.0.0`? | **Nur Legacy-FastAPI**, wenn `HOST=0.0.0.0` in `.env` und `main.py`/`uvicorn` direkt gestartet wird. Launcher spawn uvicorn mit `--host 127.0.0.1`. **Desktop-Pfad startet keinen Server.** |
| FastAPI/Gradio bei Desktop-Start? | **Nein** — `desktop/app.py` importiert weder uvicorn noch Gradio |

**Ollama bleibt lokal: Ja** — solange `OLLAMA_BASE_URL` auf localhost zeigt (Standard + Validator). Externe Ollama-Instanzen werden abgewiesen.

### httpx-Aufrufe (Ollama-relevant)

| Modul | Ziel | localhost-only |
|---|---|---|
| `base_worker.py` | `settings.ollama_base_url` + `/api/generate` | ja (via Validator) |
| `planner.py` | `settings.ollama_base_url` + `/api/generate` | ja (via Validator) |
| `control_ui.py` | `ECHO_API_URL` (FastAPI :8020) | Legacy, nicht Desktop-Pfad |
| `run_pipeline.py` | ECHO-API | Dev-Tool |

---

## Netzwerk-Bindings (nur wenn Legacy-Server laufen)

| Dienst | Bind-Adresse | Port | Gestartet durch |
|---|---|---|---|
| FastAPI (uvicorn) | `127.0.0.1` | 8020 | `launcher.py` (explizit) |
| FastAPI (uvicorn) | `HOST` aus `.env` (aktuell oft `0.0.0.0`) | 8020 | direktes `python main.py` / manuelles uvicorn |
| Gradio UI | `127.0.0.1` | 7860 | `launcher.py` → `control_ui.py` |
| PySide6 Desktop | — | — | kein Listener |

**Desktop-Alltag:** keine offenen ECHO-Ports. Nur Ollama (externer Dienst, typisch `:11434` auf localhost) muss erreichbar sein.

---

## Deprecated / eingefroren

| Artefakt | Status |
|---|---|
| `launcher.py` | DEPRECATED — Multi-Prozess-Orchestrator, Browser, taskkill, Health-Loop |
| `control_ui.py` (Gradio :7860) | eingefroren — Web-UI-Ersatz durch PySide6 |
| `main.py` (FastAPI :8020) | eingefroren — API bleibt für Tests/Dev, nicht Runtime |
| `build_launcher.py` / PyInstaller-EXE | eingefroren — kein Packer-Betrieb vorgesehen |
| `README.md`-Schnellstart via `launcher.py` | überholt — siehe unten |

Nicht entfernt (bewusst): Router-Code, Gradio, FastAPI — Referenz und schrittweise Migration, kein Alltags-Entry.

---

## Empfohlener Startweg

```cmd
cd E:\Projects\ECHO-Orchestrators\ECHO-Orchestrators
start_desktop.cmd
```

Entspricht: `uv run python -m desktop.app`

Voraussetzungen:

- `uv sync` (PySide6 installiert)
- `.env` mit `PROJECT_ROOT` (oder Projekt per Dropdown)
- Ollama lokal auf Port 11434 (optional — Fehler landen im Log)

**Nicht** für den Alltag: `launcher.py`, `build_launcher.py`, manuelles uvicorn/Gradio.

---

## CORS (Legacy FastAPI)

In `config.py`: `cors_origins` default `["http://localhost:3000", "http://127.0.0.1:7860"]`.

Relevant nur wenn FastAPI läuft. Desktop-Pfad nutzt CORS nicht. Für Enterprise: FastAPI nicht starten → CORS irrelevant.

---

## Durchgeführte Minimal-Fixes (Audit 2026-05-29)

1. `config.py`: `host`-Default `127.0.0.1`, `ollama_base_url`-Default `http://127.0.0.1:11434`, Validator gegen Remote-Ollama
2. `launcher.py`: DEPRECATED-Banner im Header (kein Refactor)
3. `.env.example`: localhost-only Defaults dokumentiert

**Offen / manuell prüfen:** Bestehende `.env` kann noch `HOST=0.0.0.0` enthalten — für Legacy-FastAPI auf `127.0.0.1` setzen, wenn uvicorn überhaupt noch genutzt wird.
