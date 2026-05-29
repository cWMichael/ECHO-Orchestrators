"""
ECHO Orchestrator — Frontend Worker
Spezialisiert auf UI-Komponenten, Layouts, Dashboard-Systeme, cyberFlow-Oberflächen.
Unterstützt: HTML, CSS, JavaScript, React/JSX, Tkinter, Python-UI.

Gibt strukturierte FILE-Blöcke aus und schreibt sie direkt ins Projektverzeichnis.
"""
from __future__ import annotations

import logging
from pathlib import Path

from base_worker import BaseWorker, extract_file_blocks
from context_loader import load_context_with_meta
from models import TaskPayload, WorkerResult, WorkerType

logger = logging.getLogger("echo.workers.frontend")


class FrontendWorker(BaseWorker):

    worker_type = WorkerType.FRONTEND

    def build_prompt(self, payload: TaskPayload) -> str:
        project_root = Path(payload.context.get("project_path", "")).resolve()
        project_structure = payload.context.get("project_structure", "")
        ruleset = payload.context.get("echo_ruleset", "")

        # Datei-Inhalte lesen
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

        prompt = "Du bist ein erfahrener Frontend-Entwickler.\n\n"

        if ruleset:
            prompt += f"## ECHO RULESET (verbindlich)\n\n{ruleset}\n\n"

        prompt += f"## Aufgabe\n\n{payload.description}\n\n"

        if project_structure:
            prompt += f"## Projektstruktur\n\n{project_structure}\n\n"

        prompt += f"## Betroffene Dateien\n\n{files_list}\n\n"

        if file_contents:
            prompt += f"## Aktuelle Datei-Inhalte\n\n{file_contents}\n\n"

        prompt += (
            "## Technologie-Fokus\n\n"
            "- HTML/CSS/JS für einfache UI-Komponenten und Dashboards\n"
            "- Tkinter für Desktop-UI (Python)\n"
            "- React/JSX wenn explizit gewünscht\n"
            "- Cyber-Wear CI: Carbon Black #0A0A0A, Cyber Blue #00A3FF, "
            "Technical Silver #C0C0C0, Heritage Lime #C2D500\n"
            "- Clean, high-end, technische Eleganz — kein visueller Lärm\n\n"
            "## Ausgabeformat — ZWINGEND EINHALTEN\n\n"
            "Für jede Datei:\n\n"
            "=== FILE: dateiname.ext ===\n"
            "<vollständiger Inhalt>\n"
            "=== END ===\n\n"
            "Nur Dateiname oder kurzer relativer Pfad. Keine absoluten Pfade. "
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
                logger.info("Frontend-Datei %s: %s", "erstellt" if is_new else "geändert", file_path)
            except OSError as exc:
                logger.error("Fehler beim Schreiben von %s: %s", file_path, exc)

        all_written = created + modified
        if not all_written:
            logger.warning("FrontendWorker: Keine FILE-Blöcke im Output. %.200s", raw)

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
        logger.info("FrontendWorker | task=%s | model=%s", payload.task_id, self._active_model_name())
        return await super().execute(payload)
