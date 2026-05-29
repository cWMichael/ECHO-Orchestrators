"""
ECHO Orchestrator — Retrieval Worker
Indexiert Projektdateien und beantwortet Suchanfragen aus dem Wissensspeicher.

Zwei Modi:
  index  — Projekt scannen und Index aufbauen/aktualisieren
  search — Relevante Chunks suchen und als Kontext zurückgeben
"""
from __future__ import annotations

import logging
from pathlib import Path

from base_worker import BaseWorker
from models import TaskPayload, WorkerResult, WorkerType
from retrieval.searcher import search, format_results_for_prompt
from retrieval.store import build_index, get_or_build_index, index_stats

logger = logging.getLogger("echo.workers.retrieval")

_INDEX_KEYWORDS = {"index", "indexier", "scan", "einlesen", "wissensdatenbank", "aufbauen"}
_SEARCH_KEYWORDS = {"such", "find", "zeig", "was", "wo", "welche", "retrieval"}


def _detect_mode(description: str) -> str:
    desc_lower = description.lower()
    if any(k in desc_lower for k in _INDEX_KEYWORDS):
        return "index"
    return "search"


class RetrievalWorker(BaseWorker):

    worker_type = WorkerType.RETRIEVAL

    def build_prompt(self, payload: TaskPayload) -> str:
        """Retrieval Worker nutzt LLM nur für Zusammenfassungen — nicht für Code."""
        project_path = payload.context.get("project_path", "")
        query = payload.description

        # Suchergebnisse in Prompt einbauen
        if project_path:
            results = search(query, Path(project_path), top_k=5)
            knowledge = format_results_for_prompt(results)
        else:
            knowledge = "Kein Projektverzeichnis gesetzt."

        return (
            "Du bist ein Wissensassistent. Beantworte die folgende Anfrage "
            "auf Basis der bereitgestellten Dokumente.\n\n"
            f"## Anfrage\n\n{query}\n\n"
            f"{knowledge}\n\n"
            "Antworte präzise und zitiere die Quelle (Datei + Zeile) für jeden Treffer. "
            "Format: Markdown. Kein Filler-Text."
        )

    async def execute(self, payload: TaskPayload) -> WorkerResult:
        project_path = payload.context.get("project_path", "")
        mode = _detect_mode(payload.description)

        logger.info(
            "RetrievalWorker | task=%s | mode=%s | project=%s",
            payload.task_id, mode, project_path or "—",
        )

        if mode == "index":
            return await self._run_index(payload, project_path)
        else:
            return await self._run_search(payload, project_path)

    async def _run_index(self, payload: TaskPayload, project_path: str) -> WorkerResult:
        """Baut den Projekt-Index auf."""
        if not project_path:
            return WorkerResult(
                task_id=payload.task_id,
                worker_type=self.worker_type,
                model_backend=self.backend,
                model_name=self._active_model_name(),
                success=False,
                output="",
                error="Kein Projektverzeichnis gesetzt — Index kann nicht aufgebaut werden.",
            )

        root = Path(project_path)
        index = build_index(root)
        chunk_count = index.get("chunk_count", 0)
        output = (
            f"# Index erfolgreich aufgebaut\n\n"
            f"- Projektverzeichnis: `{project_path}`\n"
            f"- Chunks: {chunk_count}\n"
            f"- Gespeichert: `.echo/retrieval_index.json`\n"
        )

        return WorkerResult(
            task_id=payload.task_id,
            worker_type=self.worker_type,
            model_backend=self.backend,
            model_name=self._active_model_name(),
            success=True,
            output=output,
            artifacts=[".echo/retrieval_index.json"],
            extra={"mode": "index", "chunk_count": chunk_count},
        )

    async def _run_search(self, payload: TaskPayload, project_path: str) -> WorkerResult:
        """Sucht im Index und gibt Ergebnisse zurück — optional mit LLM-Zusammenfassung."""
        if not project_path:
            return WorkerResult(
                task_id=payload.task_id,
                worker_type=self.worker_type,
                model_backend=self.backend,
                model_name=self._active_model_name(),
                success=False,
                output="",
                error="Kein Projektverzeichnis gesetzt.",
            )

        root = Path(project_path)
        results = search(payload.description, root, top_k=5)

        if not results:
            output = "Keine relevanten Dokumente gefunden."
            return WorkerResult(
                task_id=payload.task_id,
                worker_type=self.worker_type,
                model_backend=self.backend,
                model_name=self._active_model_name(),
                success=True,
                output=output,
                extra={"mode": "search", "results": 0},
            )

        # Mit LLM zusammenfassen
        result = await super().execute(payload)
        result.extra = {
            "mode": "search",
            "results": len(results),
            "sources": [r.chunk.file_path for r in results],
        }
        return result
