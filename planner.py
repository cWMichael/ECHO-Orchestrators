"""
ECHO Orchestrator — Planner
Übersetzt natürlichsprachliche Eingaben in strukturierte Task-Pläne.

Ablauf:
  1. Michael beschreibt in freier Sprache: Vision, Problem, Anforderung
  2. Planner sendet einen Analyse-Prompt an Ollama
  3. LLM gibt strukturiertes JSON zurück (PlanResult)
  4. Planner validiert und bereinigt den JSON-Output
  5. Michael sieht den Plan und gibt ihn frei (Human-in-the-Loop Gate 0)

Design-Prinzipien:
  - Kein autonomes Handeln. Der Plan wird ANGEZEIGT, nicht sofort ausgeführt.
  - JSON-Extraktion ist robust: versucht mehrere Strategien bevor es aufgibt.
  - Modell ist konfigurierbar (settings.ollama_model), kein Hardcoding.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import httpx

from config import Settings
from models import (
    PlannedTask,
    PlanRequest,
    PlanResult,
    TaskPriority,
    WorkerType,
)

logger = logging.getLogger("echo.planner")

# Token-Schätzwerte pro Worker-Typ (prompt + completion, grob)
_TOKEN_ESTIMATES: dict[WorkerType, int] = {
    WorkerType.BACKEND: 2200,
    WorkerType.FRONTEND: 1700,
    WorkerType.TEST: 2600,
    WorkerType.DOCS: 1200,
    WorkerType.RETRIEVAL: 1300,
}


class PlannerError(RuntimeError):
    """Raised when the planner cannot produce a valid plan."""


class Planner:
    """
    Nimmt natürlichsprachliche Eingaben entgegen und gibt einen
    strukturierten PlanResult zurück.

    Keine Tasks werden hier ausgeführt — der Planner produziert
    ausschließlich einen Plan zur menschlichen Freigabe.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client: httpx.AsyncClient | None = None

    async def create_plan(self, request: PlanRequest) -> PlanResult:
        """
        Analysiert die natürlichsprachliche Eingabe und erstellt einen Task-Plan.

        Args:
            request: PlanRequest mit dem Intent-Text von Michael.
        Returns:
            PlanResult mit validierten PlannedTask-Objekten.
        Raises:
            PlannerError: Wenn kein valider Plan extrahiert werden kann.
        """
        prompt = self._build_planner_prompt(request)
        raw = await self._call_ollama(prompt)

        logger.debug("Planner LLM-Rohausgabe (erste 500 Zeichen): %s", raw[:500])

        plan_dict = self._extract_json(raw)
        plan_result = self._validate_and_build(plan_dict, request)

        logger.info(
            "Plan '%s' erstellt: %d Tasks | geschätzte Tokens: %d",
            plan_result.plan_title,
            len(plan_result.tasks),
            plan_result.estimated_total_tokens,
        )
        return plan_result

    # ── Prompt ────────────────────────────────────────────────────────────────

    def _build_planner_prompt(self, request: PlanRequest) -> str:
        worker_list = "\n".join(
            f'  - "{wt.value}": {desc}'
            for wt, desc in {
                WorkerType.BACKEND: "FastAPI-Routen, Pydantic-Modelle, Service-Layer, DB-Logik",
                WorkerType.FRONTEND: "React/JSX-Komponenten, UI-Elemente, Forms",
                WorkerType.TEST: "pytest Unit-Tests und Integrationstests",
                WorkerType.DOCS: "Technische Dokumentation in Markdown",
                WorkerType.RETRIEVAL: "Suche, RAG, Kontext-Extraktion aus Dokumenten",
            }.items()
        )

        context_lines = (
            "\n".join(f"  {k}: {v}" for k, v in request.context.items())
            if request.context
            else "  (kein zusätzlicher Kontext)"
        )

        return (
            "Du bist ein erfahrener Software-Architekt und Task-Planer.\n"
            "Deine Aufgabe: Analysiere die folgende Anforderung und erstelle einen "
            "präzisen, ausführbaren Task-Plan.\n\n"
            "## Anforderung\n\n"
            f"{request.intent}\n\n"
            f"## Zusatzkontext\n\n{context_lines}\n\n"
            "## Verfügbare Worker\n\n"
            f"{worker_list}\n\n"
            "## Regeln für den Plan\n\n"
            "- Zerlege die Anforderung in 1–5 konkrete, ausführbare Tasks.\n"
            "- Wähle den spezifischsten Worker pro Task.\n"
            "- Beschreibe jeden Task so präzise, dass ein Entwickler ihn ohne Rückfragen umsetzen kann.\n"
            "- Liste betroffene Dateipfade wo bekannt (relative Pfade).\n"
            "- Priorisiere: 'critical' nur für Blocker, 'high' für Kern-Features, "
            "'normal' für Standard, 'low' für Nice-to-have.\n\n"
            "## PFLICHT: Antworte NUR mit validem JSON in exakt diesem Format\n\n"
            "```json\n"
            "{\n"
            '  "plan_title": "Kurzer Planname (max 60 Zeichen)",\n'
            '  "summary": "2-3 Sätze was der Plan tut und warum.",\n'
            '  "tasks": [\n'
            "    {\n"
            '      "title": "Kurzer Task-Titel",\n'
            '      "description": "Präzise Beschreibung was der Worker tun soll. Min. 2 Sätze.",\n'
            '      "worker_type": "backend_worker",\n'
            '      "priority": "normal",\n'
            '      "files": ["app/routes/example.py"],\n'
            '      "context": {"key": "value"},\n'
            '      "rationale": "Warum dieser Worker und diese Priorität?"\n'
            "    }\n"
            "  ],\n"
            '  "estimated_total_tokens": 2500\n'
            "}\n"
            "```\n\n"
            "Kein Text vor oder nach dem JSON-Block. Nur das JSON."
        )

    # ── JSON-Extraktion ───────────────────────────────────────────────────────

    def _extract_json(self, raw: str) -> dict:
        """
        Versucht robuste JSON-Extraktion aus dem LLM-Output.
        Strategie 1: Direktes Parsen
        Strategie 2: JSON aus ```json ... ``` Block
        Strategie 3: Erstes { ... } im Text
        """
        # Strategie 1: Direkt
        stripped = raw.strip()
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            pass

        # Strategie 2: Markdown-Code-Block
        match = re.search(r"```(?:json)?\s*([\s\S]*?)```", stripped)
        if match:
            try:
                return json.loads(match.group(1).strip())
            except json.JSONDecodeError:
                pass

        # Strategie 3: Erstes vollständiges { ... }
        match = re.search(r"\{[\s\S]*\}", stripped)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        raise PlannerError(
            "Planner konnte kein valides JSON aus der LLM-Antwort extrahieren.\n"
            f"Rohausgabe (erste 300 Zeichen): {raw[:300]}"
        )

    # ── Validierung & Aufbau ──────────────────────────────────────────────────

    def _validate_and_build(self, data: dict, request: PlanRequest) -> PlanResult:
        """
        Validiert das extrahierte JSON und baut ein PlanResult-Objekt.
        Fehlertoleranz: fehlende optionale Felder werden mit Defaults gefüllt.
        """
        if "tasks" not in data or not isinstance(data["tasks"], list):
            raise PlannerError(
                "Ungültiger Plan: 'tasks'-Liste fehlt oder ist kein Array."
            )
        if not data["tasks"]:
            raise PlannerError("Ungültiger Plan: 'tasks'-Liste ist leer.")

        planned_tasks: list[PlannedTask] = []
        for i, task_data in enumerate(data["tasks"]):
            if not isinstance(task_data, dict):
                logger.warning("Task %d übersprungen: kein Dict.", i)
                continue

            # worker_type normalisieren und validieren
            raw_worker = str(task_data.get("worker_type", "backend_worker"))
            try:
                worker_type = WorkerType(raw_worker)
            except ValueError:
                logger.warning(
                    "Unbekannter worker_type '%s' in Task %d — fallback auf backend_worker.",
                    raw_worker, i,
                )
                worker_type = WorkerType.BACKEND

            # priority normalisieren
            raw_priority = str(task_data.get("priority", "normal")).lower()
            try:
                priority = TaskPriority(raw_priority)
            except ValueError:
                priority = TaskPriority.NORMAL

            planned_tasks.append(PlannedTask(
                title=str(task_data.get("title", f"Task {i + 1}"))[:200],
                description=str(task_data.get("description", request.intent)),
                worker_type=worker_type,
                priority=priority,
                files=list(task_data.get("files", [])),
                context={
                    **request.context,
                    **{k: v for k, v in task_data.get("context", {}).items()},
                },
                rationale=str(task_data.get("rationale", "")),
            ))

        if not planned_tasks:
            raise PlannerError("Kein einziger valider Task im Plan.")

        total_tokens = sum(
            _TOKEN_ESTIMATES.get(t.worker_type, 1500) for t in planned_tasks
        )

        return PlanResult(
            intent=request.intent,
            plan_title=str(data.get("plan_title", "Unbenannter Plan"))[:60],
            summary=str(data.get("summary", "")),
            tasks=planned_tasks,
            estimated_total_tokens=int(data.get("estimated_total_tokens", total_tokens)),
        )

    # ── Ollama Call ───────────────────────────────────────────────────────────

    async def _call_ollama(self, prompt: str) -> str:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.settings.ollama_base_url,
                timeout=httpx.Timeout(
                    connect=5.0,
                    read=float(self.settings.ollama_timeout_seconds),
                    write=30.0,
                    pool=5.0,
                ),
            )

        body = {
            "model": self.settings.ollama_model,
            "prompt": prompt,
            "stream": False,
        }

        try:
            response = await self._client.post("/api/generate", json=body)
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise PlannerError(
                f"Ollama-Timeout nach {self.settings.ollama_timeout_seconds}s: {exc}"
            ) from exc
        except httpx.ConnectError as exc:
            raise PlannerError(
                f"Ollama nicht erreichbar ({self.settings.ollama_base_url}): {exc}"
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise PlannerError(
                f"Ollama HTTP {exc.response.status_code}: {exc.response.text[:300]}"
            ) from exc

        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            raise PlannerError(f"Ollama-Antwort kein valides JSON: {exc}") from exc

        return str(data.get("response", ""))

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
