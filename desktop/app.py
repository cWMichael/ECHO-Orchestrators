"""ECHO Desktop — QApplication Entry Point."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

# Projektroot als CWD (projects.json, .env, temp/)
_ROOT = Path(__file__).resolve().parent.parent
os.chdir(_ROOT)
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _configure_logging() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )


def main() -> int:
    _configure_logging()

    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:
        print("PySide6 fehlt. Installieren: uv sync", file=sys.stderr)
        raise SystemExit(1) from exc

    # Settings früh laden — .env / PROJECT_ROOT muss gesetzt sein
    try:
        from config import get_settings

        get_settings()
    except Exception as exc:
        print(
            f"Konfiguration fehlt oder ungültig: {exc}\n"
            f"Prüfe .env (PROJECT_ROOT) im Verzeichnis {_ROOT}",
            file=sys.stderr,
        )
        # Trotzdem starten — Projekt-Dropdown kann PROJECT_ROOT setzen

    app = QApplication(sys.argv)
    app.setApplicationName("ECHO Orchestrator Desktop")

    from desktop.main_window import MainWindow

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
