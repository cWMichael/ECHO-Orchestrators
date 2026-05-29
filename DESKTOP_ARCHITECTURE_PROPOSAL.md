# ECHO Desktop — Architekturvorschlag

## Problem mit aktuellem Ansatz

ECHO läuft heute als verteiltes Mini-System: `launcher.py` startet uvicorn auf Port 8020 und Gradio auf Port 7860, öffnet den Browser, überwacht Health-Checks, verwaltet Lock-Dateien und Port-Konflikte. Die eigentliche Orchestrierung steckt in Python (`core_router.py`, `planner.py`, `workers/`), wird aber nur über HTTP angesprochen. `control_ui.py` ist eine dünne httpx-Schicht — 600 Zeilen UI-Logik, die Session-State hält und alle 3 Sekunden pollt.

Das funktioniert für Entwicklung. Für den Operator auf einem Firmen-Laptop ist es der falsche Schnitt:

- Zwei lokale Server plus Browser-Tab = mehr Moving Parts, mehr Fehlerquellen (Port belegt, Backend tot, Gradio hängt).
- Kein echtes Desktop-Fenster — der Workflow hängt an localhost und einem Browser-Profil.
- Der Launcher ist fast so komplex wie die Business-Logik (900+ Zeilen Prozess-Management).
- HTTP-Roundtrips zwischen UI und Backend im selben Rechner sind reiner Overhead. Ollama frisst ohnehin RAM und GPU — darüber braucht niemand noch Chromium und zwei uvicorn-Instanzen.

Die Vision: Ein Fenster. Chat links, Plan/Diff/Ergebnis rechts. Doppelklick, fertig. Kein Terminal, kein API-Babysitting.

## Anforderungen

| Anforderung | Priorität |
|---|---|
| Ein lokales Fenster, kein Browser | Pflicht |
| Chat + Plan/Diff/Approve-UI in einem Layout | Pflicht |
| Projekt-Selector, Gate 0/1/2 (Plan / Worker / Diff) | Pflicht |
| Python-Orchestrator direkt anbinden (Planner, Workers, Git, Ollama) | Pflicht |
| Kein HTTP zwischen UI und Orchestrator | Pflicht |
| Windows-Stabilität ohne Admin-Rechte | Pflicht |
| Geringe AV/IT-Reibung (Corporate Laptop) | Hoch |
| Einfacher Start: eine EXE oder ein Doppelklick | Hoch |
| Niedriger RAM/CPU neben Ollama | Hoch |
| Optional Git im Hintergrund nach Diff-Freigabe | Beibehalten |

## Optionenvergleich

| Kriterium | Tauri | PySide6 | Electron | Textual |
|---|---|---|---|---|
| **Windows-Stabilität** | Gut (WebView2 auf Win11), Rust-Shell stabil | Sehr gut, Qt seit Jahrzehnten auf Windows | Gut, aber Chromium-Updates brechen gelegentlich Dinge | Terminal-only, kein natives Fenster-Layout |
| **IT/AV-Reibung** | Mittel — WebView2 meist vorinstalliert, Rust-Binary unbekannt | Niedrig — klassische Desktop-EXE, keine offenen Ports | Hoch — Electron/Chromium wird oft eingeschränkt oder gescannt | Niedrig, aber TUI ≠ Operator-Anforderung |
| **Single EXE / Doppelklick** | Machbar, braucht aber Rust-Build + Python-Bundle oder Sidecar | PyInstaller/Nuitka: etablierter Pfad, eine EXE + ggf. Ordner | electron-builder: großes Paket, oft Python als zweiter Prozess nötig | `python -m textual` — kein echtes Desktop-Produkt |
| **Direkte Python-Integration** | Schlecht — Rust-Host, Python als Sidecar/Subprocess oder IPC | Exzellent — alles importierbar im selben Prozess | Schlecht — Node-Prozess + Python-Backend = wieder Zwei-Prozess-Architektur |
| **Orchestrierung ohne HTTP** | Nur mit Sidecar und IPC (stdin/JSON, Named Pipes) — wieder Indirection | Direkt: `OrchestratorService` als Python-Klasse, asyncio im QThread | Wieder HTTP oder IPC zwischen Electron und Python | Direkt, aber UI zu limitiert |
| **RAM/CPU (idle)** | ~30–50 MB Shell + Python-Prozess separat | ~60–120 MB (ohne QWebEngine) | ~250–400 MB+ (Chromium) | ~20–40 MB |
| **Chat + Split-Panel UX** | HTML/CSS im WebView — flexibel | QSplitter, QTextEdit, QPlainTextEdit, optional QWebEngineView für Diff | Best-in-class Web-UI | Kein echtes Zwei-Spalten-Layout mit Buttons/Diff |
| **Diff-Anzeige** | Monaco/diff2html im WebView — gut | QPlainTextEdit mit Syntax-Highlighting oder QWebEngineView | Monaco, hervorragend | Scrollbare Textbox, kein Side-by-side |
| **Langläufige Worker + responsive UI** | Sidecar-Events über IPC/Tauri-Events | QThread + asyncio (`qasync` oder `asyncio.run_coroutine_threadsafe`) | IPC + Renderer-Prozess | Async ok, UI blockiert bei großen Diffs |
| **Build-Komplexität** | Rust + Node + Python-Bundling | Python-only, PyInstaller | Node + Python, zwei Welten | Minimal, aber falscher UX-Fit |
| **Passung zu ECHO** | Over-engineered für Python-heavy Stack | Natürliche Heimat des bestehenden Codes | Schwerer als nötig, reproduziert Launcher-Problem | Technisch interessant, produktiv unbrauchbar für diese UI |

