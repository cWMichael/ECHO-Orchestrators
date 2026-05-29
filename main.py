"""

ECHO Orchestrator - FastAPI Application Entry Point

"""



from contextlib import asynccontextmanager



import uvicorn

from fastapi import FastAPI

from fastapi.middleware.cors import CORSMiddleware



from config import get_settings

from core_router import router as orchestrator_router

from planner_router import router as planner_router

from project_router import router as project_router





settings = get_settings()





@asynccontextmanager

async def lifespan(app: FastAPI):

    """Startup / shutdown lifecycle."""

    app.state.settings = settings

    print(

        f"\n"

        f"  \n"

        f"           ECHO ORCHESTRATOR  v{app.version:<16} \n"

        f"  \n"

        f"    Lokal : http://{settings.host}:{settings.port}/            \n"

        f"    Docs  : http://127.0.0.1:{settings.port}/docs        \n"

        f"    Env   : {settings.environment:<36} \n"

        f"  \n"

    )

    yield





app = FastAPI(

    title="ECHO Orchestrator",

    description=(

        "Deterministische KI-Entwicklungsplattform fuer interne Tools. "

        "Human-in-the-Loop (zwei Gates), lokale Modell-Ausfuehrung via Ollama, "

        "isolierte Feature-Branches pro Task."

    ),

    version="0.4.0",

    lifespan=lifespan,

    docs_url="/docs",

    redoc_url="/redoc",

)



app.add_middleware(

    CORSMiddleware,

    allow_origins=settings.cors_origins,

    allow_credentials=True,

    allow_methods=["*"],

    allow_headers=["*"],

)



# Orchestrator-Endpunkte unter /api/v1:

#   POST   /api/v1/tasks, /tasks/{id}/approve, /tasks/{id}/approve-diff

#   GET    /api/v1/tasks, /tasks/{id}, /tasks/{id}/diff

#   POST   /api/v1/plan, /plan/{id}/approve

#   GET    /api/v1/projects, /projects/active  |  POST /projects/active

app.include_router(orchestrator_router, prefix="/api/v1")

app.include_router(planner_router, prefix="/api/v1")

app.include_router(project_router, prefix="/api/v1")





@app.get("/health", tags=["System"])

async def health_check() -> dict:

    """Liveness-Check fuer Load-Balancer und Monitoring."""

    return {

        "status": "ok",

        "version": app.version,

        "environment": settings.environment,

    }





if __name__ == "__main__":

    uvicorn.run(

        "main:app",

        host=settings.host,

        port=settings.port,

        reload=settings.debug,

        log_level=settings.log_level.lower(),

    )


