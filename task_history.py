"""
ECHO Orchestrator — Task History
Persistentes Gedächtnis: jeder abgeschlossene Task wird als JSON gespeichert.
Struktur: /task-history/<task_id>.json
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("echo.task_history")

HISTORY_DIR = Path(__file__).parent / "task-history"


def save_task(
    task_id: str,
    worker: str,
    files_changed: list[str],
    context_layers: list[str],
    status: str,
    summary: str,
    project_path: str = "",
    error: str | None = None,
) -> None:
    """Speichert einen Task in der History."""
    HISTORY_DIR.mkdir(exist_ok=True)
    entry = {
        "task_id": task_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "worker": worker,
        "files_changed": files_changed,
        "context_layers": context_layers,
        "status": status,
        "summary": summary,
        "project_path": project_path,
        "error": error,
    }
    path = HISTORY_DIR / f"{task_id}.json"
    try:
        path.write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.debug("Task History gespeichert: %s", path)
    except OSError as exc:
        logger.error("Task History konnte nicht gespeichert werden: %s", exc)


def load_recent(limit: int = 10) -> list[dict]:
    """Gibt die letzten N Tasks aus der History zurück, neueste zuerst."""
    if not HISTORY_DIR.exists():
        return []
    files = sorted(HISTORY_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    result = []
    for f in files[:limit]:
        try:
            result.append(json.loads(f.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            pass
    return result


def get_task(task_id: str) -> dict | None:
    """Lädt einen einzelnen Task aus der History."""
    path = HISTORY_DIR / f"{task_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def format_recent_for_context(limit: int = 5) -> str:
    """Gibt die letzten Tasks als kompakten Kontext-String zurück."""
    recent = load_recent(limit)
    if not recent:
        return ""
    lines = ["## LETZTE TASKS (Kontext)"]
    for t in recent:
        ts = t.get("timestamp", "")[:10]
        lines.append(
            f"- [{ts}] {t.get('summary', '?')} | Worker: {t.get('worker', '?')} "
            f"| Status: {t.get('status', '?')} | Dateien: {', '.join(t.get('files_changed', []))}"
        )
    return "\n".join(lines)
