"""
BEACON suspicion scorer — F1–F6 log-odds fusion.

Factors from docs/01-ARCHITECTURE.md §4:
  F1  Recurrence        ≥3 sightings, ≥2 distinct cameras, within 14 days,
                        entity NOT on street whitelist
  F2  Time anomaly      Sightings concentrated in that hex's claim-peak hours
  F3  Crime correlation Within near-repeat kernel (≈400 m, ≈14 days) of a claim
  F4  Casing behaviour  Dwell/slow-pass: repeated sightings within 1 hour at same camera
  F5  Territory roaming Same entity across ≥2 non-adjacent high-risk hexes in one week
  F6  Modal corroboration Weapon detection or audio co-located in time+hex

Fusion: calibrated log-odds addition — each factor contributes independently.
Conflict gate: if whitelist match found for this entity+hex, ALL factors are
  suppressed and score is zeroed regardless of evidence mass (ADR-0002).
Machine ceiling: state never exceeds "candidate" — only a human verify call
  promotes to "flagged".

Haversine distance used for near-repeat checks (OSRM deferred to G2 per
Sbu's feasibility note in team/SBU.md).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from ..db.models import Entity, Sighting, Whitelist, Claim, Incident

# ── thresholds ────────────────────────────────────────────────────────────────
CANDIDATE_THRESHOLD = 0.40   # base_score ≥ this → state = "candidate"

# Log-odds weights (positive = suspicious). F1 recurrence is "the core rule"
# (docs/01 §4) — a plate/face seen ≥3× across ≥2 cameras is, on its own, worth a
# human glance, so F1 alone reaches the candidate tier. This is NOT a weakening
# of the ethics guarantee: candidate is the *machine ceiling* (ADR-0002), the
# tier that exists precisely to surface leads to a human; only a human verify
# call promotes candidate → flagged, and `new_state` here can never be "flagged".
# The other factors corroborate above the candidate line, they don't gate it.
_W = {
    "F1_recurrence":       0.40,   # = CANDIDATE_THRESHOLD: the core rule alone → candidate
    "F2_time_anomaly":     0.15,
    "F3_crime_corr":       0.15,
    "F4_casing":           0.20,
    "F5_roaming":          0.15,
    "F6_modal_corrob":     0.25,
}

# ── near-repeat geometry ──────────────────────────────────────────────────────
_NR_RADIUS_KM   = 0.4    # 400 m near-repeat kernel
_NR_WINDOW_DAYS = 14

# ── time windows ─────────────────────────────────────────────────────────────
_RECURRENCE_WINDOW_DAYS  = 14
_CASING_WINDOW_MINUTES   = 60
_ROAMING_WINDOW_DAYS     = 7
_PEAK_HOURS              = {0, 1, 22, 23}   # 00:00 spike from claims data


# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SuspicionResult:
    """Output of score_entity."""
    entity_id: str
    base_score: float
    factors: dict[str, float]   # factor_name → contribution [0, weight]
    conflict_gate_fired: bool   # True = whitelist suppressed everything
    new_state: str              # "observed" | "candidate"  (never "flagged")


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Straight-line great-circle distance in km (OSRM deferred to G2)."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1))
         * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


def score_entity(entity_id: str, db: Session) -> SuspicionResult:
    """
    Compute and persist the suspicion score for an entity.

    Called after every new sighting for entities that have a resolvable
    identity (plate or embedding ref). Idempotent — safe to call multiple
    times; always writes the latest score.

    Returns a SuspicionResult; caller is responsible for db.commit().
    """
    entity: Optional[Entity] = db.query(Entity).filter(
        Entity.id == entity_id
    ).first()

    if entity is None:
        raise ValueError(f"Entity {entity_id} not found")

    # ── 0. Conflict gate — check whitelist first ──────────────────────────
    # Fetch all sightings to know which hexes to check
    all_sightings = (
        db.query(Sighting)
        .filter(Sighting.entity_id == entity_id)
        .order_by(Sighting.ts.desc())
        .all()
    )

    sighting_hexes = {s.hex_id for s in all_sightings if s.hex_id}

    whitelist_hit = (
        db.query(Whitelist)
        .filter(
            Whitelist.entity_id == entity_id,
            Whitelist.hex_id.in_(sighting_hexes) if sighting_hexes else False,
        )
        .first()
    )

    # Also accept non-expired entries
    now = datetime.utcnow()
    if whitelist_hit and whitelist_hit.expires_at and whitelist_hit.expires_at < now:
        whitelist_hit = None  # Expired — treat as not present

    if whitelist_hit:
        # Conflict gate fired: zero everything, keep state as observed
        _persist_score(entity, 0.0, "observed", db)
        return SuspicionResult(
            entity_id=entity_id,
            base_score=0.0,
            factors={k: 0.0 for k in _W},
            conflict_gate_fired=True,
            new_state="observed",
        )

    # ── 1. Gather sighting windows ─────────────────────────────────────────
    cutoff_14d = now - timedelta(days=_RECURRENCE_WINDOW_DAYS)
    recent = [s for s in all_sightings if s.ts >= cutoff_14d]

    factors: dict[str, float] = {k: 0.0 for k in _W}

    # ── F1: Recurrence ────────────────────────────────────────────────────
    # ≥3 sightings, ≥2 distinct cameras, within 14 days
    if len(recent) >= 3:
        distinct_cameras = {s.camera_id for s in recent}
        if len(distinct_cameras) >= 2:
            # The core rule firing lands exactly on the candidate line; extra
            # sightings ramp it modestly above (capped at 1.25× the base weight).
            extra = min(len(recent) - 3, 4)           # 0–4 extra sightings
            factors["F1_recurrence"] = min(
                _W["F1_recurrence"] * (1.0 + 0.0625 * extra),
                _W["F1_recurrence"] * 1.25,
            )

    # ── F2: Time anomaly ──────────────────────────────────────────────────
    # Sightings concentrated in claim-peak hours
    if recent:
        peak_count = sum(1 for s in recent if s.ts.hour in _PEAK_HOURS)
        peak_ratio = peak_count / len(recent)
        if peak_ratio >= 0.5:
            factors["F2_time_anomaly"] = _W["F2_time_anomaly"] * peak_ratio

    # ── F3: Crime correlation — near-repeat kernel ────────────────────────
    # Within ≈400 m and ≈14 days of a claim or incident
    # Uses haversine; only runs if we have lat/lng on the sightings' cameras
    if recent:
        camera_hexes = {s.hex_id for s in recent if s.hex_id}
        # Get claims in last 14 days
        claim_cutoff = now - timedelta(days=_NR_WINDOW_DAYS)
        nearby_claims = (
            db.query(Claim)
            .filter(
                Claim.claim_date >= claim_cutoff,
                Claim.lat.isnot(None),
                Claim.lng.isnot(None),
            )
            .all()
        )

        # Get lat/lng of sightings from their cameras
        from ..db.models import Camera
        camera_ids = {s.camera_id for s in recent}
        cameras = {
            c.id: c
            for c in db.query(Camera).filter(Camera.id.in_(camera_ids)).all()
        }

        nr_hit = False
        for sighting in recent:
            cam = cameras.get(sighting.camera_id)
            if not cam or cam.lat is None or cam.lng is None:
                continue
            for claim in nearby_claims:
                dist = _haversine_km(cam.lat, cam.lng, claim.lat, claim.lng)
                if dist <= _NR_RADIUS_KM:
                    nr_hit = True
                    break
            if nr_hit:
                break

        if nr_hit:
            factors["F3_crime_corr"] = _W["F3_crime_corr"]

    # ── F4: Casing behaviour ──────────────────────────────────────────────
    # ≥2 sightings at the same camera within 60 minutes
    casing_cutoff = now - timedelta(days=_RECURRENCE_WINDOW_DAYS)
    recent_for_casing = [s for s in all_sightings if s.ts >= casing_cutoff]

    cam_times: dict[str, list[datetime]] = {}
    for s in recent_for_casing:
        cam_times.setdefault(s.camera_id, []).append(s.ts)

    casing_found = False
    for times in cam_times.values():
        times_sorted = sorted(times)
        for i in range(len(times_sorted) - 1):
            gap = (times_sorted[i + 1] - times_sorted[i]).total_seconds() / 60.0
            if gap <= _CASING_WINDOW_MINUTES:
                casing_found = True
                break
        if casing_found:
            break

    if casing_found:
        factors["F4_casing"] = _W["F4_casing"]

    # ── F5: Territory roaming ─────────────────────────────────────────────
    # ≥2 non-adjacent hexes within 7 days
    roam_cutoff = now - timedelta(days=_ROAMING_WINDOW_DAYS)
    roaming_sightings = [s for s in all_sightings if s.ts >= roam_cutoff and s.hex_id]
    roaming_hexes = {s.hex_id for s in roaming_sightings}

    if len(roaming_hexes) >= 2:
        # Simple proxy: ≥2 distinct hexes = roaming (H3 adjacency check deferred to G2)
        factors["F5_roaming"] = _W["F5_roaming"]

    # ── F6: Modal corroboration ───────────────────────────────────────────
    # Weapon detection or audio detection co-located with this entity's hex
    if recent:
        entity_hex_times: list[tuple[str, datetime]] = [
            (s.hex_id, s.ts) for s in recent if s.hex_id
        ]
        # Look for weapon/audio sightings (no entity_id link) in same hex/time
        for hex_id, ts in entity_hex_times:
            window_start = ts - timedelta(minutes=15)
            window_end   = ts + timedelta(minutes=15)
            modal_hit = (
                db.query(Sighting)
                .filter(
                    (Sighting.kind == "weapon") | (Sighting.modality == "audio"),
                    Sighting.hex_id == hex_id,
                    Sighting.ts >= window_start,
                    Sighting.ts <= window_end,
                )
                .first()
            )
            if modal_hit:
                factors["F6_modal_corrob"] = _W["F6_modal_corrob"]
                break

    # ── Fuse factors — simple additive log-odds ───────────────────────────
    base_score = sum(factors.values())
    base_score = min(base_score, 0.99)   # Hard cap — never 1.0

    # Machine ceiling: candidate only, never flagged
    new_state = "candidate" if base_score >= CANDIDATE_THRESHOLD else "observed"

    _persist_score(entity, base_score, new_state, db)

    return SuspicionResult(
        entity_id=entity_id,
        base_score=base_score,
        factors=factors,
        conflict_gate_fired=False,
        new_state=new_state,
    )


def _persist_score(
    entity: Entity,
    base_score: float,
    new_state: str,
    db: Session,
) -> None:
    """Write score and state back to entity. Caller commits."""
    entity.base_score   = base_score
    entity.last_updated = datetime.utcnow()
    # Only update state if the new state is not a demotion of a human-set "flagged"
    if entity.state != "flagged":
        entity.state = new_state
    db.add(entity)
