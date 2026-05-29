"""
ECHO Orchestrator — Planner
Zerlegt natürlichsprachliche Anfragen in strukturierte Entwicklungspläne.
Kommuniziert ausschließlich mit lokalem Ollama.
Kein Cloud-Zwang, keine externen Abhängigkeiten.
"""

from __future__ import annotations

import json
import logging
import httpx

from config import get_settings
from context_loader import load_context_with_meta
from context_resolver import classify_task

logger = logging.getLogger("echo.planner")

_BASE_PROMPT = """Du bist ein technischer Entwicklungsplaner für Software-Projekte.

Deine Aufgabe: Analysiere die Anfrage des Entwicklers und erstelle einen konkreten, strukturierten Plan.

Antworte IMMER in folgendem JSON-Format — nichts davor, nichts danach:

{
  "zusammenfassung": "Ein Satz was gemacht wird",
  "dateien": ["liste", "der", "betroffenen", "dateien"],
  "schritte": [
    "Schritt 1: ...",
    "Schritt 2: ...",
    "Schritt 3: ..."
  ],
  "worker": "backend_worker",
  "risiken": ["mögliches Risiko 1", "mögliches Risiko 2"],
  "geschaetzte_komplexitaet": "niedrig|mittel|hoch"
}

Worker-Typen:
- backend_worker: FastAPI, Python, APIs, Datenmodelle, Dateien erstellen
- frontend_worker: UI-Komponenten, React, Qt, CSS
- test_worker: Unit-Tests, Integrationstests
- docs_worker: Dokumentation, README, Changelogs
- retrieval_worker: Wissenssuche, Indexierung, Connector-Abfragen

Sei präzise. Keine Füllsätze. Technisch korrekt."""


class Planner:
    """
    Analysiert Benutzeranfragen und erzeugt strukturierte Entwicklungspläne.
    Nutzt das lokale Ollama-Modell.
    Lädt automatisch relevante Rule-Layer aus /.echo/ — niemals alles global.
    """

    def __init__(self) -> None:
        self.settings = get_settings()

    def create_plan(
        self,
        user_request: str,
        project_context: str = "",
        project_path: str = "",
    ) -> dict:
        """
        Sendet die Anfrage an Ollama und gibt einen strukturierten Plan zurück.
        Lädt relevante Rule-Layer basierend auf Task-Klassifikation.
        """
        # Task-Typ klassifizieren → relevante Layer laden
        task_type = classify_task(user_request, "default")
        rule_context, active_layers = load_context_with_meta(task_type, project_path or None)

        if active_layers:
            logger.info("Planner Rule-Layer: %s", active_layers)

        # Prompt zusammenbauen
        prompt_parts = [_BASE_PROMPT]

        if rule_context:
            prompt_parts.append(f"## AKTIVE REGELN\n\n{rule_context}")

        if project_context:
            prompt_parts.append(f"## PROJEKTKONTEXT\n\n{project_context}")

        prompt_parts.append(f"Entwickleranfrage: {user_request}\n\nAntworte nur mit dem JSON-Objekt:")

        prompt = "\n\n---\n\n".join(prompt_parts)

        try:
            raw = self._call_ollama(prompt)
            plan = self._parse_response(raw)
            plan["_active_layers"] = active_layers  # für Task-History
            return plan
        except Exception as exc:
            logger.error("Planner fehlgeschlagen: %s", exc)
            return {
                "zusammenfassung": f"Anfrage: {user_request}",
                "dateien": [],
                "schritte": ["Manuelle Analyse erforderlich"],
                "worker": "backend_worker",
                "risiken": ["Planner konnte keine Analyse erstellen"],
                "geschaetzte_komplexitaet": "unbekannt",
                "fehler": str(exc),
                "_active_layers": active_layers,
            }

    def _call_ollama(self, prompt: str) -> str:
        """Synchroner Ollama-Call für den Planner (läuft im Haupt-Thread der UI)."""
        with httpx.Client(
            base_url=self.settings.ollama_base_url,
            timeout=httpx.Timeout(connect=5.0, read=120.0, write=30.0, pool=5.0),
        ) as client:
            response = client.post(
                "/api/generate",
                json={
                    "model": self.settings.ollama_model,
                    "prompt": prompt,
                    "stream": False,
                },
            )
            response.raise_for_status()
            data = response.json()
            return data.get("response", "")

    def _parse_response(self, raw: str) -> dict:
        """
        Extrahiert JSON aus der Ollama-Antwort.
        Ollama-Modelle fügen manchmal Text vor/nach dem JSON ein —
        wir suchen das erste { und das letzte }.
        """
        raw = raw.strip()

        start = raw.find("{")
        end = raw.rfind("}") + 1

        if start == -1 or end == 0:
            raise ValueError(f"Kein JSON in Ollama-Antwort gefunden: {raw[:200]}")

        json_str = raw[start:end]
        return json.loads(json_str)

    def format_plan_for_chat(self, plan: dict) -> str:
        """
        Formatiert einen Plan als lesbaren Chat-Text.
        """
        lines = []

        lines.append(f"Plan: {plan.get('zusammenfassung', '—')}")
        lines.append("")

        dateien = plan.get("dateien", [])
        if dateien:
            lines.append("Betroffene Dateien:")
            for f in dateien:
                lines.append(f"  {f}")
            lines.append("")

        schritte = plan.get("schritte", [])
        if schritte:
            lines.append("Vorgehensweise:")
            for s in schritte:
                lines.append(f"  {s}")
            lines.append("")

        risiken = plan.get("risiken", [])
        if risiken:
            lines.append("Risiken:")
            for r in risiken:
                lines.append(f"  {r}")
            lines.append("")

        komplexitaet = plan.get("geschaetzte_komplexitaet", "—")
        lines.append(f"Komplexität: {komplexitaet}")
        lines.append("")
        lines.append("Soll ich das so umsetzen? (Ja / Nein)")

        return "\n".join(lines)
