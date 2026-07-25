"""
Load Ndu's real hotspot pipeline output (hotspot_pipeline/hotspots_geocoded.csv)
into the database, closing the geocoding gap load_claims.py left open
(team/SBU.md 2026-07-25 review — "look at what Ndu/Sali built and see how it
connects").

Two things this does, both real data, nothing invented:
1. Backfills hex_id/lat/lng onto existing `Claim` rows whose SUBURB matches
   one of Ndu's 709 geocoded suburbs. This is the missing input `/v1/risk`'s
   claims-fallback, F3 near-repeat correlation, and the OR-Tools route
   planner's hex-centroid lookup all needed — before this they had zero
   claims to work with because every claim loaded with hex_id=None.
2. Writes one RiskCell row per geocoded suburb, at that suburb's own real
   peak_hour, with risk_score=severity_score (Ndu's composite frequency+cost
   score, already in [0,1]) and model_version="ndu-hotspot-v1". This
   supersedes the claims-fallback for that specific hex+hour via the
   existing 3-tier logic in src/risk/forecast.py — no contract change.
   Deliberately NOT written for all 24 hours: Ndu's data only tells us the
   ONE real peak hour per suburb, so that's the only hour tier-1 data exists
   for. Other hours still fall through to the honest claims-fallback.

hex_id is derived deterministically from the suburb name (not real H3 —
h3 was dropped from this repo already, see docs/07-TECH-STACK.md) and kept
to 15 chars to fit the existing `hex_id: String(15)` column.

Run: python scripts/load_hotspots.py [path-to-hotspots_geocoded.csv]
"""
from __future__ import annotations

import csv
import hashlib
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db.database import SessionLocal, init_db
from src.db.models import Claim, RiskCell

DEFAULT_CSV = Path(__file__).parent.parent.parent / "hotspot_pipeline" / "hotspots_geocoded.csv"
MODEL_VERSION = "ndu-hotspot-v1"


def suburb_hex_id(suburb: str) -> str:
    """Deterministic, short (<=15 char) hex_id from a suburb name."""
    digest = hashlib.md5(suburb.encode()).hexdigest()[:11]
    return f"hex_{digest}"


def load(csv_path: Path) -> None:
    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    init_db()
    db = SessionLocal()
    claims_backfilled = 0
    risk_cells_written = 0
    try:
        for row in rows:
            suburb = row["SUBURB"].strip().upper()
            hex_id = suburb_hex_id(suburb)
            lat = float(row["lat"])
            lon = float(row["lon"])
            peak_hour = int(row["peak_hour"])
            severity = min(max(float(row["severity_score"]), 0.0), 1.0)

            updated = (
                db.query(Claim)
                .filter(Claim.suburb == suburb, Claim.hex_id.is_(None))
                .update(
                    {Claim.hex_id: hex_id, Claim.lat: lat, Claim.lng: lon},
                    synchronize_session=False,
                )
            )
            claims_backfilled += updated

            db.add(RiskCell(
                hex_id=hex_id,
                forecast_date=datetime.utcnow(),
                hour=peak_hour,
                risk_score=severity,
                top_factors={
                    "top_claim_type": row["top_claim_type"],
                    "incident_count": int(row["incident_count"]),
                    "peak_month": row["peak_month"],
                    "peak_day_of_week": row["peak_day_of_week"],
                },
                model_version=MODEL_VERSION,
            ))
            risk_cells_written += 1

        db.commit()
    finally:
        db.close()

    print(f"Backfilled hex_id/lat/lng on {claims_backfilled} claim rows across {len(rows)} suburbs.")
    print(f"Wrote {risk_cells_written} RiskCell rows (model_version={MODEL_VERSION}).")


if __name__ == "__main__":
    csv_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_CSV
    if not csv_path.exists():
        raise SystemExit(f"hotspots_geocoded.csv not found at {csv_path}")
    load(csv_path)
