"""
ECHO Orchestrator — Retrieval Worker
Spezialisiert auf RAG-Operationen: Kontextsuche, Embedding-Anfragen,
Dokument-Retrieval aus internen Wissensdatenbanken.

Stufe 1 (jetzt):  Mock-Implementierung.
Stufe 3 (später): build_prompt() liefert den Prompt, execute() delegiert
                  an super().execute().
"""

from __future__ import annotations

import logging

from base_worker import BaseWorker
from models import ModelBackend, TaskPayload, TokenUsage, WorkerResult, WorkerType

logger = logging.getLogger("echo.workers.retrieval")


class RetrievalWorker(BaseWorker):

    worker_type = WorkerType.RETRIEVAL

    # ── Prompt Builder (für Stufe 3) ──────────────────────────────────────────

    def build_prompt(self, payload: TaskPayload) -> str:
        files = "\n".join(f"  - {f}" for f in payload.files) or "  (keine Dateien angegeben)"
        context_lines = "\n".join(
            f"  {k}: {v}" for k, v in payload.context.items()
        ) or "  (kein zusätzlicher Kontext)"

        return (
            "Du bist ein Retrieval-Spezialist.\n"
            "Analysiere die folgende Anfrage und extrahiere relevante Informationen "
            "aus dem bereitgestellten Kontext:\n\n"
            f"{payload.description}\n\n"
            f"Verfügbare Dokumente / Dateien:\n{files}\n\n"
            f"Kontext:\n{context_lines}\n\n"
            "Antworte mit den relevantesten Textstellen, Zusammenfassungen und "
            "einer Quellenangabe pro Treffer. Format: Markdown."
        )

    # ── Mock Execute (Stufe 1) ────────────────────────────────────────────────

    async def execute(self, payload: TaskPayload) -> WorkerResult:
        logger.info(
            "RetrievalWorker | task=%s | backend=%s [MOCK]",
            payload.task_id,
            self.backend,
        )

        mock_output = (
            "# [MOCK] Retrieval-Ergebnis\n\n"
            "## Treffer 1\n"
            "**Quelle:** `docs/architecture.md` (Zeile 42–67)\n"
            "**Relevanz:** 0.91\n\n"
            "> Das ECHO-System verwendet ein deterministisches Routing-Modell, "
            "bei dem jede Aufgabe anhand eines Complexity Scores einem spezialisierten "
            "Worker zugewiesen wird. Human-in-the-Loop bleibt obligatorisch.\n\n"
            "## Treffer 2\n"
            "**Quelle:** `docs/api_reference.md` (Zeile 12–28)\n"
            "**Relevanz:** 0.84\n\n"
            "> Der Core Router berechnet den Complexity Score auf Basis des Worker-Typs, "
            "der Beschreibungslänge und der Kontextgröße. Schwellenwert: 0.6.\n"
        )

        mock_tokens = TokenUsage(prompt_tokens=950, completion_tokens=320)

        result = WorkerResult(
            task_id=payload.task_id,
            worker_type=self.worker_type,
            model_backend=self.backend,
            model_name=self._active_model_name(),
            success=True,
            output=mock_output,
            artifacts=["docs/architecture.md", "docs/api_reference.md"],
        )

        self._write_metric_log(
            payload=payload,
            result=result,
            token_usage=mock_tokens,
            duration=0.0,
        )
        return result
