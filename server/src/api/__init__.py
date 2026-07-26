"""API routers."""
from .sightings import router as sightings_router
from .entities import router as entities_router
from .alerts import router as alerts_router
from .risk import router as risk_router
from .hotspots_geo import router as hotspots_geo_router
from .routes import router as routes_router
from .safest_route import router as safest_route_router
from .incidents import router as incidents_router
from .events import router as events_router
from .cameras import router as cameras_router
from .vision_jobs import router as vision_jobs_router
from .assistant import router as assistant_router
from .audio_classify import router as audio_classify_router

__all__ = [
    "sightings_router", "entities_router", "alerts_router", "risk_router",
    "hotspots_geo_router", "routes_router", "safest_route_router",
    "incidents_router", "events_router", "cameras_router",
    "vision_jobs_router", "assistant_router", "audio_classify_router",
]
