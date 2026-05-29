#!/usr/bin/env python3
"""
ECHO Orchestrator — Interaktives Pipeline-Testskript
Steuert den vollständigen Zwei-Gate-Workflow über das Terminal.

Voraussetzung:
    uvicorn main:app --reload   (in einem separaten Terminal)

Verwendung:
    python run_pipeline.py
    python run_pipeline.py --host http://127.0.0.1:8000 --reviewer "Mica"
"""

from __future__ import annotations

import argparse
import json
import sys
import textwrap
import time
from typing import Any

import httpx

# ── ANSI Farb-Codes ───────────────────────────────────────────────────────────
# Fallback auf leere Strings falls Terminal keine Farben unterstützt

try:
    import os
    _COLOR = sys.stdout.isatty() or os.environ.get("FORCE_COLOR") == "1"
except Exception:
    _COLOR = False


class C:
    """ANSI-Farbkonstanten."""
    RESET   = "\033[0m"   if _COLOR else ""
    BOLD    = "\033[1m"   if _COLOR else ""
    DIM     = "\033[2m"   if _COLOR else ""
    GREEN   = "\033[32m"  if _COLOR else ""
    YELLOW  = "\033[33m"  if _COLOR else ""
    CYAN    = "\033[36m"  if _COLOR else ""
    RED     = "\033[31m"  if _COLOR else ""
    MAGENTA = "\033[35m"  if _COLOR else ""
    WHITE   = "\033[97m"  if _COLOR else ""

    ADD     = "\033[32m"  if _COLOR else ""   # Diff: hinzugefügte Zeilen
    REMOVE  = "\033[31m"  if _COLOR else ""   # Diff: entfernte Zeilen
    HUNK    = "\033[36m"  if _COLOR else ""   # Diff: @@ Hunk-Header


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────

def _sep(char: str = "─", width: int = 72) -> str:
    return C.DIM + char * width + C.RESET


def _header(title: str) -> None:
    print()
    print(_sep("═"))
    print(f"  {C.BOLD}{C.WHITE}{title}{C.RESET}")
    print(_sep("═"))


def _step(label: str, text: str) -> None:
    print(f"  {C.CYAN}{C.BOLD}{label:<16}{C.RESET} {text}")


def _ok(msg: str) -> None:
    print(f"  {C.GREEN}✓{C.RESET}  {msg}")


def _warn(msg: str) -> None:
    print(f"  {C.YELLOW}⚠{C.RESET}  {msg}")


def _err(msg: str) -> None:
    print(f"  {C.RED}✗{C.RESET}  {msg}")


def _abort(reason: str) -> None:
    print()
    print(_sep())
    _err(f"Abbruch: {reason}")
    print(_sep())
    sys.exit(1)


def _ask(question: str) -> bool:
    """Fragt den Nutzer nach y/n. Gibt True bei 'y', False bei 'n'."""
    while True:
        print()
        try:
            answer = input(
                f"  {C.BOLD}{C.YELLOW}?{C.RESET}  {question} {C.DIM}(y/n){C.RESET}  "
            ).strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            _abort("Abgebrochen durch Benutzer (Ctrl+C).")
        if answer in ("y", "j", "yes", "ja"):
            return True
        if answer in ("n", "no", "nein"):
            return False
        print(f"  {C.DIM}Bitte 'y' oder 'n' eingeben.{C.RESET}")


def _print_diff(diff: str) -> None:
    """Gibt einen Git-Diff farblich formatiert aus."""
    if not diff:
        _warn("Kein Diff vorhanden — Worker hat keine Dateien verändert.")
        return

    lines = diff.splitlines()
    print()
    print(_sep())
    print(f"  {C.BOLD}GIT DIFF  ({len(lines)} Zeilen){C.RESET}")
    print(_sep())
    print()

    for line in lines:
        if line.startswith("+++") or line.startswith("---"):
            print(f"{C.BOLD}{line}{C.RESET}")
        elif line.startswith("+"):
            print(f"{C.ADD}{line}{C.RESET}")
        elif line.startswith("-"):
            print(f"{C.REMOVE}{line}{C.RESET}")
        elif line.startswith("@@"):
            print(f"{C.HUNK}{line}{C.RESET}")
        elif line.startswith("diff ") or line.startswith("index "):
            print(f"{C.MAGENTA}{line}{C.RESET}")
        else:
            print(line)

    print()
    print(_sep())


