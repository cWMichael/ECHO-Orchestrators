from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from ..database import get_async_session
from ..services.project_service import ProjectService
from ..schemas.project import ProjectCreate, ProjectResponse

router = APIRouter(prefix="/api/v1", tags=["projects"])

@router.post("/projects", response_model=ProjectResponse, status_code=201)
async def create_project(
    project_data: ProjectCreate,
    db: AsyncSession = Depends(get_async_session),
    service: ProjectService = Depends(ProjectService)
):
    """
    Create a new project.

    Args:
        project_data (ProjectCreate): The data for creating the project.
        db (AsyncSession, optional): The database session. Defaults to Depends(get_async_session).
        service (ProjectService, optional): The project service instance. Defaults to Depends(ProjectService).

    Returns:
        ProjectResponse: The created project as response model.

    Raises:
        HTTPException: If there is an error during project creation.
    """
    return await service.create_project(db, project_data)
