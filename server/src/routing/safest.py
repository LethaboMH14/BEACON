"""
Route exposure scoring — the member-facing "safest route" question.

NOT THE PATROL PLANNER. routing/planner.py solves the opposite objective: it
sends a vehicle TOWARDS high-risk cells (maximise risk covered per patrol hour).
This scores a route so a member can go AROUND them. Do not extend planner.py
for this; the two objectives share a data source and nothing else.

WHAT IS REAL HERE AND WHAT IS NOT
Real: the exposure score. Every hotspot it samples is a genuine RiskCell row
from Ndu's pipeline (709 geocoded suburbs, >=5 claims each), and the score is a
distance-weighted sum of those suburbs' severities along the polyline you pass
in, time-weighted by whether you'd be passing through at that suburb's own
historical peak hour.

Not ours: the polyline itself. Road geometry needs a routing provider
(OpenRouteService). This module takes geometry as input rather than inventing
it, so the moment a real provider is wired in, nothing here changes. A caller
that has no provider is passing approximate geometry and must say so — that is
what `geometry_source` on the response is for, and the client is expected to
surface it.

HONESTY BOUNDARY (same as risk/forecast.py, hotspots_geo.py)
A suburb is a point, not a polygon. "Within 2 km of the Bryanston claims
centroid" is not "on a dangerous street". Exposure is a comparative number for
ranking two routes against each other — it is not a probability of being
robbed, and nothing here should ever be rendered as one.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, Optional, Sequence

# How far from a suburb's claims centroid we still count as "exposed to" it.
# 2.5 km is roughly the radius of a large Johannesburg suburb — beyond that,
# attributing a route's risk to that suburb's claims stops being defensible.
EXPOSURE_RADIUS_KM = 2.5

# Passing a suburb during its own historically peak hour costs more than passing
# it at 11am. Deliberately modest: this multiplies an already-soft signal, and an
# aggressive value would let time-of-day dominate actual claims severity.
PEAK_HOUR_MULTIPLIER = 1.6
# Hours either side of peak that get a partial boost — crime doesn't observe
# hour boundaries, and a hard cliff at :00 produces routes that flip absurdly.
PEAK_SHOULDER_HOURS = 1
PEAK_SHOULDER_MULTIPLIER = 1.25

# Sample the polyline every 250 m so a long straight leg through a hotspot is
# not scored the same as a single vertex clipping its edge.
SAMPLE_SPACING_KM = 0.25

EARTH_RADIUS_KM = 6371.0


@dataclass(frozen=True)
class HotspotPoint:
    """Minimal view of a RiskCell needed for scoring — keeps this module DB-free."""
    hex_id: str
    suburb: str
    lat: float
    lng: float
    severity: float
    peak_hour: int
    top_claim_type: Optional[str] = None
    incident_count: Optional[int] = None


@dataclass
class SuburbExposure:
    suburb: str
    hex_id: str
    severity: float
    top_claim_type: Optional[str]
    incident_count: Optional[int]
    # metres of this route that fall inside EXPOSURE_RADIUS_KM of the suburb
    exposed_metres: int
    at_peak_hour: bool
    contribution: float


@dataclass
class RouteScore:
    exposure_score: float
    distance_km: float
    suburbs: list[SuburbExposure] = field(default_factory=list)

    @property
    def worst(self) -> Optional[SuburbExposure]:
        return max(self.suburbs, key=lambda s: s.contribution) if self.suburbs else None


def haversine_km(a_lat: float, a_lng: float, b_lat: float, b_lng: float) -> float:
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp = p2 - p1
    dl = math.radians(b_lng - a_lng)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(h))


def densify(polyline: Sequence[tuple[float, float]], spacing_km: float = SAMPLE_SPACING_KM):
    """
    Yield (lat, lng, segment_km) sample points spaced ~spacing_km apart.

    A routing provider returns vertices at corners, not at even intervals: a 6 km
    straight stretch of the N1 can be two points. Scoring raw vertices would make
    that stretch count for as little as a 50 m side street. So we walk the line.
    Each sample carries the length it represents, which is what turns
    "how severe is this suburb" into "how much of my drive is inside it".
    """
    pts = list(polyline)
    if len(pts) < 2:
        if pts:
            yield pts[0][0], pts[0][1], 0.0
        return

    for (lat1, lng1), (lat2, lng2) in zip(pts, pts[1:]):
        seg_km = haversine_km(lat1, lng1, lat2, lng2)
        if seg_km <= 0:
            continue
        steps = max(1, int(seg_km / spacing_km))
        step_km = seg_km / steps
        for i in range(steps):
            f = (i + 0.5) / steps  # sample at segment midpoints
            yield lat1 + (lat2 - lat1) * f, lng1 + (lng2 - lng1) * f, step_km


def _time_multiplier(peak_hour: int, depart_hour: Optional[int]) -> tuple[float, bool]:
    if depart_hour is None:
        return 1.0, False
    # circular distance in hours
    d = abs(peak_hour - depart_hour)
    d = min(d, 24 - d)
    if d == 0:
        return PEAK_HOUR_MULTIPLIER, True
    if d <= PEAK_SHOULDER_HOURS:
        return PEAK_SHOULDER_MULTIPLIER, False
    return 1.0, False


def score_route(
    polyline: Sequence[tuple[float, float]],
    hotspots: Iterable[HotspotPoint],
    depart_hour: Optional[int] = None,
) -> RouteScore:
    """
    Exposure = sum over suburbs of severity * exposed_km * time_multiplier.

    Distance-weighted rather than count-weighted on purpose. A route that clips
    the corner of three hotspots for 200 m each should not outscore one that
    spends 4 km inside a single severe suburb, and count-weighting gets that
    backwards. Falloff inside the radius is linear (1 at the centroid -> 0 at
    the edge) — the centroid is itself an approximation, so anything sharper
    would be false precision.
    """
    spots = list(hotspots)
    samples = list(densify(polyline))
    distance_km = sum(s[2] for s in samples)

    exposed_km: dict[str, float] = {}
    for lat, lng, seg_km in samples:
        for h in spots:
            d = haversine_km(lat, lng, h.lat, h.lng)
            if d >= EXPOSURE_RADIUS_KM:
                continue
            falloff = 1.0 - (d / EXPOSURE_RADIUS_KM)
            exposed_km[h.hex_id] = exposed_km.get(h.hex_id, 0.0) + seg_km * falloff

    by_hex = {h.hex_id: h for h in spots}
    out: list[SuburbExposure] = []
    total = 0.0
    for hex_id, km in exposed_km.items():
        h = by_hex[hex_id]
        mult, at_peak = _time_multiplier(h.peak_hour, depart_hour)
        contribution = h.severity * km * mult
        total += contribution
        out.append(SuburbExposure(
            suburb=h.suburb,
            hex_id=hex_id,
            severity=round(h.severity, 4),
            top_claim_type=h.top_claim_type,
            incident_count=h.incident_count,
            exposed_metres=int(round(km * 1000)),
            at_peak_hour=at_peak,
            contribution=round(contribution, 4),
        ))

    out.sort(key=lambda s: s.contribution, reverse=True)
    return RouteScore(exposure_score=round(total, 4), distance_km=round(distance_km, 3), suburbs=out)


def compare_routes(scores: Sequence[RouteScore]) -> Optional[float]:
    """
    Percentage less exposure the best route has vs the worst, or None if there
    is nothing to compare. Returned rather than computed client-side so the
    number in the UI and the number in the logs can't drift apart.
    """
    if len(scores) < 2:
        return None
    best = min(s.exposure_score for s in scores)
    worst = max(s.exposure_score for s in scores)
    if worst <= 0:
        return None
    return round((worst - best) / worst * 100, 1)
