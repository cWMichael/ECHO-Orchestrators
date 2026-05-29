"""
ECHO Orchestrator — FastAPI Application Entry Point
"""

from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from core_router import router as orchestrator_router


settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    app.state.settings = settings
    # Banner — Port kommt ausschließlich aus settings (config.py / .env)
    print(
        f"\n"
        f"  ╔══════════════════════════════════════════════╗\n"
        f"  ║         ECHO ORCHESTRATOR  v{app.version:<16} ║\n"
        f"  ╠══════════════════════════════════════════════╣\n"
        f"  ║  Lokal : http://{settings.host}:{settings.port}/            ║\n"
        f"  ║  Docs  : http://127.0.0.1:{settings.port}/docs        ║\n"
        f"  ║  Env   : {settings.environment:<36} ║\n"
        f"  ╚══════════════════════════════════════════════╝\n"
    )
    yield
    # Shutdown — HTTP-Clients der Worker werden über worker.close() freigegeben,
    # falls ein Worker-Pool in zukünftigen Stufen eingeführt wird.


app = FastAPI(
    title="ECHO Orchestrator",
    description=(
        "Deterministische KI-Entwicklungsplattform für interne Tools. "
        "Human-in-the-Loop (zwei Gates), hybrides Modell-Routing (Anthropic / Ollama), "
        "isolierte Feature-Branches pro Task."
    ),
    version="0.4.0",  # Port 8020 — Shared Infrastructure Paradigma
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

# Alle Orchestrator-Endpunkte unter /api/v1:
#
#   POST   /api/v1/tasks                         — Task einreichen
#   POST   /api/v1/tasks/{id}/approve            — Gate 1: Worker-Run freigeben
#   POST   /api/v1/tasks/{id}/approve-diff       — Gate 2: Code-Diff freigeben
#   GET    /api/v1/tasks/{id}/diff               — Diff zur Ansicht abrufen
#   GET    /api/v1/tasks/{id}                    — Task-Status
#   GET    /api/v1/tasks                         — Alle Tasks (paginiert)
app.include_router(orchestrator_router, prefix="/api/v1")


@app.get("/health", tags=["System"])
async def health_check() -> dict:
    """Liveness-Check für Load-Balancer und Monitoring."""
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
