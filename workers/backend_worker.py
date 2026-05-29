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
        project_root = Path(payload.context.get("project_path", "")).resolve()
        project_structure = payload.context.get("project_structure", "")

        # Datei-Inhalte lesen wenn vorhanden
        file_contents = ""
        if payload.files and project_root.exists():
            blocks = []
            for f in payload.files:
                fp = project_root / f
                if fp.exists() and fp.is_file():
                    try:
                        content = fp.read_text(encoding="utf-8", errors="replace")
                        blocks.append(f"=== FILE: {f} ===\n{content}\n=== END ===")
                    except OSError:
                        pass
            if blocks:
                file_contents = "\n\n".join(blocks)

        files_list = (
            "\n".join(f"  - {f}" for f in payload.files)
            if payload.files
            else "  (keine Dateien angegeben)"
        )

        ruleset = payload.context.get("echo_ruleset", "")

        prompt = (
            "Du bist ein erfahrener Entwickler. Führe die folgende Aufgabe aus "
            "und liefere alle notwendigen Dateiänderungen.\n\n"
        )

        if ruleset:
            prompt += f"## ECHO RULESET (verbindlich)\n\n{ruleset}\n\n"

        prompt += f"## Aufgabe\n\n{payload.description}\n\n"

        if project_structure:
            prompt += f"## Projektstruktur\n\n{project_structure}\n\n"

        prompt += f"## Betroffene Dateien\n\n{files_list}\n\n"

        if file_contents:
            prompt += f"## Aktuelle Datei-Inhalte\n\n{file_contents}\n\n"

        prompt += (
            "## Ausgabeformat — ZWINGEND EINHALTEN\n\n"
            "Für jede Datei die erstellt oder geändert wird, exakt dieses Format:\n\n"
            "=== FILE: hello.py ===\n"
            "<vollständiger Dateiinhalt>\n"
            "=== END ===\n\n"
            "WICHTIG: Nur den Dateinamen oder kurzen relativen Pfad angeben (z.B. 'hello.py' oder 'backend/hello.py').\n"
            "NIEMALS absolute Pfade wie 'C:\\...' oder '/home/...' verwenden.\n"
            "Kein Text außerhalb der FILE-Blöcke. Keine Erklärungen. Nur die Blöcke."
        )
        return prompt

    # ── Output Parser — schreibt Dateien auf Disk ─────────────────────────────

    def parse_output(self, raw: str, payload: TaskPayload) -> WorkerResult:
        matches = _FILE_PATTERN.findall(raw)
        written: list[str] = []

        # Projektverzeichnis aus Kontext — fallback: CWD
        project_root = Path(payload.context.get("project_path", "")).resolve()
        if not project_root.exists():
            project_root = Path.cwd()

        for file_path_str, content in matches:
            rel_path = Path(file_path_str.strip())
            # Sicherheit: keine absoluten Pfade, kein Path-Traversal
            if rel_path.is_absolute() or ".." in rel_path.parts:
                logger.warning("Unsicherer Pfad übersprungen: %s", rel_path)
                continue
            file_path = project_root / rel_path
            try:
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(content, encoding="utf-8")
                written.append(str(rel_path))
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
