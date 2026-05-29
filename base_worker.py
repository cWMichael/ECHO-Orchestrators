"""
ECHO Orchestrator — Abstract Base Worker
Alle spezialisierten Worker erben von dieser Klasse.

Verantwortlichkeiten:
  - Einheitliches execute()-Interface
  - Modell-Routing: httpx → Ollama (lokal)
  - Robuste Fehlerbehandlung (Netzwerk-Timeouts, API-Fehler)
  - JSON-Lines Metriken-Logging (echte Tokens aus API-Antworten, Laufzeit, Dateien)
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from abc import ABC, abstractmethod
from pathlib import Path

import httpx

# ── File-Block Parser ─────────────────────────────────────────────────────────

_ECHO_FILE_PATTERN = re.compile(
    r"===\s*FILE:\s*(.+?)\s*===\n(.*?)(?===\s*END\s*===|\Z)",
    re.DOTALL,
)

# Markdown-Codeblock mit Dateiname davor
# z.B. ### tests/test_hello.py\n```python\n...\n```
_MD_FILE_PATTERN = re.compile(
    r"(?:#{1,4}\s+|//\s*|#\s*)?([\w/\\.\-]+\.(?:py|js|ts|jsx|tsx|html|css|md|txt|json|yaml|yml))\s*\n```[^\n]*\n(.*?)```",
    re.DOTALL,
)

# Codeblock mit # FILE: Kommentar als erste Zeile innerhalb des Blocks
# z.B. ```python\n# FILE: tests/test_hello.py\n...\n```
_INLINE_FILE_PATTERN = re.compile(
    r"```[^\n]*\n#\s*FILE:\s*([\w/\\.\-]+)\s*\n(.*?)```",
    re.DOTALL,
)


_TRAILING_ARTIFACTS = {"```", "=", "---", "===", ""}


def _clean_content(content: str) -> str:
    """
    Bereinigt extrahierten Dateiinhalt von LLM-Artefakten.
    Entfernt führende/abschließende Backticks, =, Leerzeilen und ECHO-Trennzeichen.
    Wird auf ALLE extrahierten Inhalte angewendet.
    """
    lines = content.splitlines()
    # Führende Backtick-Zeile entfernen
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    # Abschließende Artefakte entfernen
    while lines and lines[-1].strip() in _TRAILING_ARTIFACTS:
        lines = lines[:-1]
    return "\n".join(lines)


def _strip_code_fences(content: str) -> str:
    """Alias für _clean_content."""
    return _clean_content(content)


def extract_file_blocks(raw: str) -> list[tuple[str, str]]:
    """
    Extrahiert (Dateipfad, Inhalt) Paare aus LLM-Output.
    Alle Inhalte werden durch _clean_content bereinigt.
    Unterstützt:
      1. ECHO-Format:      === FILE: path === ... === END ===
      2. Inline-Kommentar: ```python\\n# FILE: path.py\\n...\\n```
      3. Markdown-Heading: ### path.py\\n```python\\n...\\n```
    """
    # 1. ECHO-Format
    matches = _ECHO_FILE_PATTERN.findall(raw)
    if matches:
        return [(path.strip(), _clean_content(content)) for path, content in matches]

    # 2. Inline FILE-Kommentar im Codeblock
    matches = _INLINE_FILE_PATTERN.findall(raw)
    if matches:
        return [(path.strip(), _clean_content(content)) for path, content in matches]

    # 3. Dateiname als Heading vor Codeblock
    matches = _MD_FILE_PATTERN.findall(raw)
    if matches:
        return [(path.strip(), _clean_content(content)) for path, content in matches]

    return []


# Einfacher Codeblock ohne Dateinamen
_BARE_CODE_PATTERN = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)


def extract_code_blocks(raw: str) -> list[str]:
    """Gibt alle Codeblock-Inhalte zurück (ohne Dateinamen-Zuordnung)."""
    return [_clean_content(m) for m in _BARE_CODE_PATTERN.findall(raw)
            if m.strip() and not m.strip().startswith("bash") and len(m.strip()) > 20]

from config import Settings
from models import (
    MetricLogEntry,
    ModelBackend,
    TaskPayload,
    TokenUsage,
    WorkerResult,
    WorkerType,
)

logger = logging.getLogger("echo.base_worker")


class BaseWorker(ABC):
    """
    Abstract base for all ECHO workers.

    Subclasses must implement:
      - worker_type  (class attribute)
      - build_prompt(payload) → str

    Subclasses may override:
      - parse_output(raw, payload) → WorkerResult
    """

    worker_type: WorkerType  # Set by each subclass

    def __init__(self, backend: ModelBackend, settings: Settings) -> None:
        self.backend = backend
        self.settings = settings
        self._http_client: httpx.AsyncClient | None = None

    # ── Public Interface ──────────────────────────────────────────────────────

    async def execute(self, payload: TaskPayload) -> WorkerResult:
        """
        Main entry point called by the core router.
        Runs the full pipeline: prompt → LLM call → parse → log metrics.
        """
        start = time.perf_counter()
        token_usage = TokenUsage()
        result: WorkerResult

        try:
            prompt = self.build_prompt(payload)

            raw, token_usage = await self._call_ollama(prompt)

            result = self.parse_output(raw, payload)

        except Exception as exc:
            duration = time.perf_counter() - start
            logger.exception(
                "Worker %s failed for task %s: %s",
                self.worker_type,
                payload.task_id,
                exc,
            )
            result = WorkerResult(
                task_id=payload.task_id,
                worker_type=self.worker_type,
                model_backend=self.backend,
                model_name=self._active_model_name(),
                success=False,
                output="",
                error=str(exc),
            )
            self._write_metric_log(
                payload=payload,
                result=result,
                token_usage=token_usage,
                duration=duration,
            )
            return result

        duration = time.perf_counter() - start
        self._write_metric_log(
            payload=payload,
            result=result,
            token_usage=token_usage,
            duration=duration,
        )
        return result

    # ── Abstract Methods ──────────────────────────────────────────────────────

    @abstractmethod
    def build_prompt(self, payload: TaskPayload) -> str:
        """
        Construct the LLM prompt from the task payload.
        Override in each worker to craft domain-specific prompts.
        """

    # ── Optional Override ─────────────────────────────────────────────────────

    def parse_output(self, raw: str, payload: TaskPayload) -> WorkerResult:
        """
        Convert raw LLM output into a WorkerResult.
        Default implementation passes the raw text through unchanged.
        Override for structured extraction (e.g., JSON, code blocks).
        """
        return WorkerResult(
            task_id=payload.task_id,
            worker_type=self.worker_type,
            model_backend=self.backend,
            model_name=self._active_model_name(),
            success=True,
            output=raw,
            artifacts=payload.files,
        )

    # ── Ollama Call ───────────────────────────────────────────────────────────

    async def _call_ollama(self, prompt: str) -> tuple[str, TokenUsage]:
        """
        Calls the local Ollama /api/generate endpoint via async httpx.
        Uses stream=false for a single JSON response.
        Extracts prompt_eval_count and eval_count as real token counts.
        Raises on network errors, timeouts, and non-2xx HTTP responses.
        """
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                base_url=self.settings.ollama_base_url,
                timeout=httpx.Timeout(
                    connect=5.0,
                    read=float(self.settings.ollama_timeout_seconds),
                    write=30.0,
                    pool=5.0,
                ),
            )

        request_body = {
            "model": self.settings.ollama_model,
            "prompt": prompt,
            "stream": False,
        }

        try:
            response = await self._http_client.post(
                "/api/generate",
                json=request_body,
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise TimeoutError(
                f"Ollama request timed out after "
                f"{self.settings.ollama_timeout_seconds}s "
                f"(url={self.settings.ollama_base_url}): {exc}"
            ) from exc
        except httpx.ConnectError as exc:
            raise ConnectionError(
                f"Cannot reach Ollama at {self.settings.ollama_base_url}. "
                f"Is the Ollama server running? Details: {exc}"
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"Ollama returned HTTP {exc.response.status_code}: "
                f"{exc.response.text[:500]}"
            ) from exc

        try:
            data: dict = response.json()
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Ollama response is not valid JSON: {exc}"
            ) from exc

        raw_text: str = data.get("response", "")

        # Ollama returns token counts only when stream=false
        usage = TokenUsage(
            prompt_tokens=data.get("prompt_eval_count", 0),
            completion_tokens=data.get("eval_count", 0),
        )

        logger.debug(
            "Ollama call complete | model=%s | prompt_tokens=%d | completion_tokens=%d",
            self.settings.ollama_model,
            usage.prompt_tokens,
            usage.completion_tokens,
        )
        return raw_text, usage

    # ── Metrics Logging ───────────────────────────────────────────────────────

    def _write_metric_log(
        self,
        payload: TaskPayload,
        result: WorkerResult,
        token_usage: TokenUsage,
        duration: float,
    ) -> None:
        entry = MetricLogEntry(
            task_id=payload.task_id,
            worker_type=self.worker_type,
            model_backend=self.backend,
            model_name=self._active_model_name(),
            success=result.success,
            duration_seconds=round(duration, 4),
            token_usage=token_usage,
            files_touched=result.artifacts,
            error=result.error,
        )

        log_path = Path(self.settings.log_file_path)
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8") as fh:
                fh.write(entry.model_dump_json() + os.linesep)
        except OSError as exc:
            # Log but never crash the worker over a log write failure
            logger.error("Failed to write metric log to %s: %s", log_path, exc)

        logger.info(
            "Task %s | %s | backend=%s | success=%s | "
            "prompt_tokens=%d | completion_tokens=%d | total_tokens=%d | %.3fs",
            payload.task_id,
            self.worker_type,
            self.backend,
            result.success,
            token_usage.prompt_tokens,
            token_usage.completion_tokens,
            token_usage.total_tokens,
            duration,
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _active_model_name(self) -> str:
        return self.settings.ollama_model

    async def close(self) -> None:
        """Release HTTP clients — wire into FastAPI lifespan shutdown."""
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None
