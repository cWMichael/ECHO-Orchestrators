# ECHO Control UI

Dünne Gradio-Oberfläche für den Orchestrator. Logik bleibt in FastAPI.

## Start

**Desktop (empfohlen):** Doppelklick auf `ECHO_Orchestrator_Start.exe`  
(Desktop nach `uv run python build_launcher.py`, oder `dist\ECHO_Orchestrator_Start.exe`)

Startet Backend (:8020) + Gradio UI (:7860), öffnet den Browser erst nach Health-Check, Logs unter `logs/launcher/`, `logs/backend/`, `logs/ui/`.

Voraussetzung einmalig im Projekt: `uv sync` (`.venv` muss existieren).  
Projekt-Pfad: `echo_project_root.txt` neben der EXE (vom Build), oder `ECHO_PROJECT_ROOT`.

Dry-run (nur Port-Check): `uv run python launcher.py --dry-run`

**Entwicklung / ohne EXE:**

```powershell
cd E:\Projects\ECHO-Orchestrators\ECHO-Orchestrators
uv sync
uv run python launcher.py
```

Browser: http://127.0.0.1:7860

## Ablauf (vollständig in der UI)

1. **Zielprojekt wählen** (Dropdown → `POST /api/v1/projects/active`)
2. **Anforderung im Chat** eingeben → `POST /api/v1/plan` (Planner / Gate 0)
3. **Plan prüfen** → **Plan freigeben** oder ablehnen → Tasks werden eingereicht
4. Pro Task:
   - **Gate 1** — Worker freigeben oder ablehnen (`POST /api/v1/tasks/{id}/approve`)
   - Live-Status oben (Polling alle 3 s)
   - **Gate 2** — Diff im Textfeld prüfen, dann Commit oder Verwerfen (`POST /api/v1/tasks/{id}/approve-diff`)
5. **Ergebnis-Panel** — Status, Commit-Meldung, Branch, geänderte Dateien
6. **Task-History** unten (`GET /api/v1/tasks`)

## Manueller Test (ohne Terminal)

1. Doppelklick `ECHO_Orchestrator_Start.exe` (oder `uv run python launcher.py`)
2. Browser öffnet http://127.0.0.1:7860
3. API-Status oben muss „API OK“ zeigen
4. Projekt `echo_c_ki` wählen
5. Chat: z. B. „Erstelle eine Health-Check-Route GET /api/v1/status“
6. Plan lesen → **Plan freigeben (Gate 0)**
7. **Gate 1: Worker starten** — warten bis Diff erscheint
8. Diff prüfen → **Gate 2: Commit + Push** oder Verwerfen
9. Ergebnis-Panel und Chat prüfen (Commit-Hash in Meldung, Dateiliste)

Bei Fehlern: Meldung im Chat; Backend-Log unter `logs/backend/`.

## Konfiguration

| Variable | Default |
|---|---|
| `ECHO_PROJECT_ROOT` | (Launcher-Default) — Pfad zum Orchestrator-Repo |
| `ECHO_API_URL` | `http://127.0.0.1:8020` |
| `ECHO_UI_PORT` | `7860` |
| `ECHO_REVIEWER` | `Michael` |

Zielprojekte: `projects.json` (Pfade anpassen/erweitern).

## CLI-Alternative

```powershell
uv run python run_pipeline.py --natural "Deine Anforderung"
```
