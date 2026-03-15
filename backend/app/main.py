import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.app.core.config import get_settings
from backend.app.routers import auth, admin, generate, health, places, training, events, crm

settings = get_settings()

app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, tags=["Health"])
app.include_router(auth.router, prefix=settings.API_V1_PREFIX, tags=["Auth"])
app.include_router(admin.router, prefix=settings.API_V1_PREFIX, tags=["Admin"])
app.include_router(generate.router, prefix=settings.API_V1_PREFIX, tags=["Generate"])
app.include_router(places.router, prefix=settings.API_V1_PREFIX, tags=["Places"])
app.include_router(training.router, prefix=settings.API_V1_PREFIX, tags=["Training"])
app.include_router(events.router, prefix=settings.API_V1_PREFIX, tags=["Events"])
app.include_router(crm.router, prefix=settings.API_V1_PREFIX, tags=["CRM"])

# Serve React frontend static files in production
FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if FRONTEND_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIR / "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(request: Request, full_path: str):
        """Serve the React SPA for all non-API routes."""
        file_path = FRONTEND_DIR / full_path
        if file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(FRONTEND_DIR / "index.html"))
