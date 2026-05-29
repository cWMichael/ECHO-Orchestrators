"""
ECHO Orchestrator — Projekt-Auswahl API
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from config import get_settings
from project_registry import get_active_project_name, load_projects, resolve_project_path

logger = logging.getLogger("echo.project_router")

router = APIRouter(tags=["Projects"])


class SetActiveProjectRequest(BaseModel):
    name: str = Field(..., min_length=1, description="Schlüssel aus projects.json")


class ActiveProjectResponse(BaseModel):
    name: str | None
    path: str


@router.get("/projects", summary="Verfügbare Zielprojekte")
async def list_projects() -> dict[str, str]:
    return load_projects()


@router.get("/projects/active", response_model=ActiveProjectResponse)
async def get_active_project() -> ActiveProjectResponse:
    settings = get_settings()
    return ActiveProjectResponse(
        name=get_active_project_name(),
        path=settings.project_root,
    )


@router.post("/projects/active", response_model=ActiveProjectResponse)
async def set_active_project(request: SetActiveProjectRequest) -> ActiveProjectResponse:
    try:
        path = resolve_project_path(request.name)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    if not Path(path).exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Projektpfad existiert nicht: {path}",
        )

    logger.info("Aktives Zielprojekt: %s → %s", request.name, path)
    return ActiveProjectResponse(name=request.name, path=path)
