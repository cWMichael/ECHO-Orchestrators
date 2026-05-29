"""
ECHO Orchestrator — Projekt-Registry und Laufzeit-Umschaltung des Zielprojekts.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from config import get_settings, set_project_root_override

logger = logging.getLogger("echo.project_registry")

PROJECTS_FILE = Path("projects.json")
_active_project_name: str | None = None


def _orchestrator_dir() -> Path:
    return Path(__file__).resolve().parent


def _validate_target_path(path: str) -> str:
    if not path:
        raise ValueError("Pfad ist leer.")

    target = Path(path).resolve()

    if not target.exists():
        raise ValueError(f"project_root '{target}' existiert nicht.")

    orch = _orchestrator_dir()
    if target == orch or str(target).startswith(str(orch)):
        raise ValueError(
            f"project_root darf nicht auf das Orchestrator-Verzeichnis zeigen: '{target}'."
        )

    return str(target)


def _read_entries() -> list[dict]:
    if not PROJECTS_FILE.exists():
        return []
    try:
        data = json.loads(PROJECTS_FILE.read_text(encoding="utf-8"))
        return list(data.get("projects", []))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("projects.json konnte nicht gelesen werden: %s", exc)
        return []


def load_projects() -> dict[str, str]:
    """Schlüssel (id) → absoluter Pfad."""
    result: dict[str, str] = {}
    for entry in _read_entries():
        key = entry.get("id") or entry.get("name", "")
        path = entry.get("path", "")
        if key and path:
            result[str(key)] = str(path)
    return result


def get_active_project_name() -> str | None:
    global _active_project_name
    if _active_project_name:
        return _active_project_name

    settings = get_settings()
    active_path = Path(settings.project_root).resolve()
    for key, path in load_projects().items():
        if Path(path).resolve() == active_path:
            return key
    return None


def resolve_project_path(name: str) -> str:
    """Setzt aktives Zielprojekt und liefert den validierten Pfad."""
    global _active_project_name

    projects = load_projects()
    if name not in projects:
        raise KeyError(f"Unbekanntes Projekt '{name}'. Verfügbar: {', '.join(projects) or '(keine)'}")

    validated = _validate_target_path(projects[name])
    set_project_root_override(validated)
    _active_project_name = name
    logger.info("Aktives Zielprojekt: %s → %s", name, validated)
    return validated
