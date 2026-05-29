"""
ECHO Orchestrator — Docs Worker
Erzeugt technische Dokumentation, ADRs, API-Dokumentation, Changelogs.
Schreibt ausschließlich .md Dateien ins Projektverzeichnis.
"""
from __future__ import annotations

import logging
from pathlib import Path

from base_worker import BaseWorker, extract_file_blocks
from models import TaskPayload, WorkerResult, WorkerType

logger = logging.getLogger("echo.workers.docs")


class DocsWorker(BaseWorker):

    worker_type = WorkerType.DOCS

    def build_prompt(self, payload: TaskPayload) -> str:
        project_root = Path(payload.context.get("project_path", "")).resolve()
        project_structure = payload.context.get("project_structure", "")
        ruleset = payload.context.get("echo_ruleset", "")

        # Quelldateien für Dokumentation einlesen
        file_contents = ""
        if payload.files and project_root.exists():
            blocks = []
            for f in payload.files:
                fp = project_root / f
                if fp.exists():
                    try:
                        content = fp.read_text(encoding="utf-8", errors="replace")
                        blocks.append(f"=== FILE: {f} ===\n{content}\n=== END ===")
                    except OSError:
                        pass
            if blocks:
                file_contents = "\n\n".join(blocks)

        files_list = (
            "\n".join(f"  - {f}" for f in payload.files)
            if payload.files else "  (keine Dateien angegeben)"
        )

        prompt = (
            "Du bist ein technischer Redakteur mit Expertise in Software-Dokumentation.\n"
            "Erstelle präzise, entwicklerorientierte Dokumentation.\n\n"
        )

        if ruleset:
            prompt += f"## ECHO RULESET (verbindlich)\n\n{ruleset}\n\n"

        prompt += f"## Aufgabe\n\n{payload.description}\n\n"

        if project_structure:
            prompt += f"## Projektstruktur\n\n{project_structure}\n\n"

        prompt += f"## Betroffene Dateien\n\n{files_list}\n\n"

        if file_contents:
            prompt += f"## Zu dokumentierender Code\n\n{file_contents}\n\n"

        prompt += (
            "## Dokumentations-Standards\n\n"
            "- Schreibe in Markdown\n"
            "- Klar strukturiert: Überschriften, Codebeispiele, Tabellen wo sinnvoll\n"
            "- Zielgruppe: Entwickler die das System zum ersten Mal sehen\n"
            "- Kein Marketing-Sprech, kein Filler-Text\n"
            "- Technisch präzise und vollständig\n"
            "- Für ADRs: Status, Kontext, Entscheidung, Konsequenzen\n"
            "- Für Changelogs: Added / Changed / Fixed / Removed\n\n"
            "## Ausgabeformat — ZWINGEND EINHALTEN\n\n"
            "=== FILE: docs/dateiname.md ===\n"
            "<vollständiger Markdown-Inhalt>\n"
            "=== END ===\n\n"
            "Nur relativer Pfad. Keine absoluten Pfade. "
            "Kein Text außerhalb der FILE-Blöcke."
        )
        return prompt

    def parse_output(self, raw: str, payload: TaskPayload) -> WorkerResult:
        matches = extract_file_blocks(raw)
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
                (created if is_new else modified).append(str(rel_path))
                logger.info("Docs-Datei %s: %s", "erstellt" if is_new else "geändert", file_path)
            except OSError as exc:
                logger.error("Fehler beim Schreiben von %s: %s", file_path, exc)

        all_written = created + modified
        if not all_written:
            logger.warning("DocsWorker: Keine FILE-Blöcke im Output. %.200s", raw)

        return WorkerResult(
            task_id=payload.task_id,
            worker_type=self.worker_type,
            model_backend=self.backend,
            model_name=self._active_model_name(),
            success=len(all_written) > 0,
            output=raw,
            artifacts=all_written or payload.files,
            error=None if all_written else "Keine Dateien im Output gefunden.",
            extra={"created": created, "modified": modified, "deleted": []},
        )

    async def execute(self, payload: TaskPayload) -> WorkerResult:
        logger.info("DocsWorker | task=%s | model=%s", payload.task_id, self._active_model_name())
        return await super().execute(payload)
