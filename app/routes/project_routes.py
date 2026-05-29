from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.schemas.project import ProjectCreate, ProjectResponse
from app.services.project_service import ProjectService

router = APIRouter(prefix="/api/v1", tags=["projects"])

@router.post("/projects", response_model=ProjectResponse, status_code=201)
async def create_project(
    project_data: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    service: ProjectService = Depends(ProjectService)
) -> ProjectResponse:
    """
    Endpoint to create a new project.

    Args:
        project_data (ProjectCreate): The data for the project to be created.
        db (AsyncSession): The asynchronous database session.
        service (ProjectService): The project service layer.

    Returns:
        ProjectResponse: The created project response model.

    Raises:
        HTTPException: If there is an error during creation.
    """
    try:
        return await service.create_project(db, project_data)
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error") from e
