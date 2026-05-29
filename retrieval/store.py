"""
ECHO Retrieval — Store
Persistenter JSON-Index. Lädt, speichert und aktualisiert Chunk-Sammlungen.

Index-Datei: .echo/retrieval_index.json im Projektverzeichnis.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from retrieval.indexer import Chunk, index_project

logger = logging.getLogger("echo.retrieval.store")

INDEX_FILENAME = "retrieval_index.json"


def _index_path(project_root: Path) -> Path:
    echo_dir = project_root / ".echo"
    echo_dir.mkdir(exist_ok=True)
    return echo_dir / INDEX_FILENAME


def build_index(project_root: Path) -> dict:
    """Scannt das Projekt und speichert den Index. Gibt Index-Metadaten zurück."""
    chunks = index_project(project_root)
    index = {
        "project": str(project_root),
        "indexed_at": datetime.now(timezone.utc).isoformat(),
        "chunk_count": len(chunks),
        "chunks": [c.to_dict() for c in chunks],
    }
    path = _index_path(project_root)
    path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Index gespeichert: %s (%d Chunks)", path, len(chunks))
    return index


def load_index(project_root: Path) -> dict | None:
    """Lädt den gespeicherten Index. Gibt None zurück wenn keiner existiert."""
    path = _index_path(project_root)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("Index konnte nicht geladen werden: %s", exc)
        return None


def get_or_build_index(project_root: Path) -> dict:
    """Lädt bestehenden Index oder erstellt einen neuen."""
    existing = load_index(project_root)
    if existing:
        logger.info(
            "Bestehender Index geladen: %d Chunks (Stand: %s)",
            existing.get("chunk_count", 0),
            existing.get("indexed_at", "?")[:10],
        )
        return existing
    logger.info("Kein Index gefunden — erstelle neuen Index.")
    return build_index(project_root)


def index_stats(project_root: Path) -> dict:
    """Gibt Statistiken zum aktuellen Index zurück."""
    index = load_index(project_root)
    if not index:
        return {"status": "kein Index vorhanden"}
    return {
        "status": "ok",
        "chunk_count": index.get("chunk_count", 0),
        "indexed_at": index.get("indexed_at", "?"),
        "project": index.get("project", "?"),
    }
