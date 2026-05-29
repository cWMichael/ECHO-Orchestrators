# ECHO Desktop V1 — UI-Plan

Kurzplan für den PySide6-Prototyp. Ein Prozess, direkte Imports, kein HTTP.

**Security / Runtime:** Architekturregeln, Audit pro Komponente, Ollama-Localhost-Policy und empfohlener Startweg stehen in [SECURITY_RUNTIME.md](SECURITY_RUNTIME.md). Alltag: nur `start_desktop.cmd`; `launcher.py`, Gradio und FastAPI sind deprecated (frozen, nicht entfernt).

## Layout

```
+----------------------------------------------------------+
| [Projekt ▼]  [Neu laden]  Pfad…     Status: idle         |
+-------------+--------------------------------------------+
| Chat        | Plan / Task output                         |
| (Verlauf)   | Gate 0 / 1 / 2 Buttons                   |
|             | Diff (monospace, read-only)                |
| [Eingabe]   | Live Log (append-only, Timestamps)         |
| [Senden]    |                                            |
+-------------+--------------------------------------------+
```

Links: `ChatPanel` — NL-Eingabe, Verlauf.  
Rechts oben: `PlanPanel` — Planner- und Task-Zusammenfassung.  
Darunter: `GateButtons` — Gate 0 (Plan), Gate 1 (Worker), Gate 2 (Diff/Commit).  
Diff: `DiffView`.  
Unten: `LogView`.

## Komponenten

| Modul | Aufgabe |
|---|---|
| `desktop/app.py` | `QApplication`, CWD = Projektroot, `python -m desktop.app` |
| `desktop/main_window.py` | Layout, Session-State via Bridge, Signal-Wiring |
| `desktop/orchestrator_bridge.py` | QThread + asyncio, ruft `OrchestratorService` auf |
| `desktop/signals.py` | Qt-Signals UI ← Hintergrund |
| `desktop/widgets/*` | Chat, Projekt, Plan, Diff, Log, Gates |
| `orchestrator/service.py` | Gate-Logik aus Routern, ohne FastAPI |

## Signalfluss

```
UI (Senden)
  → OrchestratorBridge.create_plan()
  → QThread: asyncio.run(service.create_plan())
  → plan_ready / plan_failed → PlanPanel, Chat, Status

Gate 0 Approve
  → approve_plan() → submit_task() pro PlannedTask
  → tasks_submitted → Gate 1 aktiv

Gate 1 Approve
  → approve_task() → Worker.execute() → git diff
  → task_updated, diff_updated → DiffView, Gate 2

Gate 2 Approve
  → approve_diff() → commit_and_push
  → task_updated → PlanPanel, Status completed
```

Regel: ein Task zur Zeit. `AsyncRunner` blockiert parallele Aufrufe.

## Imports aus bestehendem Code

| Bereich | Module |
|---|---|
| Planner | `planner.Planner`, `models.PlanRequest`, `PlanResult` |
| Tasks / Gates | Logik aus `core_router` → `orchestrator/service.py` |
| Plan-Gate | Logik aus `planner_router` → `orchestrator/service.py` |
| Projekte | `project_registry.load_projects`, `resolve_project_path` |
| Config | `config.get_settings`, `set_project_root_override` |
| Worker | `workers/*` via `_get_worker()` |
| Git | `git_manager.GitManager` |
| Persistenz | `task_store.get_store()` |

Nicht angefasst in V1: `launcher.py`, `control_ui.py`, `main.py`, FastAPI-Router.

## Start

```cmd
start_desktop.cmd
```

oder:

```cmd
uv run python -m desktop.app
```

## Abhängigkeiten

- `pyside6>=6.6` in `pyproject.toml`
- `.env` mit `PROJECT_ROOT` (oder Projekt per Dropdown wählen)
- Ollama optional: Planner/Worker liefern Fehler ins Log wenn offline
