"""
ECHO Orchestrator — Test Worker
Spezialisiert auf automatisiertes Testschreiben: pytest Unit-Tests,
Integration-Tests, Fixtures, parametrisierte Testfälle.

Stufe 1 (jetzt):  Mock-Implementierung.
Stufe 3 (später): build_prompt() liefert den Prompt, execute() delegiert
                  an super().execute().
"""

from __future__ import annotations

import logging

from base_worker import BaseWorker
from models import ModelBackend, TaskPayload, TokenUsage, WorkerResult, WorkerType

logger = logging.getLogger("echo.workers.test")


class TestWorker(BaseWorker):

    worker_type = WorkerType.TEST

    # ── Prompt Builder (für Stufe 3) ──────────────────────────────────────────

    def build_prompt(self, payload: TaskPayload) -> str:
        files = "\n".join(f"  - {f}" for f in payload.files) or "  (keine Dateien angegeben)"
        context_lines = "\n".join(
            f"  {k}: {v}" for k, v in payload.context.items()
        ) or "  (kein zusätzlicher Kontext)"

        return (
            "Du bist ein erfahrener Test-Ingenieur (Python, pytest).\n"
            "Schreibe vollständige, ausführbare Unit-Tests für die folgende Aufgabe:\n\n"
            f"{payload.description}\n\n"
            f"Betroffene Dateien:\n{files}\n\n"
            f"Kontext:\n{context_lines}\n\n"
            "Anforderungen:\n"
            "  - Verwende pytest und pytest-asyncio für async Tests.\n"
            "  - Decke Happy Path, Edge Cases und Fehlerfälle ab.\n"
            "  - Nutze parametrisierte Tests wo sinnvoll.\n"
            "  - Kein Platzhalter-Code. Jeder Test muss lauffähig sein."
        )

    # ── Mock Execute (Stufe 1) ────────────────────────────────────────────────

    async def execute(self, payload: TaskPayload) -> WorkerResult:
        logger.info(
            "TestWorker | task=%s | backend=%s [MOCK]",
            payload.task_id,
            self.backend,
        )

        mock_output = (
            "# [MOCK] Unit-Tests generiert\n\n"
            "import pytest\n"
            "from httpx import AsyncClient, ASGITransport\n"
            "from main import app\n\n\n"
            "@pytest.mark.asyncio\n"
            "async def test_health_check():\n"
            "    async with AsyncClient(\n"
            "        transport=ASGITransport(app=app), base_url='http://test'\n"
            "    ) as client:\n"
            "        response = await client.get('/health')\n"
            "    assert response.status_code == 200\n"
            "    assert response.json()['status'] == 'ok'\n\n\n"
            "@pytest.mark.asyncio\n"
            "@pytest.mark.parametrize('worker_type', ['backend_worker', 'test_worker'])\n"
            "async def test_submit_task_pending(worker_type: str):\n"
            "    async with AsyncClient(\n"
            "        transport=ASGITransport(app=app), base_url='http://test'\n"
            "    ) as client:\n"
            "        response = await client.post(\n"
            "            '/api/v1/tasks',\n"
            "            json={\n"
            "                'title': 'Test-Task',\n"
            "                'description': 'Beschreibung für parametrisierten Test.',\n"
            "                'worker_type': worker_type,\n"
            "            },\n"
            "        )\n"
            "    assert response.status_code == 201\n"
            "    data = response.json()\n"
            "    assert 'task_id' in data\n"
            "    assert data['status'] in ('awaiting_approval', 'approved')\n\n\n"
            "@pytest.mark.asyncio\n"
            "async def test_get_nonexistent_task_returns_404():\n"
            "    async with AsyncClient(\n"
            "        transport=ASGITransport(app=app), base_url='http://test'\n"
            "    ) as client:\n"
            "        response = await client.get('/api/v1/tasks/does-not-exist')\n"
            "    assert response.status_code == 404\n"
        )

        mock_tokens = TokenUsage(prompt_tokens=1800, completion_tokens=800)

        result = WorkerResult(
            task_id=payload.task_id,
            worker_type=self.worker_type,
            model_backend=self.backend,
            model_name=self._active_model_name(),
            success=True,
            output=mock_output,
            artifacts=["tests/test_api.py"],
        )

        self._write_metric_log(
            payload=payload,
            result=result,
            token_usage=mock_tokens,
            duration=0.0,
        )
        return result
