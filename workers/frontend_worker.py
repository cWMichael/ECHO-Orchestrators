"""
ECHO Orchestrator — Frontend Worker
Spezialisiert auf UI-Komponenten: React/JSX, Tailwind, Formulare,
State-Management, API-Anbindung im Browser.

Stufe 1 (jetzt):  Mock-Implementierung.
Stufe 3 (später): build_prompt() liefert den Prompt, execute() delegiert
                  an super().execute().
"""

from __future__ import annotations

import logging

from base_worker import BaseWorker
from models import ModelBackend, TaskPayload, TokenUsage, WorkerResult, WorkerType

logger = logging.getLogger("echo.workers.frontend")


class FrontendWorker(BaseWorker):

    worker_type = WorkerType.FRONTEND

    # ── Prompt Builder (für Stufe 3) ──────────────────────────────────────────

    def build_prompt(self, payload: TaskPayload) -> str:
        files = "\n".join(f"  - {f}" for f in payload.files) or "  (keine Dateien angegeben)"
        context_lines = "\n".join(
            f"  {k}: {v}" for k, v in payload.context.items()
        ) or "  (kein zusätzlicher Kontext)"

        return (
            "Du bist ein erfahrener Frontend-Entwickler (React 18, TypeScript, Tailwind CSS).\n"
            "Deine Aufgabe:\n\n"
            f"{payload.description}\n\n"
            f"Betroffene Dateien:\n{files}\n\n"
            f"Kontext:\n{context_lines}\n\n"
            "Liefere eine vollständige, funktionsfähige React-Komponente. "
            "Kein Platzhalter-Code. Verwende funktionale Komponenten mit Hooks. "
            "Exportiere die Komponente als Default-Export."
        )

    # ── Mock Execute (Stufe 1) ────────────────────────────────────────────────

    async def execute(self, payload: TaskPayload) -> WorkerResult:
        logger.info(
            "FrontendWorker | task=%s | backend=%s [MOCK]",
            payload.task_id,
            self.backend,
        )

        mock_output = (
            "// [MOCK] UI-Komponente generiert\n\n"
            "import { useState } from 'react';\n\n"
            "interface Props {\n"
            "  title: string;\n"
            "  onSubmit: (value: string) => void;\n"
            "}\n\n"
            "export default function GeneratedComponent({ title, onSubmit }: Props) {\n"
            "  const [value, setValue] = useState('');\n\n"
            "  return (\n"
            "    <div className='p-4 rounded-lg shadow'>\n"
            "      <h2 className='text-xl font-semibold mb-2'>{title}</h2>\n"
            "      <input\n"
            "        className='border rounded px-3 py-2 w-full'\n"
            "        value={value}\n"
            "        onChange={(e) => setValue(e.target.value)}\n"
            "      />\n"
            "      <button\n"
            "        className='mt-2 px-4 py-2 bg-blue-600 text-white rounded'\n"
            "        onClick={() => onSubmit(value)}\n"
            "      >\n"
            "        Absenden\n"
            "      </button>\n"
            "    </div>\n"
            "  );\n"
            "}\n"
        )

        mock_tokens = TokenUsage(prompt_tokens=1200, completion_tokens=450)

        result = WorkerResult(
            task_id=payload.task_id,
            worker_type=self.worker_type,
            model_backend=self.backend,
            model_name=self._active_model_name(),
            success=True,
            output=mock_output,
            artifacts=["frontend/src/Component.jsx"],
        )

        self._write_metric_log(
            payload=payload,
            result=result,
            token_usage=mock_tokens,
            duration=0.0,
        )
        return result
