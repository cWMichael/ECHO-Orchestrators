"""
ECHO Orchestrator — Backend Worker
Spezialisiert auf allgemeine Coding-Tasks: Dateien erstellen, bearbeiten,
Python-Code, Konfigurationen, Skripte.

Der Worker gibt strukturierte FILE-Blöcke aus und schreibt sie auf Disk.
Git-Diff zeigt danach die echten Änderungen.
"""

from __future__ import annotations

import logging
from pathlib import Path

from base_worker import BaseWorker, extract_file_blocks
from models import TaskPayload, WorkerResult, WorkerType

logger = logging.getLogger("echo.workers.backend")


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
        matches = extract_file_blocks(raw)

        # Projektverzeichnis aus Kontext — fallback: CWD
        project_root = Path(payload.context.get("project_path", "")).resolve()
        if not project_root.exists():
            project_root = Path.cwd()

        created: list[str] = []
        modified: list[str] = []

        for file_path_str, content in matches:
            rel_path = Path(file_path_str.strip())
            if rel_path.is_absolute() or ".." in rel_path.parts:
                logger.warning("Unsicherer Pfad übersprungen: %s", rel_path)
                continue
            file_path = project_root / rel_path
            is_new = not file_path.exists()
            try:
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(content, encoding="utf-8")
                if is_new:
                    created.append(str(rel_path))
                else:
                    modified.append(str(rel_path))
                logger.info("Datei %s: %s", "erstellt" if is_new else "geändert", file_path)
            except OSError as exc:
                logger.error("Fehler beim Schreiben von %s: %s", file_path, exc)

        all_written = created + modified

        if not all_written:
            logger.warning("BackendWorker: Keine FILE-Blöcke im Output. Rohausgabe: %.200s", raw)

        # Änderungsinfo als strukturiertes Artefakt mitgeben
        change_summary = {
            "created": created,
            "modified": modified,
            "deleted": [],
        }

        return WorkerResult(
            task_id=payload.task_id,
            worker_type=self.worker_type,
            model_backend=self.backend,
            model_name=self._active_model_name(),
            success=len(all_written) > 0,
            output=raw,
            artifacts=all_written or payload.files,
            error=None if all_written else "Keine Dateien im Output gefunden.",
            extra=change_summary,
        )

    # ── execute() ─────────────────────────────────────────────────────────────

    async def execute(self, payload: TaskPayload) -> WorkerResult:
        logger.info(
            "BackendWorker | task=%s | model=%s",
            payload.task_id,
            self._active_model_name(),
        )
        return await super().execute(payload)
