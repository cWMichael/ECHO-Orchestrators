from pydantic import BaseModel, Field

class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(None, max_length=1024)

class ProjectResponse(BaseModel):
    id: int
    name: str
    description: str | None

    class Config:
        orm_mode = True
