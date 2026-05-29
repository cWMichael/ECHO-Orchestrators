"""
ECHO Orchestrator — Rules Parser
Liest /.echo/ Layer-Dateien und gibt deren Inhalt strukturiert zurück.
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger("echo.rules_parser")

LAYER_FILES = {
    "core":         "core.md",
    "security":     "security.md",
    "architecture": "architecture.md",
    "branding":     "branding.md",
    "connectors":   "connectors.md",
}


def load_layer(layer_id: str, echo_dir: Path) -> str:
    """Liest einen einzelnen Layer. Gibt leeren String zurück wenn nicht vorhanden."""
    filename = LAYER_FILES.get(layer_id)
    if not filename:
        logger.warning("Unbekannter Layer: %s", layer_id)
        return ""
    path = echo_dir / filename
    if not path.exists():
        logger.debug("Layer-Datei nicht gefunden: %s", path)
        return ""
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        logger.error("Fehler beim Lesen von %s: %s", path, exc)
        return ""


def load_layers(layer_ids: list[str], echo_dir: Path) -> dict[str, str]:
    """Liest mehrere Layer und gibt ein Dict {layer_id: content} zurück."""
    return {lid: load_layer(lid, echo_dir) for lid in layer_ids if load_layer(lid, echo_dir)}


def available_layers(echo_dir: Path) -> list[str]:
    """Gibt alle vorhandenen Layer-IDs zurück."""
    return [lid for lid, fname in LAYER_FILES.items() if (echo_dir / fname).exists()]
