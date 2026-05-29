"""
ECHO Orchestrator — Docs Worker
Spezialisiert auf technische Dokumentation: README, API-Referenz,
Architecture Decision Records (ADRs), Inline-Docstrings.

Stufe 1 (jetzt):  Mock-Implementierung.
Stufe 3 (später): build_prompt() liefert den Prompt, execute() delegiert
                  an super().execute().
"""

from __future__ import annotations

import logging

from base_worker import BaseWorker
from models import ModelBackend, TaskPayload, TokenUsage, WorkerResult, WorkerType

logger = logging.getLogger("echo.workers.docs")


class DocsWorker(BaseWorker):

    worker_type = WorkerType.DOCS

    # ── Prompt Builder (für Stufe 3) ──────────────────────────────────────────

    def build_prompt(self, payload: TaskPayload) -> str:
        files = "\n".join(f"  - {f}" for f in payload.files) or "  (keine Dateien angegeben)"
        context_lines = "\n".join(
            f"  {k}: {v}" for k, v in payload.context.items()
        ) or "  (kein zusätzlicher Kontext)"

        return (
            "Du bist ein technischer Redakteur mit Expertise in Software-Dokumentation.\n"
            "Erstelle präzise, entwicklerorintierte Dokumentation für die folgende Aufgabe:\n\n"
            f"{payload.description}\n\n"
            f"Betroffene Dateien:\n{files}\n\n"
            f"Kontext:\n{context_lines}\n\n"
            "Anforderungen:\n"
            "  - Schreibe in Markdown.\n"
            "  - Klar strukturiert: Überschriften, Codebeispiele, Tabellen wo sinnvoll.\n"
            "  - Zielgruppe: Entwickler, die das System zum ersten Mal sehen.\n"
            "  - Kein Marketing-Sprech. Präzise, technisch korrekt, kein Filler-Text."
        )

    # ── Mock Execute (Stufe 1) ────────────────────────────────────────────────

    async def execute(self, payload: TaskPayload) -> WorkerResult:
        logger.info(
            "DocsWorker | task=%s | backend=%s [MOCK]",
            payload.task_id,
            self.backend,
        )

        mock_output = (
            "# [MOCK] Technische Dokumentation generiert\n\n"
            "## ECHO Orchestrator\n\n"
            "Deterministische KI-Entwicklungsplattform für interne Tools.\n"
            "Human-in-the-Loop. Hybrides Modell-Routing (Anthropic / Ollama).\n\n"
            "---\n\n"
            "## Setup\n\n"
            "```bash\n"
            "# Abhängigkeiten installieren\n"
            "pip install -r requirements.txt\n\n"
            "# Umgebungsvariablen konfigurieren\n"
            "cp .env.example .env\n\n"
            "# Server starten\n"
            "python main.py\n"
            "```\n\n"
            "## API-Endpunkte\n\n"
            "| Methode | Pfad | Beschreibung |\n"
            "|---------|------|--------------|\n"
            "| `GET`   | `/health` | Liveness-Check |\n"
            "| `POST`  | `/api/v1/tasks` | Task einreichen |\n"
            "| `POST`  | `/api/v1/tasks/{id}/approve` | Task genehmigen/ablehnen |\n"
            "| `GET`   | `/api/v1/tasks/{id}` | Task-Status abfragen |\n"
            "| `GET`   | `/api/v1/tasks` | Alle Tasks auflisten |\n\n"
            "## Worker-Typen\n\n"
            "| Worker | Aufgabe | Standard-Backend |\n"
            "|--------|---------|------------------|\n"
            "| `backend_worker` | FastAPI-Routen, DB-Modelle | Anthropic |\n"
            "| `frontend_worker` | React-Komponenten, UI | Ollama |\n"
            "| `test_worker` | pytest Unit-Tests | Ollama |\n"
            "| `docs_worker` | Technische Dokumentation | Ollama |\n"
            "| `retrieval_worker` | RAG / Suche | Ollama |\n\n"
            "## Metriken\n\n"
            "Alle Ausführungen werden als JSON-Lines nach `logs/echo_metrics.jsonl` geschrieben.\n"
            "Felder: `task_id`, `worker_type`, `model_backend`, `duration_seconds`,\n"
            "`token_usage` (prompt/completion/total), `files_touched`, `success`, `timestamp`.\n"
        )

        mock_tokens = TokenUsage(prompt_tokens=800, completion_tokens=350)

        result = WorkerResult(
            task_id=payload.task_id,
            worker_type=self.worker_type,
            model_backend=self.backend,
            model_name=self._active_model_name(),
            success=True,
            output=mock_output,
            artifacts=["docs/README.md"],
        )

        self._write_metric_log(
            payload=payload,
            result=result,
            token_usage=mock_tokens,
            duration=0.0,
        )
        return result
