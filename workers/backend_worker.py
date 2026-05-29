"""
ECHO Orchestrator — Backend Worker (Stufe 6: Datei-Modifikation aktiv)
Spezialisiert auf Server-seitige Logik: FastAPI-Routen, Datenbankmodelle,
Business-Logic, API-Integrationen.

Pipeline:
  1. build_prompt()   → strukturierter Prompt mit ## FILE: Format-Anweisung
  2. super().execute() → Ollama-Call via BaseWorker
  3. parse_output()   → FileWriter extrahiert Code-Blöcke und schreibt Dateien
  4. Metriken-Log mit echten geschriebenen Pfaden als artifacts
"""

from __future__ import annotations

import logging
from pathlib import Path

from base_worker import BaseWorker
from models import TaskPayload, WorkerResult, WorkerType
from workers.file_writer import FileWriteError, FileWriter

logger = logging.getLogger("echo.workers.backend")


class BackendWorker(BaseWorker):

    worker_type = WorkerType.BACKEND

    # ── Prompt Builder ────────────────────────────────────────────────────────

    def build_prompt(self, payload: TaskPayload) -> str:
        files_list = (
            "\n".join(f"  - {f}" for f in payload.files)
            if payload.files
            else "  (keine Zieldateien angegeben — erstelle sinnvolle Dateinamen)"
        )
        context_lines = (
            "\n".join(f"  {k}: {v}" for k, v in payload.context.items())
            if payload.context
            else "  (kein zusätzlicher Kontext)"
        )

        # Dateiliste für das Output-Format-Beispiel
        example_file = payload.files[0] if payload.files else "app/routes/example.py"

        return (
            "Du bist ein erfahrener Backend-Entwickler (Python 3.11+, FastAPI, Pydantic v2, "
            "SQLAlchemy 2.x async).\n\n"
            "## Aufgabe\n\n"
            f"{payload.description}\n\n"
            "## Zieldateien\n\n"
            f"{files_list}\n\n"
            "## Kontext\n\n"
            f"{context_lines}\n\n"
            "## Anforderungen an den Code\n\n"
            "- Vollständig, produktionsreif, keine Platzhalter, keine TODOs.\n"
            "- async/await konsequent einsetzen.\n"
            "- Pydantic v2 Modelle für alle Request- und Response-Schemas.\n"
            "- HTTPException mit aussagekräftigen Detail-Meldungen.\n"
            "- Präzise Docstrings für alle Funktionen und Klassen.\n\n"
            "## PFLICHT: Output-Format\n\n"
            "Antworte AUSSCHLIESSLICH in diesem Format. "
            "Für jede zu erstellende oder zu modifizierende Datei:\n\n"
            f"## FILE: {example_file}\n"
            "```python\n"
            "<vollständiger Dateiinhalt>\n"
            "```\n\n"
            "Wiederhole das Muster für jede weitere Datei. "
            "Kein Text vor dem ersten ## FILE:-Marker. "
            "Kein Text nach dem letzten Code-Block."
        )

    # ── Output-Parser mit Datei-Schreibung ────────────────────────────────────

    def parse_output(self, raw: str, payload: TaskPayload) -> WorkerResult:
        """
        Extrahiert CODE-Blöcke aus dem LLM-Output und schreibt sie
        in die Zieldateien innerhalb von settings.project_root.
        """
        writer = FileWriter(project_root=Path(self.settings.project_root).resolve())

        try:
            written_paths = writer.extract_and_write(raw)
        except FileWriteError as exc:
            logger.error("FileWriter fehlgeschlagen: %s", exc)
            return WorkerResult(
                task_id=payload.task_id,
                worker_type=self.worker_type,
                model_backend=self.backend,
                model_name=self._active_model_name(),
                success=False,
                output=raw,
                error=str(exc),
            )

        artifacts = [str(p) for p in written_paths]

        if not artifacts:
            # LLM hat kein FILE-Format geliefert — Output trotzdem zurückgeben
            logger.warning(
                "BackendWorker: Keine Dateien geschrieben. "
                "LLM hat kein ## FILE: Format verwendet."
            )
            return WorkerResult(
                task_id=payload.task_id,
                worker_type=self.worker_type,
                model_backend=self.backend,
                model_name=self._active_model_name(),
                success=True,
                output=raw,
                artifacts=[],
            )

        logger.info(
            "BackendWorker: %d Datei(en) geschrieben: %s",
            len(artifacts),
            ", ".join(artifacts),
        )
        return WorkerResult(
            task_id=payload.task_id,
            worker_type=self.worker_type,
            model_backend=self.backend,
            model_name=self._active_model_name(),
            success=True,
            output=raw,
            artifacts=artifacts,
        )

    # ── execute() delegiert an BaseWorker ────────────────────────────────────

    async def execute(self, payload: TaskPayload) -> WorkerResult:
        logger.info(
            "BackendWorker | task=%s | model=%s | project_root=%s",
            payload.task_id,
            self._active_model_name(),
            self.settings.project_root,
        )
        return await super().execute(payload)
