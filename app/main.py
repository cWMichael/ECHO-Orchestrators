from fastapi import FastAPI

app = FastAPI(title="Project Management API", version="1.0.0")

# Include the project routes
from app.routes.project_routes import router as projects_router
app.include_router(projects_router)

@app.on_event("startup")
async def startup():
    # Initialize database tables
    pass

@app.on_event("shutdown")
async def shutdown():
    # Clean up resources
    pass
