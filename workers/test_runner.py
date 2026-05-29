"""
ECHO Orchestrator — Test Runner
Führt pytest via subprocess im Ziel-Projektverzeichnis aus und
gibt ein strukturiertes Ergebnis zurück.

Design:
  - Läuft synchron (subprocess), wird via asyncio.to_thread() aufgerufen.
  - Nutzt `uv run pytest` falls uv verfügbar, sonst `python -m pytest`.
  - Gibt TestRunResult zurück — enthält pass/fail/error Counts und
    den vollständigen pytest-Output für das Metrics-Log und Gate-2-Anzeige.
  - Schlägt fehl → WorkerResult.success = False → kein Commit ohne grüne Tests.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class TestRunResult:
    """Strukturiertes Ergebnis eines pytest-Laufs."""
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0
    duration_seconds: float = 0.0
    output: str = ""
    success: bool = False

    @property
    def summary(self) -> str:
        return (
            f"pytest | passed={self.passed} failed={self.failed} "
            f"errors={self.errors} skipped={self.skipped} "
            f"({self.duration_seconds:.2f}s)"
        )


class TestRunner:
    """
    Führt pytest für eine Liste von Testdateien im angegebenen
    Projektverzeichnis aus.

    Usage:
        runner = TestRunner(project_root=Path("/my/project"))
        result = runner.run(test_paths=["tests/test_projects.py"])
        if result.success:
            # Alle Tests grün → Commit erlaubt
    """

    def __init__(self, project_root: Path | str = ".") -> None:
        self.project_root = Path(project_root).resolve()

    def run(
        self,
        test_paths: list[str] | None = None,
        extra_args: list[str] | None = None,
    ) -> TestRunResult:
        """
        Führt pytest aus.

        Args:
            test_paths: Spezifische Testdateien oder -verzeichnisse.
                        None = pytest läuft im gesamten project_root.
            extra_args: Zusätzliche pytest-Flags (z.B. ["-x", "--tb=short"]).
        Returns:
            TestRunResult mit pass/fail-Counts und vollem Output.
        """
        cmd = self._build_command(test_paths or [], extra_args or [])

        try:
            proc = subprocess.run(
                cmd,
                cwd=str(self.project_root),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=300,  # max 5 Minuten
            )
        except subprocess.TimeoutExpired:
            return TestRunResult(
                success=False,
                output="pytest-Lauf abgebrochen: Timeout nach 300 Sekunden.",
            )
        except FileNotFoundError:
            return TestRunResult(
                success=False,
                output=(
                    "pytest nicht gefunden. Bitte sicherstellen, dass pytest "
                    "im Ziel-Projekt installiert ist:\n  uv add pytest pytest-asyncio"
                ),
            )

        full_output = (proc.stdout + proc.stderr).strip()
        passed, failed, errors, skipped, duration = self._parse_summary(full_output)

        return TestRunResult(
            passed=passed,
            failed=failed,
            errors=errors,
            skipped=skipped,
            duration_seconds=duration,
            output=full_output,
            # pytest Exit-Code 0 = alle Tests grün
            # pytest Exit-Code 5 = keine Tests gefunden (behandeln wir als Warnung, nicht Fehler)
            success=proc.returncode in (0, 5),
        )

    # ── Internal ──────────────────────────────────────────────────────────────

    def _build_command(
        self, test_paths: list[str], extra_args: list[str]
    ) -> list[str]:
        """
        Baut den pytest-Befehl.
        Nutzt `uv run pytest` nur wenn ein uv-Projekt (pyproject.toml / uv.lock)
        im project_root vorhanden ist — sonst direkter Fallback auf python -m pytest.
        """
        base: list[str]
        has_uv_project = (
            (self.project_root / "pyproject.toml").exists()
            or (self.project_root / "uv.lock").exists()
        )
        if has_uv_project and shutil.which("uv"):
            base = ["uv", "run", "pytest"]
        else:
            base = [sys.executable, "-m", "pytest"]

        return base + [
            "-v",           # verbose: jeder Test einzeln ausgeben
            "--tb=short",   # kompakte Traceback-Ausgabe
            "--no-header",  # Kopfzeile unterdrücken (spart Platz im Log)
            *test_paths,
            *extra_args,
        ]

    def _parse_summary(
        self, output: str
    ) -> tuple[int, int, int, int, float]:
        """
        Parst die letzte pytest-Zusammenfassungszeile.
        Format: "X passed, Y failed, Z error in N.NNs"
        Gibt (passed, failed, errors, skipped, duration) zurück.
        """
        import re

        passed = failed = errors = skipped = 0
        duration = 0.0

        # Beispiel: "3 passed, 1 failed, 0 errors in 2.34s"
        patterns = {
            "passed":  re.compile(r"(\d+)\s+passed"),
            "failed":  re.compile(r"(\d+)\s+failed"),
            "errors":  re.compile(r"(\d+)\s+error"),
            "skipped": re.compile(r"(\d+)\s+skipped"),
            "duration": re.compile(r"in\s+([\d.]+)s"),
        }

        for line in reversed(output.splitlines()):
            # Letzte Zeile mit "passed" oder "failed" ist die Summary
            if "passed" in line or "failed" in line or "error" in line:
                m = patterns["passed"].search(line)
                if m:
                    passed = int(m.group(1))
                m = patterns["failed"].search(line)
                if m:
                    failed = int(m.group(1))
                m = patterns["errors"].search(line)
                if m:
                    errors = int(m.group(1))
                m = patterns["skipped"].search(line)
                if m:
                    skipped = int(m.group(1))
                m = patterns["duration"].search(line)
                if m:
                    duration = float(m.group(1))
                break

        return passed, failed, errors, skipped, duration