def _print_json(data: dict) -> None:
    """Gibt ein Dict als eingerücktes JSON aus."""
    formatted = json.dumps(data, indent=2, ensure_ascii=False, default=str)
    for line in formatted.splitlines():
        print(f"  {C.DIM}{line}{C.RESET}")


# ── HTTP-Client ───────────────────────────────────────────────────────────────

class PipelineClient:
    """Thin wrapper um httpx.Client mit Fehlerbehandlung."""

    def __init__(self, base_url: str, timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            headers={"Content-Type": "application/json"},
        )

    def check_server(self, max_retries: int = 5, retry_delay: float = 1.0) -> None:
        """
        Wartet auf den FastAPI-Server mit Polling.
        Versucht max_retries Mal im Abstand von retry_delay Sekunden.
        """
        last_exc: Exception | None = None

        for attempt in range(1, max_retries + 1):
            print(
                f"\r  {C.DIM}Warte auf Server-Startup "
                f"(Versuch {attempt}/{max_retries}) ...{C.RESET}",
                end="",
                flush=True,
            )
            try:
                r = self._client.get("/health")
                r.raise_for_status()
                data = r.json()
                print()  # Zeilenumbruch nach \r
                _ok(
                    f"Server erreichbar: {self.base_url}  "
                    f"| Version {data.get('version', '?')} "
                    f"| Env: {data.get('environment', '?')}"
                )
                return
            except (httpx.ConnectError, httpx.HTTPStatusError) as exc:
                last_exc = exc
                if attempt < max_retries:
                    time.sleep(retry_delay)

        print()  # Zeilenumbruch nach letztem \r
        _err(
            f"Server nach {max_retries} Versuchen nicht erreichbar "
            f"unter {self.base_url}.\n"
            "  Bitte starte den Server zuerst:\n\n"
            f"    {C.BOLD}uv run uvicorn main:app --reload --port 8020{C.RESET}\n"
        )
        sys.exit(1)

    def post(self, path: str, payload: dict) -> dict:
        return self._request("POST", path, payload)

    def get(self, path: str) -> dict:
        return self._request("GET", path)

    def _request(self, method: str, path: str, payload: dict | None = None) -> dict:
        try:
            if method == "POST":
                r = self._client.post(path, json=payload)
            else:
                r = self._client.get(path)
        except httpx.ConnectError:
            _abort(
                f"Verbindung zu {self.base_url} unterbrochen. "
                "Ist der Server noch aktiv?"
            )
        except httpx.TimeoutException:
            _abort(f"Request-Timeout bei {method} {path}.")

        if r.status_code >= 400:
            try:
                detail = r.json().get("detail", r.text[:300])
            except Exception:
                detail = r.text[:300]
            _abort(
                f"HTTP {r.status_code} bei {method} {path}: {detail}"
            )

        return r.json()

    def close(self) -> None:
        self._client.close()


# ── Pipeline-Schritte ─────────────────────────────────────────────────────────

def step_a_submit(client: PipelineClient, task_payload: dict) -> str:
    """Schritt A: Task einreichen."""
    _header("SCHRITT A — Task einreichen")

    _step("Endpunkt:", "POST /api/v1/tasks")
    _step("Worker:", task_payload["worker_type"])
    _step("Titel:", task_payload["title"])
    print()

    data = client.post("/api/v1/tasks", task_payload)

    task_id: str = data["task_id"]
    _ok(f"Task erstellt: {C.BOLD}{task_id}{C.RESET}")
    _step("Status:", data["status"])
    _step("Meldung:", data["message"])

    return task_id


def step_b_gate1(client: PipelineClient, task_id: str, reviewer: str) -> bool:
    """Schritt B: Gate 1 — Worker-Run freigeben oder ablehnen."""
    _header("GATE 1 — Worker-Ausführung freigeben?")

    # Aktuellen Status anzeigen
    status_data = client.get(f"/api/v1/tasks/{task_id}")
    _step("Task-ID:", task_id)
    _step("Status:", status_data["status"])
    _step("Backend:", str(status_data.get("model_backend", "n/a")))
    _step("Complexity:", str(status_data.get("complexity_score", "n/a")))

    approved = _ask("Worker-Run freigeben und KI-Generierung starten?")

    approval_payload = {
        "approved": approved,
        "reviewer": reviewer,
        "comment": "Gate-1-Freigabe via run_pipeline.py" if approved else "Abgelehnt via run_pipeline.py",
    }

    data = client.post(f"/api/v1/tasks/{task_id}/approve", approval_payload)

    if not approved:
        _warn("Gate 1 abgelehnt. Feature-Branch wird verworfen.")
        _step("Status:", data["status"])
        return False

    _ok("Gate 1 freigegeben. Worker wird ausgeführt ...")
    _step("Status:", data["status"])
    _step("Meldung:", data["message"])
    return True


