"""
ECHO Orchestrator — Backend Worker
Spezialisiert auf allgemeine Coding-Tasks: Dateien erstellen, bearbeiten,
Python-Code, Konfigurationen, Skripte.

Der Worker gibt strukturierte FILE-Blöcke aus und schreibt sie auf Disk.
Git-Diff zeigt danach die echten Änderungen.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from base_worker import BaseWorker
from models import TaskPayload, WorkerResult, WorkerType

logger = logging.getLogger("echo.workers.backend")

_FILE_PATTERN = re.compile(
    r"===\s*FILE:\s*(.+?)\s*===\n(.*?)(?===\s*END\s*===|\Z)",
    re.DOTALL,
)


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
            "Du bist ein erfahrener Entwickler. Führe die folgende Aufgabe aus "
            "und liefere alle notwendigen Dateiänderungen.\n\n"
            "## Aufgabe\n\n"
            f"{payload.description}\n\n"
            "## Betroffene Dateien\n\n"
            f"{files}\n\n"
            "## Kontext\n\n"
            f"{context_lines}\n\n"
            "## Ausgabeformat — ZWINGEND EINHALTEN\n\n"
            "Für jede Datei die erstellt oder geändert wird, exakt dieses Format:\n\n"
            "=== FILE: pfad/zur/datei.ext ===\n"
            "<vollständiger Dateiinhalt>\n"
            "=== END ===\n\n"
            "Mehrere Dateien hintereinander im selben Format.\n"
            "WICHTIG: Wenn eine Datei bereits existiert, übernimm den VOLLSTÄNDIGEN bestehenden Code "
            "und ergänze nur die notwendigen Änderungen. Lösche NIEMALS vorhandenen Code der nicht "
            "direkt zur Aufgabe gehört.\n"
            "Kein Text außerhalb der FILE-Blöcke. Keine Erklärungen. Nur die Blöcke."
        )

    # ── Output Parser — schreibt Dateien auf Disk ─────────────────────────────

    def parse_output(self, raw: str, payload: TaskPayload) -> WorkerResult:
        matches = _FILE_PATTERN.findall(raw)
        written: list[str] = []

        for file_path_str, content in matches:
            file_path = Path(file_path_str.strip())
            # Sicherheit: keine absoluten Pfade, kein Path-Traversal
            if file_path.is_absolute() or ".." in file_path.parts:
                logger.warning("Unsicherer Pfad übersprungen: %s", file_path)
                continue
            try:
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(content, encoding="utf-8")
                written.append(str(file_path))
                logger.info("Datei geschrieben: %s", file_path)
            except OSError as exc:
                logger.error("Fehler beim Schreiben von %s: %s", file_path, exc)

        if not written:
            logger.warning(
                "BackendWorker: Keine FILE-Blöcke im Output gefunden. "
                "Rohausgabe: %.200s", raw
            )

        return WorkerResult(
            task_id=payload.task_id,
            worker_type=self.worker_type,
            model_backend=self.backend,
            model_name=self._active_model_name(),
            success=len(written) > 0,
            output=raw,
            artifacts=written or payload.files,
            error=None if written else "Keine Dateien im Output gefunden.",
        )

    # ── execute() ─────────────────────────────────────────────────────────────

    async def execute(self, payload: TaskPayload) -> WorkerResult:
        logger.info(
            "BackendWorker | task=%s | model=%s",
            payload.task_id,
            self._active_model_name(),
        )
        return await super().execute(payload)
