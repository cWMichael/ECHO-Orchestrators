"""
ECHO Orchestrator — Context Loader
Kombiniert Rule-Layer zu einem fertigen Kontext-String für Planner und Worker.
Sucht /.echo/ im Projektverzeichnis, dann im Orchestrator-Verzeichnis.
"""
from __future__ import annotations

import logging
from pathlib import Path

from context_resolver import resolve_layers
from rules_parser import load_layer

logger = logging.getLogger("echo.context_loader")

# Orchestrator-eigenes .echo/ als Fallback
_ECHO_DIR_FALLBACK = Path(__file__).parent / ".echo"


def find_echo_dir(project_path: str | Path | None = None) -> Path:
    """Findet das .echo-Verzeichnis: erst im Projekt, dann im Orchestrator."""
    if project_path:
        candidate = Path(project_path) / ".echo"
        if candidate.exists():
            return candidate
    if _ECHO_DIR_FALLBACK.exists():
        return _ECHO_DIR_FALLBACK
    return _ECHO_DIR_FALLBACK  # auch wenn nicht vorhanden — graceful


def load_context(
    worker_type: str,
    project_path: str | Path | None = None,
    extra_layers: list[str] | None = None,
) -> str:
    """
    Hauptfunktion. Lädt relevante Layer für den Worker-Typ
    und gibt einen kompakten Kontext-String zurück.

    Args:
        worker_type: Worker-Typ oder Task-Klassifikation
        project_path: Optionaler Projektpfad für projektspezifisches .echo/
        extra_layers: Zusätzliche Layer die immer mitgeladen werden sollen

    Returns:
        Fertiger Kontext-String für Prompt-Injection
    """
    echo_dir = find_echo_dir(project_path)
    layer_ids = resolve_layers(worker_type)

    if extra_layers:
        for lid in extra_layers:
            if lid not in layer_ids:
                layer_ids.append(lid)

    loaded: list[str] = []
    active_layers: list[str] = []

    for lid in layer_ids:
        content = load_layer(lid, echo_dir)
        if content:
            loaded.append(content)
            active_layers.append(lid)

    if not loaded:
        logger.warning("Keine Rule-Layer geladen für worker_type=%s", worker_type)
        return ""

    logger.debug("Aktive Layer für %s: %s", worker_type, active_layers)

    return "\n\n---\n\n".join(loaded)


def load_context_with_meta(
    worker_type: str,
    project_path: str | Path | None = None,
) -> tuple[str, list[str]]:
    """
    Wie load_context, gibt zusätzlich die Liste der aktiven Layer-IDs zurück.
    Für Task-History und Audit-Logging.
    """
    echo_dir = find_echo_dir(project_path)
    layer_ids = resolve_layers(worker_type)
    loaded: list[str] = []
    active: list[str] = []

    for lid in layer_ids:
        content = load_layer(lid, echo_dir)
        if content:
            loaded.append(content)
            active.append(lid)

    context = "\n\n---\n\n".join(loaded) if loaded else ""
    return context, active