def step_c_diff(client: PipelineClient, task_id: str) -> str:
    """Schritt C: Code-Diff abrufen und anzeigen."""
    _header("SCHRITT C — Code-Diff abrufen")

    # Kurz warten falls der Worker noch läuft
    _wait_for_status(
        client,
        task_id,
        expected=("pending_diff", "completed", "failed"),
        max_wait=120,
    )

    diff_data = client.get(f"/api/v1/tasks/{task_id}/diff")
    diff: str = diff_data.get("diff", "")

    _step("Branch:", str(diff_data.get("branch", "n/a")))
    _step("Diff-Zeilen:", str(diff_data.get("diff_lines", 0)))

    _print_diff(diff)
    return diff


def step_d_gate2(
    client: PipelineClient, task_id: str, reviewer: str, diff: str
) -> None:
    """Schritt D: Gate 2 — Diff committen oder verwerfen."""
    _header("GATE 2 — Code-Diff final committen?")

    if not diff:
        _warn(
            "Kein Diff vorhanden. Gate 2 wird übersprungen — "
            "nichts zu committen."
        )
        return

    approved = _ask("Diesen Code-Diff final in Git committen und pushen?")

    approval_payload = {
        "approved": approved,
        "reviewer": reviewer,
        "comment": "Gate-2-Freigabe via run_pipeline.py" if approved else "Diff abgelehnt via run_pipeline.py",
    }

    data = client.post(f"/api/v1/tasks/{task_id}/approve-diff", approval_payload)

    if not approved:
        _warn("Gate 2 abgelehnt. Alle Änderungen wurden verworfen.")
        _step("Status:", data["status"])
        return

    _ok("Code committed und gepusht.")
    _step("Status:", data["status"])
    _step("Meldung:", data["message"])


def _wait_for_status(
    client: PipelineClient,
    task_id: str,
    expected: tuple[str, ...],
    max_wait: int = 120,
    poll_interval: float = 2.0,
) -> None:
    """
    Pollt den Task-Status bis einer der erwarteten Zustände erreicht ist.
    Bricht nach max_wait Sekunden ab.
    """
    print()
    elapsed = 0.0
    while elapsed < max_wait:
        data = client.get(f"/api/v1/tasks/{task_id}")
        current = data.get("status", "")
        print(
            f"\r  {C.DIM}Warte auf Worker ... Status: {current} "
            f"({elapsed:.0f}s){C.RESET}",
            end="",
            flush=True,
        )
        if current in expected:
            print()  # Zeilenumbruch nach dem \r
            return
        time.sleep(poll_interval)
        elapsed += poll_interval

    print()
    _abort(
        f"Timeout nach {max_wait}s. Task '{task_id}' hat keinen der "
        f"erwarteten Status erreicht: {expected}."
    )


# ── Summary ───────────────────────────────────────────────────────────────────

def print_summary(client: PipelineClient, task_id: str) -> None:
    """Gibt den finalen Task-Status tabellarisch aus."""
    _header("PIPELINE ABGESCHLOSSEN — Zusammenfassung")

    data = client.get(f"/api/v1/tasks/{task_id}")

    status = data.get("status", "?")
    color = C.GREEN if status == "completed" else C.RED if status == "failed" else C.YELLOW

    _step("Task-ID:",    task_id)
    _step("Titel:",      data.get("title", "?"))
    _step("Status:",     f"{color}{C.BOLD}{status}{C.RESET}")
    _step("Worker:",     str(data.get("worker_type", "?")))
    _step("Backend:",    str(data.get("model_backend", "n/a")))
    _step("Complexity:", str(data.get("complexity_score", "n/a")))

    result = data.get("result")
    if result:
        print()
        print(f"  {C.BOLD}Worker-Output (Vorschau):{C.RESET}")
        output_lines = str(result.get("output", "")).splitlines()[:20]
        for line in output_lines:
            print(f"  {C.DIM}{line}{C.RESET}")
        if len(str(result.get("output", "")).splitlines()) > 20:
            print(f"  {C.DIM}... (gekürzt){C.RESET}")

        artifacts = result.get("artifacts", [])
        if artifacts:
            print()
            _step("Dateien:", ", ".join(artifacts))

    print()
    print(_sep("═"))
    print()


