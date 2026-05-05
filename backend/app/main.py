import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.app.core.config import get_settings
from backend.app.core.observability import setup_observability
from backend.app.core.vertex_client import _ensure_init as init_vertex_ai
from backend.app.middleware.request_logger import RequestLoggingMiddleware
from backend.app.routers import auth, admin, generate, health, places, training, events, crm, copilot

settings = get_settings()

# Boot observability (Cloud Logging + Cloud Trace) before anything else
setup_observability()

# Pre-warm Vertex AI SDK connection
init_vertex_ai()

app = FastAPI(
    title=settings.APP_NAME,
    version="2.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Structured request logging with trace IDs
app.add_middleware(RequestLoggingMiddleware)

app.include_router(health.router, tags=["Health"])
app.include_router(auth.router, prefix=settings.API_V1_PREFIX, tags=["Auth"])
app.include_router(admin.router, prefix=settings.API_V1_PREFIX, tags=["Admin"])
app.include_router(generate.router, prefix=settings.API_V1_PREFIX, tags=["Generate"])
app.include_router(places.router, prefix=settings.API_V1_PREFIX, tags=["Places"])
app.include_router(training.router, prefix=settings.API_V1_PREFIX, tags=["Training"])
app.include_router(events.router, prefix=settings.API_V1_PREFIX, tags=["Events"])
app.include_router(crm.router, prefix=settings.API_V1_PREFIX, tags=["CRM"])
app.include_router(copilot.router, prefix=settings.API_V1_PREFIX, tags=["Copilot"])

# Serve React frontend static files in production
FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if FRONTEND_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIR / "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(request: Request, full_path: str):
        file_path = FRONTEND_DIR / full_path
        if file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(FRONTEND_DIR / "index.html"))
