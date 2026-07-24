"""
BEACON FastAPI server — main application.
Sbu's contract from docs/01-ARCHITECTURE.md §5.
"""
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from .db import init_db
from .api import sightings_router, entities_router, alerts_router, risk_router, routes_router
from .ws import ws_router

# Load environment variables
load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # Startup: initialize database
    init_db()
    print("[OK] Database initialized")
    yield
    # Shutdown: cleanup if needed
    print("[OK] Server shutdown")


# Create FastAPI app
app = FastAPI(
    title="BEACON API",
    description="AI community-safety network — the light that stays on",
    version="0.1.0",
    lifespan=lifespan
)

# CORS middleware for dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(sightings_router, prefix="/v1", tags=["sightings"])
app.include_router(entities_router, prefix="/v1", tags=["entities"])
app.include_router(alerts_router, prefix="/v1", tags=["alerts"])
app.include_router(risk_router, prefix="/v1", tags=["risk"])
app.include_router(routes_router, prefix="/v1", tags=["routes"])
app.include_router(ws_router, tags=["websockets"])


@app.get("/")
async def root():
    """Health check."""
    return {
        "service": "BEACON",
        "version": "0.1.0",
        "status": "operational",
        "tagline": "the light that stays on"
    }


@app.get("/health")
async def health():
    """Detailed health check."""
    return {
        "status": "healthy",
        "database": "connected",
        "websocket": "ready"
    }
