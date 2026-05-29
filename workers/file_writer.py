"""
ECHO Orchestrator — FileWriter Utility
Parst LLM-Output nach strukturierten FILE-Markern und schreibt
die extrahierten Code-Blöcke in das Ziel-Dateisystem.

Erwartetes LLM-Output-Format:

    ## FILE: app/routes/projects.py
    ```python
    <vollständiger Code>
    ```

    ## FILE: app/models/project.py
    ```python
    <vollständiger Code>
    ```

Regeln:
  - Mehrere Dateien pro LLM-Antwort möglich.
  - Unbekannte Sprachmarker (```typescript, ```jsx etc.) werden ebenfalls
    akzeptiert — der Sprachmarker wird entfernt, der Inhalt bleibt.
  - Dateipfade werden gegen project_root aufgelöst.
  - Elternverzeichnisse werden automatisch erstellt.
  - Path-Traversal-Angriffe (../../) werden abgeblockt.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger("echo.file_writer")

# Regex: ## FILE: <pfad>  (optional führende/nachfolgende Leerzeichen)
_FILE_MARKER = re.compile(
    r"##\s*FILE:\s*(?P<path>[^\n]+)\n"
    r"```[^\n]*\n"          # ```python / ```typescript / ``` etc.
    r"(?P<code>.*?)"        # Code-Inhalt (non-greedy)
    r"```",                  # schließende ```
    re.DOTALL,
)


class FileWriteError(RuntimeError):
    """Raised when a file cannot be written."""


class FileWriter:
    """
    Extracts code blocks from structured LLM output and writes them to disk.

    Usage:
        writer = FileWriter(project_root=Path("/my/project"))
        written = writer.extract_and_write(llm_output)
        # written == [Path("app/routes/projects.py"), ...]
    """

    def __init__(self, project_root: Path | str = ".") -> None:
        self.project_root = Path(project_root).resolve()

    def extract_and_write(self, raw: str) -> list[Path]:
        """
        Parst raw LLM-Output, extrahiert alle FILE-Blöcke und schreibt
        sie auf das Dateisystem.

        Returns:
            Liste der geschriebenen Pfade (relativ zu project_root).
        Raises:
            FileWriteError: Wenn ein Dateipfad unsicher ist oder das
                            Schreiben fehlschlägt.
        """
        matches = list(_FILE_MARKER.finditer(raw))

        if not matches:
            logger.warning(
                "FileWriter: Keine ## FILE: Marker im LLM-Output gefunden. "
                "Kein Datei-Write durchgeführt."
            )
            return []

        written: list[Path] = []
        for match in matches:
            rel_path_str = match.group("path").strip()
            code = match.group("code")

            # Sicherheits-Check: kein Path-Traversal
            rel_path = self._safe_relative_path(rel_path_str)
            abs_path = self.project_root / rel_path

            self._write_file(abs_path, code)
            written.append(rel_path)
            logger.info("FileWriter: Geschrieben → %s", abs_path)

        return written

    def extract_only(self, raw: str) -> dict[str, str]:
        """
        Parst LLM-Output und gibt ein Dict {relativer_pfad: code} zurück,
        ohne zu schreiben. Nützlich für Dry-Run / Preview.
        """
        result: dict[str, str] = {}
        for match in _FILE_MARKER.finditer(raw):
            rel_path_str = match.group("path").strip()
            code = match.group("code")
            result[rel_path_str] = code
        return result

    # ── Internal ──────────────────────────────────────────────────────────────

    def _safe_relative_path(self, raw_path: str) -> Path:
        """
        Normalisiert den Pfad und stellt sicher, dass er innerhalb von
        project_root bleibt. Wirft FileWriteError bei Path-Traversal.
        """
        # Normalisiere Windows/Unix Trennzeichen
        normalized = raw_path.replace("\\", "/").lstrip("/")
        rel = Path(normalized)

        # Resolved-Check: muss unter project_root liegen
        resolved = (self.project_root / rel).resolve()
        if not str(resolved).startswith(str(self.project_root)):
            raise FileWriteError(
                f"Path-Traversal blockiert: '{raw_path}' liegt außerhalb "
                f"von project_root '{self.project_root}'."
            )
        return rel

    def _write_file(self, abs_path: Path, code: str) -> None:
        """Erstellt Verzeichnisse und schreibt den Code in die Datei."""
        try:
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            abs_path.write_text(code, encoding="utf-8")
        except OSError as exc:
            raise FileWriteError(
                f"Datei konnte nicht geschrieben werden: {abs_path} — {exc}"
            ) from exc
