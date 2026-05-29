"""
ECHO Orchestrator — Backend Worker (Stufe 3: echte API-Calls aktiv)
Spezialisiert auf Server-seitige Logik: FastAPI-Routen, Datenbankmodelle,
Business-Logic, API-Integrationen.

Routing:
  - Complexity Score >= threshold → Anthropic (Claude) via BaseWorker._call_anthropic()
  - Complexity Score <  threshold → Ollama (lokal) via BaseWorker._call_ollama()

execute() delegiert vollständig an BaseWorker.execute().
Der Worker selbst ist nur noch für den Prompt-Bau zuständig.
"""

from __future__ import annotations

import logging

from base_worker import BaseWorker
from models import TaskPayload, WorkerResult, WorkerType

logger = logging.getLogger("echo.workers.backend")


class BackendWorker(BaseWorker):

    worker_type = WorkerType.BACKEND

    # ── Prompt Builder ────────────────────────────────────────────────────────

    def build_prompt(self, payload: TaskPayload) -> str:
        files = (
            "\n".join(f"  - {f}" for f in payload.files)
            if payload.files
            else "  (keine Dateien angegeben)"
        )
        context_lines = (
            "\n".join(f"  {k}: {v}" for k, v in payload.context.items())
            if payload.context
            else "  (kein zusätzlicher Kontext)"
        )

        return (
            "Du bist ein erfahrener Backend-Entwickler (Python 3.11+, FastAPI, Pydantic v2, "
            "SQLAlchemy 2.x).\n\n"
            "## Aufgabe\n\n"
            f"{payload.description}\n\n"
            "## Betroffene Dateien\n\n"
            f"{files}\n\n"
            "## Kontext\n\n"
            f"{context_lines}\n\n"
            "## Anforderungen\n\n"
            "- Liefere vollständigen, produktionsreifen Python-Code.\n"
            "- Keine Platzhalter, keine TODOs, keine Auslassungen.\n"
            "- Jede Funktion erhält einen präzisen Docstring.\n"
            "- Verwende async/await konsequent.\n"
            "- Pydantic-Modelle für alle Request- und Response-Schemas.\n"
            "- Fehlerbehandlung mit aussagekräftigen HTTPException-Details.\n"
            "- Antworte ausschließlich mit dem Code. Keine Einleitung, kein Nachsatz."
        )

    # ── execute() — delegiert an BaseWorker (echte API-Calls) ────────────────

    async def execute(self, payload: TaskPayload) -> WorkerResult:
        """
        Ruft BaseWorker.execute() auf, welcher:
          1. build_prompt() aufruft
          2. je nach self.backend _call_anthropic() oder _call_ollama() ausführt
          3. parse_output() aufruft
          4. Metriken mit echten Token-Zahlen in das JSONL-Log schreibt
        """
        logger.info(
            "BackendWorker | task=%s | backend=%s | model=%s",
            payload.task_id,
            self.backend,
            self._active_model_name(),
        )
        return await super().execute(payload)
