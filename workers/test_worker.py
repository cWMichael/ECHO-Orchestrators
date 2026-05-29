"""
ECHO Orchestrator — Test Worker (Stufe 7: automatischer Test-Run aktiv)
Spezialisiert auf pytest Unit- und Integrationstests.

Pipeline:
  1. build_prompt()        → Prompt mit Quelldateien + ## FILE: Format-Anweisung
  2. super().execute()     → Ollama-Call via BaseWorker
  3. parse_output()
       a. FileWriter       → Testdateien ins tests/-Verzeichnis schreiben
       b. TestRunner.run() → pytest im PROJECT_ROOT ausführen
       c. success=True nur wenn alle Tests grün
  4. Metriken-Log mit Test-Ergebnis und Laufzeit
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from base_worker import BaseWorker
from models import TaskPayload, WorkerResult, WorkerType
from workers.file_writer import FileWriteError, FileWriter
from workers.test_runner import TestRunner

logger = logging.getLogger("echo.workers.test")


class TestWorker(BaseWorker):

    worker_type = WorkerType.TEST

    # ── Prompt Builder ────────────────────────────────────────────────────────

    def build_prompt(self, payload: TaskPayload) -> str:
        source_files = (
            "\n".join(f"  - {f}" for f in payload.files)
            if payload.files
            else "  (keine Quelldateien angegeben)"
        )
        context_lines = (
            "\n".join(f"  {k}: {v}" for k, v in payload.context.items())
            if payload.context
            else "  (kein zusätzlicher Kontext)"
        )

        # Test-Dateinamen ableiten: app/routes/projects.py → tests/test_projects.py
        test_files = [
            f"tests/test_{Path(src).stem}.py"
            for src in payload.files
        ] if payload.files else ["tests/test_module.py"]

        example_test = test_files[0]

        return (
            "Du bist ein erfahrener Test-Ingenieur "
            "(Python 3.11+, pytest, pytest-asyncio, httpx.AsyncClient für FastAPI-Tests).\n\n"
            "## Aufgabe\n\n"
            f"{payload.description}\n\n"
            "## Zu testende Quelldateien\n\n"
            f"{source_files}\n\n"
            "## Kontext\n\n"
            f"{context_lines}\n\n"
            "## Anforderungen\n\n"
            "- Vollständige, sofort lauffähige pytest-Tests. Keine Platzhalter.\n"
            "- Happy Path, Edge Cases und Fehlerfälle (HTTP 4xx/5xx) abdecken.\n"
            "- Async Tests ausschließlich mit @pytest.mark.asyncio.\n"
            "- FastAPI-Endpunkte via httpx.AsyncClient + ASGITransport testen.\n"
            "- @pytest.mark.parametrize für Gruppen ähnlicher Testfälle.\n"
            "- Gemeinsame Fixtures in derselben Testdatei oder conftest.py.\n"
            "- Kein echtes Netzwerk, keine echte DB — Fixtures oder In-Memory.\n\n"
            "## PFLICHT: Output-Format\n\n"
            "Antworte AUSSCHLIESSLICH in diesem Format:\n\n"
            f"## FILE: {example_test}\n"
            "```python\n"
            "<vollständiger Testdatei-Inhalt>\n"
            "```\n\n"
            "Wiederhole das Muster für jede weitere Testdatei. "
            "Kein Text vor dem ersten ## FILE:-Marker. "
            "Kein Text nach dem letzten Code-Block."
        )

    # ── parse_output: Schreiben + Test-Run ───────────────────────────────────

    def parse_output(self, raw: str, payload: TaskPayload) -> WorkerResult:
        """
        1. Schreibt Testdateien via FileWriter.
        2. Führt pytest synchron aus (wird von execute() via to_thread aufgerufen).
        3. success=True nur wenn alle Tests grün.
        """
        project_root = Path(self.settings.project_root).resolve()
        writer = FileWriter(project_root=project_root)

        # ── Testdateien schreiben ─────────────────────────────────────────────
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
            logger.warning(
                "TestWorker: Keine Testdateien geschrieben — "
                "LLM hat kein ## FILE: Format verwendet."
            )
            return WorkerResult(
                task_id=payload.task_id,
                worker_type=self.worker_type,
                model_backend=self.backend,
                model_name=self._active_model_name(),
                success=False,
                output=raw,
                error="Keine Testdateien generiert — LLM-Output enthält kein ## FILE: Marker.",
            )

        logger.info(
            "TestWorker: %d Testdatei(en) geschrieben: %s",
            len(artifacts),
            ", ".join(artifacts),
        )

        # ── pytest ausführen ──────────────────────────────────────────────────
        runner = TestRunner(project_root=project_root)
        test_result = runner.run(test_paths=artifacts)

        logger.info(
            "TestWorker: %s | success=%s",
            test_result.summary,
            test_result.success,
        )

        # Pytest-Output in den Worker-Output integrieren
        combined_output = (
            f"=== GENERIERTE TESTDATEIEN ===\n"
            f"{', '.join(artifacts)}\n\n"
            f"=== PYTEST ERGEBNIS ===\n"
            f"{test_result.summary}\n\n"
            f"{test_result.output}"
        )

        error_msg: str | None = None
        if not test_result.success:
            error_msg = (
                f"Tests fehlgeschlagen: "
                f"{test_result.failed} failed, {test_result.errors} errors. "
                f"Kein Commit bis alle Tests grün."
            )
            logger.warning("TestWorker: %s", error_msg)

        return WorkerResult(
            task_id=payload.task_id,
            worker_type=self.worker_type,
            model_backend=self.backend,
            model_name=self._active_model_name(),
            success=test_result.success,
            output=combined_output,
            artifacts=artifacts,
            error=error_msg,
        )

    # ── execute(): delegiert an BaseWorker ───────────────────────────────────

    async def execute(self, payload: TaskPayload) -> WorkerResult:
        """
        BaseWorker.execute() → build_prompt() → _call_ollama() → parse_output()
        parse_output() läuft synchron (FileWriter + subprocess pytest),
        wird intern von BaseWorker im async-Kontext aufgerufen.
        """
        logger.info(
            "TestWorker | task=%s | model=%s | project_root=%s",
            payload.task_id,
            self._active_model_name(),
            self.settings.project_root,
        )
        return await super().execute(payload)
