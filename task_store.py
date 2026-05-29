"""
ECHO Orchestrator — Persistenter Task-Store
Ersetzt den flüchtigen _task_store-Dict im core_router.py.

Speichert TaskState-Objekte als JSON in temp/state.json.
Überlebt Server-Neustarts und --reload-Zyklen.

Design:
  - Singleton via get_store()
  - Alle Schreiboperationen sofort auf Disk (kein Batch, kein Risiko)
  - Lädt beim Start automatisch den letzten bekannten State
  - Thread-safe für uvicorn (single-process, async — kein Lock nötig)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from models import (
    HumanApproval,
    ModelBackend,
    TaskPayload,
    TaskState,
    TaskStatus,
    WorkerResult,
    WorkerType,
    TaskPriority,
)

logger = logging.getLogger("echo.task_store")

STATE_FILE = Path("temp/state.json")


class PersistentTaskStore:
    """
    Schreibt jeden State-Zustand sofort in temp/state.json.
    Beim Start wird der letzte bekannte State geladen.
    """

    def __init__(self, path: Path = STATE_FILE) -> None:
        self._path = path
        self._store: dict[str, TaskState] = {}
        self._load()

    # ── Public API ────────────────────────────────────────────────────────────

    def get(self, task_id: str) -> TaskState | None:
        return self._store.get(task_id)

    def set(self, task_id: str, state: TaskState) -> None:
        self._store[task_id] = state
        self._save()

    def all(self) -> list[TaskState]:
        return list(self._store.values())

    def __contains__(self, task_id: str) -> bool:
        return task_id in self._store

    # ── Persistence ───────────────────────────────────────────────────────────

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        raw: dict[str, Any] = {}
        for tid, state in self._store.items():
            raw[tid] = state.model_dump(mode="json")
        try:
            self._path.write_text(
                json.dumps(raw, indent=2, default=str), encoding="utf-8"
            )
        except OSError as exc:
            logger.error("State-Datei konnte nicht geschrieben werden: %s", exc)

    def _load(self) -> None:
        if not self._path.exists():
            logger.info("Kein State gefunden — starte mit leerem Store (%s).", self._path)
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            loaded = 0
            for tid, data in raw.items():
                try:
                    state = TaskState.model_validate(data)
                    self._store[tid] = state
                    loaded += 1
                except Exception as exc:
                    logger.warning("Task %s konnte nicht geladen werden: %s", tid, exc)
            logger.info("State geladen: %d Tasks aus %s", loaded, self._path)
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("State-Datei defekt, starte leer: %s", exc)


# ── Singleton ──────────────────────────────────────────────────────────────────

_store_instance: PersistentTaskStore | None = None


def get_store() -> PersistentTaskStore:
    global _store_instance
    if _store_instance is None:
        _store_instance = PersistentTaskStore()
    return _store_instance
