"""
ECHO Orchestrator — Backend Worker (Stufe 3 + FileWriter-Validierung)

Änderungen gegenüber der Originalversion:
  - FileWriter extrahiert ## FILE: <path> ... ## END FILE Blöcke aus dem LLM-Output
  - Wenn keine Marker gefunden werden → WorkerResult.success = False mit Klartext-Error
  - Debug-Logging: vollständiger Raw-Output wird bei LOG_LEVEL=DEBUG sichtbar
  - Bei fehlendem FileWriter (Import-Error) läuft der Worker im Passthrough-Modus
    und loggt eine Warnung — kein harter Crash

Datei-Marker-Format (muss im Prompt definiert sein):
  ## FILE: path/to/file.py
  <code>
  ## END FILE
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

from base_worker import BaseWorker
from models import TaskPayload, WorkerResult, WorkerType

logger = logging.getLogger("echo.workers.backend")

# Regex für ## FILE: <path> ... ## END FILE Blöcke
_FILE_MARKER_RE = re.compile(
    r"##\s*FILE:\s*(?P<path>[^\n]+)\n(?P<content>.*?)##\s*END FILE",
    re.DOTALL,
)


def _extract_and_write_files(raw: str, base_dir: Path) -> list[str]:
    """
    Sucht im LLM-Output nach ## FILE: <path> / ## END FILE Blöcken,
    schreibt die Inhalte auf Disk und gibt die Pfadliste zurück.

    Gibt leere Liste zurück wenn keine Marker gefunden wurden.
    """
    written: list[str] = []

    for match in _FILE_MARKER_RE.finditer(raw):
        rel_path = match.group("path").strip()
        content = match.group("content")

        # Sicherheitscheck: keine absoluten Pfade, kein Path-Traversal
        if os.path.isabs(rel_path) or ".." in rel_path:
            logger.warning(
                "FileWriter: Unsicherer Pfad übersprungen: '%s'", rel_path
            )
            continue

        target = base_dir / rel_path
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            written.append(rel_path)
            logger.info("FileWriter: Datei geschrieben → %s", target)
        except OSError as exc:
            logger.error("FileWriter: Schreiben fehlgeschlagen für %s: %s", rel_path, exc)

    return written


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
            "- Fehlerbehandlung mit aussagekräftigen HTTPException-Details.\n\n"
            "## Ausgabeformat (ZWINGEND EINHALTEN)\n\n"
            "Strukturiere deinen Output ausschließlich so:\n\n"
            "## FILE: <relativer/pfad/zur/datei.py>\n"
            "<vollständiger Dateiinhalt>\n"
            "## END FILE\n\n"
            "Wiederhole diesen Block für jede Datei. "
            "Keine Einleitung, kein Nachsatz, kein Markdown außerhalb der Blöcke."
        )

    # ── execute() mit FileWriter-Validierung ──────────────────────────────────

    async def execute(self, payload: TaskPayload) -> WorkerResult:
        logger.info(
            "BackendWorker | task=%s | backend=%s | model=%s",
            payload.task_id,
            self.backend,
            self._active_model_name(),
        )

        # Basis-Ausführung via BaseWorker (API-Call + Metriken)
        result = await super().execute(payload)

        if not result.success:
            # BaseWorker hat bereits einen Fehler geloggt
            return result

        raw = result.output

        # Debug: kompletten Output sichtbar machen
        logger.debug(
            "BackendWorker RAW OUTPUT (task=%s, %d Zeichen):\n%s",
            payload.task_id,
            len(raw),
            raw,
        )

        # Auch bei INFO sichtbar — zeigt ob Marker vorhanden sind
        marker_count = len(_FILE_MARKER_RE.findall(raw))
        logger.info(
            "BackendWorker | task=%s | Datei-Marker im Output: %d",
            payload.task_id,
            marker_count,
        )

        if marker_count == 0:
            # Kein Marker → kein Diff → kein Gate 2 → Geister-Commit
            # Hier stoppen und den Fehler klar benennen
            logger.error(
                "BackendWorker | task=%s | KEINE ## FILE:-Marker im LLM-Output gefunden.\n"
                "Raw-Output (erste 500 Zeichen):\n%s",
                payload.task_id,
                raw[:500],
            )
            return WorkerResult(
                task_id=payload.task_id,
                worker_type=self.worker_type,
                model_backend=self.backend,
                model_name=self._active_model_name(),
                success=False,
                output=raw,
                error=(
                    "Keine ## FILE: <path> / ## END FILE Marker im LLM-Output gefunden. "
                    "Das Modell hat keinen strukturierten Code geliefert. "
                    f"Output-Vorschau: {raw[:300]}"
                ),
            )

        # Dateien schreiben
        project_root = Path(".").resolve()
        written_files = _extract_and_write_files(raw, base_dir=project_root)

        if not written_files:
            logger.error(
                "BackendWorker | task=%s | Marker gefunden (%d), "
                "aber keine Datei konnte geschrieben werden.",
                payload.task_id,
                marker_count,
            )
            return WorkerResult(
                task_id=payload.task_id,
                worker_type=self.worker_type,
                model_backend=self.backend,
                model_name=self._active_model_name(),
                success=False,
                output=raw,
                error=(
                    f"{marker_count} Datei-Marker gefunden, "
                    "aber Schreiben auf Disk fehlgeschlagen. "
                    "Prüfe die Pfade und Schreibrechte."
                ),
            )

        logger.info(
            "BackendWorker | task=%s | %d Datei(en) geschrieben: %s",
            payload.task_id,
            len(written_files),
            ", ".join(written_files),
        )

        # Erfolgreiches Result mit den tatsächlich geschriebenen Dateien
        return WorkerResult(
            task_id=payload.task_id,
            worker_type=self.worker_type,
            model_backend=self.backend,
            model_name=self._active_model_name(),
            success=True,
            output=raw,
            artifacts=written_files,
        )