### Kurzfassung pro Option

**Tauri:** Leichtgewichtige Shell, aber Python bleibt Außenseiter. Entweder Sidecar-Prozess (zweiter Prozess, IPC, wieder Komplexität) oder Python embedden in Rust (aufwändig, selten gepflegt). Für ein Team, das ohnehin in Python denkt, ist das ein Umweg.

**PySide6:** Orchestrator-Logik bleibt Python. UI ist Python. Ein Prozess, ein Event-Loop-Hybrid (Qt + asyncio). Diff kann erstmal als monospace Text reichen; Syntax-Highlighting später nachrüsten. PyInstaller kennt jede IT-Abteilung.

**Electron:** Beste Web-UI, schlechtester Fit für die Anforderungen. RAM-Hunger neben Ollama ist real. Würde fast sicher wieder Python als Subprozess brauchen — dann hat man Electron + Python statt Gradio + uvicorn. Horizontaler Tausch, nicht Vereinfachung.

**Textual:** Für CLI-Tools und Monitoring ok. Kein Projekt-Selector mit Dropdown, kein brauchbarer Diff-Viewer, kein Gate-Workflow mit Buttons in Split-View. Scheitert an der UX-Vision, nicht an der Technik.

## Empfehlung

**Primary: PySide6 (Qt 6)**

Warum: Der gesamte wertvolle Code — `planner.py`, Worker-Pipeline in `core_router.py`, `workers/*`, `git_manager`, `task_store`, `project_registry` — ist Python. PySide6 erlaubt direkten Import statt HTTP. Ein Prozess, ein Fenster, kein Port-Management, kein Browser. Windows-native, AV-freundlicher als Electron, RAM-budget verträglich neben Ollama.

**Fallback: Tauri 2 + Python Sidecar**

Nur sinnvoll, wenn die UI später deutlich web-lastig werden soll (Monaco Editor, komplexe Diff-Ansichten, Markdown-Rendering) und jemand Rust/Frontend-Zeit investiert. Dann Python-Orchestrator als Sidecar-Prozess mit JSON-RPC über stdin/stdout — bewusst einfacher als HTTP, aber immer noch zwei Prozesse. Nicht der Default.

**Nicht empfohlen:** Electron (Gewicht, RAM, IT), Textual (UX-Deckungsgleichheit null).

## Zielarchitektur (konzeptionell)

### Prozessmodell

```
┌─────────────────────────────────────────────────────────┐
│  echo_desktop.exe  (ein Python-Prozess)                 │
│                                                         │
│  ┌──────────────┐    direkte Aufrufe    ┌─────────────┐ │
│  │  Qt UI       │ ◄──────────────────► │ Orchestrator │ │
│  │  (MainWindow)│    Signals/Slots     │ Service      │ │
│  └──────────────┘                      └──────┬──────┘ │
│                                               │         │
│                    asyncio in QThread         │         │
│                                               ▼         │
│              ┌─────────┐  ┌──────────┐  ┌──────────┐  │
│              │ Planner │  │ Workers  │  │GitManager│  │
│              └────┬────┘  └────┬─────┘  └──────────┘  │
└───────────────────┼──────────┼─────────────────────────┘
                    │          │
                    ▼          ▼
              ┌──────────────────────┐
              │ Ollama :11434        │  (extern, bleibt)
              │ Zielprojekt (Git)    │  (project_root)
              └──────────────────────┘
```

**Ein Prozess.** Ollama bleibt extern (läuft ohnehin als Dienst). Kein uvicorn, kein Gradio, kein Launcher mit Port-Inspektion.

### Was passiert mit FastAPI / Gradio / Launcher

