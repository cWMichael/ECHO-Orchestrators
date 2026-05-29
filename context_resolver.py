"""
ECHO Orchestrator — Context Resolver
Entscheidet welche Rule-Layer für einen gegebenen Task-Typ geladen werden.
Niemals alles in jeden Prompt — nur was relevant ist.
"""
from __future__ import annotations

from models import WorkerType

# Mapping: WorkerType / Task-Typ → relevante Layer
_LAYER_MAP: dict[str, list[str]] = {
    # Worker-basiert
    WorkerType.BACKEND:   ["core", "architecture", "security"],
    WorkerType.FRONTEND:  ["core", "architecture", "security"],
    WorkerType.TEST:      ["core", "architecture"],
    WorkerType.DOCS:      ["core", "branding"],
    WorkerType.RETRIEVAL: ["core", "security", "connectors"],
    # Generische Task-Typen (für Planner)
    "backend_task":    ["core", "architecture", "security"],
    "frontend_task":   ["core", "architecture", "security"],
    "content_task":    ["core", "branding"],
    "connector_task":  ["core", "security", "connectors"],
    "ai_task":         ["core", "security", "architecture"],
    "default":         ["core", "security"],
}


def resolve_layers(worker_type: str | WorkerType) -> list[str]:
    """
    Gibt die relevanten Layer-IDs für einen Worker-Typ zurück.
    Fallback auf 'default' wenn kein Mapping existiert.
    """
    key = worker_type if isinstance(worker_type, str) else worker_type
    return _LAYER_MAP.get(key, _LAYER_MAP["default"])


def classify_task(description: str, worker_type: str) -> str:
    """
    Klassifiziert einen Task grob anhand von Keywords falls kein Worker-Typ bekannt.
    Gibt einen Task-Typ-String zurück.
    """
    desc_lower = description.lower()
    if any(k in desc_lower for k in ["api", "python", "fastapi", "backend", "datei", "file", "script"]):
        return "backend_task"
    if any(k in desc_lower for k in ["ui", "frontend", "button", "design", "css", "html", "react"]):
        return "frontend_task"
    if any(k in desc_lower for k in ["text", "content", "blog", "artikel", "bild", "brand", "marketing"]):
        return "content_task"
    if any(k in desc_lower for k in ["connector", "sync", "sharepoint", "azure", "crm"]):
        return "connector_task"
    return worker_type or "default"
