"""API routers."""
from .sightings import router as sightings_router
from .entities import router as entities_router
from .alerts import router as alerts_router
from .risk import router as risk_router
from .routes import router as routes_router
from .incidents import router as incidents_router
from .events import router as events_router
from .cameras import router as cameras_router

__all__ = [
    "sightings_router", "entities_router", "alerts_router", "risk_router", "routes_router",
    "incidents_router", "events_router", "cameras_router",
]
