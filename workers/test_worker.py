"""
ECHO Orchestrator — Test Worker
Erzeugt Unit-Tests, Integrationstests, Smoke Checks, Regressionstests.
Schreibt test_*.py Dateien ins Projektverzeichnis.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from base_worker import BaseWorker
from models import TaskPayload, WorkerResult, WorkerType

logger = logging.getLogger("echo.workers.test")

_FILE_PATTERN = re.compile(
    r"===\s*FILE:\s*(.+?)\s*===\n(.*?)(?===\s*END\s*===|\Z)",
    re.DOTALL,
)


class TestWorker(BaseWorker):

    worker_type = WorkerType.TEST

    def build_prompt(self, payload: TaskPayload) -> str:
        project_root = Path(payload.context.get("project_path", "")).resolve()
        project_structure = payload.context.get("project_structure", "")
        ruleset = payload.context.get("echo_ruleset", "")

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
            "Du bist ein erfahrener Software-Tester mit Fokus auf Python.\n"
            "Erstelle vollständige, ausführbare Tests.\n\n"
        )

        if ruleset:
            prompt += f"## ECHO RULESET (verbindlich)\n\n{ruleset}\n\n"

        prompt += f"## Aufgabe\n\n{payload.description}\n\n"

        if project_structure:
            prompt += f"## Projektstruktur\n\n{project_structure}\n\n"

        prompt += f"## Zu testende Dateien\n\n{files_list}\n\n"

        if file_contents:
            prompt += f"## Zu testender Code\n\n{file_contents}\n\n"

        prompt += (
            "## Test-Standards\n\n"
            "- Verwende pytest\n"
            "- Dateiname beginnt mit test_ (z.B. test_hello.py)\n"
            "- Jede Funktion beginnt mit test_\n"
            "- Smoke Checks: grundlegende Funktionalität\n"
            "- Edge Cases: Grenzwerte und Fehlerbehandlung\n"
            "- Keine externen Abhängigkeiten außer pytest und der zu testenden Datei\n"
            "- Vollständig ausführbar, kein Platzhalter-Code\n\n"
            "## Ausgabeformat — ZWINGEND EINHALTEN\n\n"
            "=== FILE: test_dateiname.py ===\n"
            "<vollständiger Test-Code>\n"
            "=== END ===\n\n"
            "Nur relativer Pfad. Keine absoluten Pfade. "
            "Kein Text außerhalb der FILE-Blöcke."
        )
        return prompt

    def parse_output(self, raw: str, payload: TaskPayload) -> WorkerResult:
        matches = _FILE_PATTERN.findall(raw)
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
                logger.info("Test-Datei %s: %s", "erstellt" if is_new else "geändert", file_path)
            except OSError as exc:
                logger.error("Fehler beim Schreiben von %s: %s", file_path, exc)

        all_written = created + modified
        if not all_written:
            logger.warning("TestWorker: Keine FILE-Blöcke im Output.\nROH-OUTPUT:\n%s", raw)

        return WorkerResult(
            task_id=payload.task_id,
            worker_type=self.worker_type,
            model_backend=self.backend,
            model_name=self._active_model_name(),
            success=len(all_written) > 0,
            output=raw,
            artifacts=all_written or payload.files,
            error=None if all_written else "Keine Test-Dateien im Output gefunden.",
            extra={"created": created, "modified": modified, "deleted": []},
        )

    async def execute(self, payload: TaskPayload) -> WorkerResult:
        logger.info("TestWorker | task=%s | model=%s", payload.task_id, self._active_model_name())
        return await super().execute(payload)
