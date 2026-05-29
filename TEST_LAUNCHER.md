# Launcher Lifecycle Tests

**Datum:** 2026-05-29  
**Launcher-Version:** 1.1.0

## Automatisierter Lauf (Agent-Umgebung)

In der Cursor-Agent-Session lieferte die Shell **keine Ausgabe und keine Exit-Codes** (bekanntes Umgebungsproblem). Die Lifecycle-Tests wurden deshalb **nicht automatisch verifiziert**.

Bitte lokal ausführen:

```powershell
cd E:\Projects\ECHO-Orchestrators\ECHO-Orchestrators
powershell -ExecutionPolicy Bypass -File scripts\test_launcher_lifecycle.ps1
```

Ergebnis landet in `TEST_LAUNCHER_run.txt` im Projektroot.

## Manuelle Checkliste

| Schritt | Befehl | Erwartung |
|---|---|---|
| 1 | `uv run python launcher.py --dry-run` | Exit 0, Port-Status `free` oder `echo` |
| 2 | `uv run python launcher.py --no-browser` | Backend `/health` 200, UI 7860 mit „gradio“ |
| 3 | Logs | `logs/launcher/launcher.log`, `launcher_state.json`, `logs/backend/backend.log`, `logs/ui/ui.log` |
| 4 | Ctrl+C | Kind-PIDs weg, State + Lock gelöscht |
| 5 | `tasklist \| findstr python` / `netstat -ano \| findstr 8020` | Keine verwaisten Listener (nach wenigen Sekunden) |
| 6 | Erneut `--dry-run` | Sauberer Zustand |

## Statische Verifikation (diese Session)

- `launcher.py`: keine Linter-Fehler
- `/health` in `main.py` vorhanden (`status`, `version`, `environment`)
- Log-Pfade in `CONTROL_UI.md` / `README.md` aktualisiert

## Bekannte Grenzen

- Wiederverwendete Dienste (bereits auf Port, Health OK) werden **nicht** in der Monitor-Loop überwacht — nur vom Launcher gestartete Kinder.
- Lock-Datei schützt nur parallele **Launcher**-Instanzen, nicht manuelles Starten von uvicorn/Gradio ohne Launcher.
- Fremde Prozesse auf 8020/7860: Abbruch mit Fehlermeldung (tasklist-Detail unter Windows).

## Nach erfolgreichem Lokaltest

Eintragen unter „Lokaler Lauf“:

```
Datum:
Dry-run exit:
Health 8020/7860:
Logs OK:
Shutdown clean:
Restart dry-run exit:
Notizen:
```