| Komponente | Schicksal |
|---|---|
| `main.py` + uvicorn | Entfällt als Runtime-Entry. Router-Logik wird extrahiert, nicht gelöscht. |
| `core_router.py` | HTTP-Decorator und `HTTPException` raus → `OrchestratorService` mit plain async methods. Gate-Logik, Worker-Dispatch, Git-Flow bleiben 1:1. |
| `planner_router.py` | `_pending_plans` + approve-Flow → Methoden auf `OrchestratorService` oder `PlannerService`. |
| `project_router.py` | → `ProjectService` (list/set active), UI ruft direkt auf. |
| `control_ui.py` | Wird ersetzt durch `desktop/` Qt-Modul. Session-State wandert in ViewModel oder MainWindow-Controller. |
| `launcher.py` | Entfällt. Start = `echo_desktop.exe` oder `python -m echo.desktop`. Optional: Pre-Flight-Check ob Ollama erreichbar (ein HTTP-Call nach außen, kein eigener Server). |
| `workers/*`, `planner.py`, `git_manager.py`, `task_store.py`, `models.py`, `config.py` | Bleiben. Keine Änderung am Kern nötig. |

### UI-Schicht

```
QMainWindow
├── QSplitter (horizontal)
│   ├── Links: ChatPanel
│   │     ├── QListWidget / custom MessageList (User/Assistant)
│   │     ├── QLineEdit / QTextEdit (Eingabe)
│   │     └── Senden-Button
│   └── Rechts: WorkPanel
│         ├── ProjectSelector (QComboBox)
│         ├── PlanView (QTextBrowser — Markdown)
│         ├── DiffView (QPlainTextEdit, monospace, scroll)
│         ├── ResultView (QTextBrowser)
│         └── GateButtons (QHBox: Approve/Reject × Gate 0/1/2)
└── StatusBar (Task-Status, Ollama-Reachability)
```

Polling entfällt. Stattdessen: Orchestrator emittiert Qt-Signals bei Statuswechsel (`plan_ready`, `task_status_changed`, `diff_ready`, `worker_finished`). UI reagiert event-driven.

### Orchestrator-Schicht

Neues Modul `orchestrator/service.py` — extrahiert aus den Routern:

```python
class OrchestratorService:
    async def create_plan(self, intent: str, reviewer: str) -> PlanResult: ...
    async def approve_plan(self, plan_id: str, approved: bool, ...) -> list[TaskSubmitResult]: ...
    async def approve_task(self, task_id: str, approved: bool, ...) -> TaskResult: ...
    async def approve_diff(self, task_id: str, approved: bool, ...) -> TaskResult: ...
    def get_task(self, task_id: str) -> TaskStatus: ...
    def get_diff(self, task_id: str) -> DiffInfo: ...
    def list_projects(self) -> dict[str, str]: ...
    def set_active_project(self, name: str) -> ProjectInfo: ...
```

Kein FastAPI, kein httpx zwischen UI und Service. `planner_router.approve_plan` ruft heute intern schon `submit_task` auf — genau dieses Pattern, nur ohne HTTP-Umschlag.

### Worker / Git / Ollama

Unverändert. Workers laufen über `BaseWorker.execute()` → httpx zu Ollama (extern). Git über `GitManager` mit `settings.project_root`. FileWriter schreibt ins Zielprojekt.

Gate-Flow bleibt:
- Gate 0: Plan anzeigen → Approve → Tasks einreichen
- Gate 1: Worker freigeben → Branch + Worker-Lauf
- Gate 2: Diff anzeigen → Commit/Push oder Verwerfen

### Threading-Modell

| Operation | Wo | Mechanismus |
|---|---|---|
| UI-Interaktion | Main Thread | Qt Event Loop |
| Planner (Ollama, 30–120s) | Background | `QThread` + `asyncio.run()` oder `qasync` |
| Worker execute (Ollama + FileWriter) | Background | Gleicher Worker-Thread, nicht UI blockieren |
| Git (branch, diff, commit) | Background | `asyncio.to_thread()` wie heute in `core_router` |
| Status-Updates an UI | Main Thread | `pyqtSignal` von Service/WorkerThread |

Regel: Nie synchron `worker.execute()` im UI-Thread aufrufen. Nie Qt-Widgets aus dem Worker-Thread anfassen — nur Signals.

Langläufige Runs: Progress-Label in StatusBar ("Worker läuft… Task 2/3"). Cancel optional später, nicht Phase 1.

## Migrationspfad (Phasen, nicht implementieren)

### Phase 1 — Orchestrator entkoppeln (Backend-Logik ohne HTTP)