# ── CLI-Argumente ─────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="ECHO Orchestrator — Interaktiver Pipeline-Test",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
            Beispiele:
              python run_pipeline.py
              python run_pipeline.py --reviewer "Mica" --worker backend_worker
              python run_pipeline.py --host http://127.0.0.1:8000 --no-color
        """),
    )
    parser.add_argument(
        "--host",
        default="http://127.0.0.1:8020",
        help="Base-URL des ECHO Orchestrator Servers (default: http://127.0.0.1:8000)",
    )
    parser.add_argument(
        "--reviewer",
        default="Michael",
        help="Name des Human Reviewers für Approval-Requests (default: Mica)",
    )
    parser.add_argument(
        "--worker",
        default="backend_worker",
        choices=[
            "backend_worker",
            "frontend_worker",
            "test_worker",
            "docs_worker",
            "retrieval_worker",
        ],
        help="Worker-Typ für den Test-Task (default: backend_worker)",
    )
    parser.add_argument(
        "--title",
        default="Neue API-Route für cyberFlow",
        help="Titel des Test-Tasks",
    )
    parser.add_argument(
        "--description",
        default=(
            "Erstelle eine neue FastAPI-Route POST /api/v1/projects mit Pydantic-Schema, "
            "Validierung und einem zugehörigen Service-Layer. Die Route soll ein Projekt "
            "anlegen, in der Datenbank persistieren und eine strukturierte JSON-Antwort "
            "mit HTTP 201 zurückgeben."
        ),
        help="Beschreibung des Test-Tasks",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="HTTP-Timeout in Sekunden (default: 30)",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="ANSI-Farben deaktivieren",
    )
    return parser.parse_args()


# ── Einstiegspunkt ────────────────────────────────────────────────────────────

def main() -> None:
    args = _parse_args()

    if args.no_color:
        # Alle Farbkonstanten leeren
        for attr in vars(C):
            if not attr.startswith("__"):
                setattr(C, attr, "")

    task_payload = {
        "title": args.title,
        "description": args.description,
        "worker_type": args.worker,
        "priority": "normal",
        "context": {
            "project": "cyberFlow",
            "target_file": "app/routes/projects.py",
        },
        "files": [
            "app/routes/projects.py",
            "app/models/project.py",
            "app/services/project_service.py",
        ],
    }

    print()
    print(_sep("═"))
    print(f"  {C.BOLD}{C.WHITE}ECHO ORCHESTRATOR — PIPELINE TEST{C.RESET}")
    print(_sep("═"))
    print(f"  Server  : {args.host}")
    print(f"  Reviewer: {args.reviewer}")
    print(f"  Worker  : {args.worker}")
    print(_sep("═"))

    client = PipelineClient(base_url=args.host, timeout=args.timeout)

    # ── Server-Check ──────────────────────────────────────────────────────────
    print()
    client.check_server()

    # ── Schritt A: Task einreichen ────────────────────────────────────────────
    task_id = step_a_submit(client, task_payload)

    # ── Schritt B: Gate 1 ────────────────────────────────────────────────────
    gate1_approved = step_b_gate1(client, task_id, reviewer=args.reviewer)
    if not gate1_approved:
        print_summary(client, task_id)
        client.close()
        sys.exit(0)

    # ── Schritt C: Diff abrufen ───────────────────────────────────────────────
    diff = step_c_diff(client, task_id)

    # Finalen Status prüfen — falls kein Diff → Pipeline endet hier
    status_data = client.get(f"/api/v1/tasks/{task_id}")
    if status_data["status"] != "pending_diff":
        _ok("Kein Diff-Gate nötig — Task direkt abgeschlossen.")
        print_summary(client, task_id)
        client.close()
        sys.exit(0)

    # ── Schritt D: Gate 2 ────────────────────────────────────────────────────
    step_d_gate2(client, task_id, reviewer=args.reviewer, diff=diff)

    # ── Abschlusszusammenfassung ──────────────────────────────────────────────
    print_summary(client, task_id)
    client.close()


if __name__ == "__main__":
    main()
