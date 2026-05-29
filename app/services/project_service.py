from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.models.project import Project as ProjectModel
from app.schemas.project import ProjectCreate, ProjectResponse
from app.exceptions.http_exceptions import HTTPException

class ProjectService:
    async def create_project(
        self,
        db: AsyncSession,
        project_data: ProjectCreate
    ) -> ProjectResponse:
        """
        Creates a new project in the database.

        Args:
            db (AsyncSession): The asynchronous database session.
            project_data (ProjectCreate): The data for the project to be created.

        Returns:
            ProjectResponse: The created project response model.

        Raises:
            HTTPException: If there is an integrity error during creation.
        """
        new_project = ProjectModel(**project_data.model_dump())
        db.add(new_project)
        
        try:
            await db.commit()
        except IntegrityError as e:
            await db.rollback()
            raise HTTPException(status_code=400, detail="Project already exists") from e
        
        await db.refresh(new_project)
        return ProjectResponse.from_orm(new_project)