- `OrchestratorService` aus `core_router.py`, `planner_router.py`, `project_router.py` extrahieren.
- FastAPI-Router werden dünne Wrapper (optional, für Übergang) oder deprecated.
- Bestehende pytest-Tests gegen Service-Klasse laufen lassen, nicht gegen HTTP.
- `_pending_plans`, `_task_branches`, `_task_diffs` in Service-Instanz statt Modul-Globals.

Ergebnis: Gleiche Logik, aufrufbar per `await service.approve_task(...)`.

### Phase 2 — Minimales Desktop-Fenster

- `desktop/app.py` mit PySide6: Split-Layout, Chat links, Plan/Diff rechts.
- Projekt-Dropdown wired zu `ProjectService`.
- Gate-Buttons wired zu Service-Methoden.
- Kein Polling — Signals bei Statusänderung.
- Start via `python -m echo.desktop`, noch kein PyInstaller.

Ergebnis: Feature-Parität mit `control_ui.py`, ohne Gradio und ohne localhost:7860.

### Phase 3 — Packaging + Aufräumen

- PyInstaller-Spec: eine EXE, `.venv`-Dependencies gebündelt, Icon, kein Konsolenfenster.
- Optional: Ollama-Reachability-Check beim Start (Dialog wenn nicht erreichbar).
- `launcher.py`, `control_ui.py`, Gradio-Dependency entfernen.
- FastAPI/uvicorn aus Runtime-Dependencies streichen (dev-only behalten falls API-Tests gewünscht).

Ergebnis: Doppelklick → Fenster. Kein Browser, kein Terminal.

### Phase 4 — UX-Härtung (optional)

- Diff-Syntax-Highlighting (QSyntaxHighlighter oder leichtgewichtiges HTML in QTextBrowser).
- Task-History-Panel.
- Tray-Icon + Minimize-to-tray wenn Worker im Hintergrund läuft.
- Settings-Dialog (Ollama-Modell, Reviewer-Name, projects.json Editor).

## Was wegfällt

- **Gradio** (`control_ui.py`) — komplett
- **Gradio HTTP-Server** auf Port 7860
- **FastAPI/uvicorn als Runtime** — Ports 8020, Health-Checks, CORS
- **`launcher.py`** — Prozess-Orchestrierung, Lock-Files, Port-Klassifizierung, Browser-Open
- **httpx-Client in der UI-Schicht** (`EchoApiClient`)
- **3-Sekunden-Polling-Timer** — ersetzt durch Events
- **`gradio`, `uvicorn` aus Produktions-Dependencies**
- **Browser als Pflicht-UI**

Was bleibt im Repo (Bibliothek, nicht Runtime):
- `models.py`, `config.py`, Worker-Code, Git, Task-Store
- Optional FastAPI als dev/test-API hinter Feature-Flag

## Risiken / Offene Punkte

| Risiko | Einschätzung | Mitigation |
|---|---|---|
| PyInstaller-EXE-Größe (80–150 MB mit Qt) | Akzeptabel vs. Electron | `--onedir` statt `--onefile` für schnelleren Start |
| Qt-Lizenz (LGPL) | Dynamically linked = ok für interne Tools | PySide6 ist LGPL, keine Probleme bei korrektem Packaging |
| asyncio + Qt Event Loop | Bekanntes Pattern, `qasync` ist stabil | Worker-Thread isoliert, nicht im Main Thread |
| Diff-UX ohne Web-Engine | Phase 1: Plaintext reicht | Phase 4: QSyntaxHighlighter oder Tauri-Fallback |
| `_task_branches`/`_task_diffs` flüchtig (heute schon) | Bestehendes TODO | In Phase 1 mit in `task_store` persistieren |
| Ollama nicht gestartet | Operator sieht Fehler | Start-Check mit klarer Meldung im Fenster |
| Corporate Proxy blockiert nichts Relevantes | Kein Outbound nötig außer Git Push | Git Push optional, lokal reicht |

**Offen:** Soll die EXE Ollama mitstarten oder nur prüfen? Empfehlung: nur prüfen — Ollama ist oft systemweit installiert und als Dienst konfiguriert.

**Offen:** `--onefile` vs. Ordner-Distribution? Empfehlung: Ordner (`echo_desktop/echo_desktop.exe`) — schnellerer Cold Start, einfacheres Debugging auf Kunden-Laptops.

## Nächster Schritt (wenn User zustimmt)

1. Phase 1 starten: `OrchestratorService` extrahieren, Tests gegen Service schreiben.
2. PySide6 als Dependency in `pyproject.toml` aufnehmen.
3. Phase 2: Skelett `desktop/app.py` mit Split-Layout und Gate-Buttons — Feature-Parität zu `control_ui.py` als Abnahmekriterium.
4. Erst wenn Desktop stabil läuft: `launcher.py` und Gradio entfernen.
