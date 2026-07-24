"""
G3 demo orchestration: one command returns the system to a known,
tell-a-story demo state (team/SBU.md G3 checklist).

Wipes all tables, then seeds a minimal scenario that lets the pitch
walk through the whole pipeline: a recurring entity crossing 2 cameras
in the same hex within the 14-day window (-> watch_candidate via
suspicion/scorer.py's F1), real Claim rows at the midnight peak hour
(00:00) in that same hex feeding /v1/risk + /v1/hotspots + /v1/routes/plan
honestly (real data, not invented calibration - see docs/07-TECH-STACK.md).

Run: python scripts/demo_reset.py   (from server/)
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db.database import SessionLocal, engine
from src.db.models import Base, Camera, Entity, Sighting, Claim
from src.suspicion.scorer import score_entity

DEMO_HEX = "hex_demo_soweto_01"
DEMO_LAT, DEMO_LNG = -26.2485, 27.8540  # Soweto-area coordinate, matches claims data region


def reset_schema() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def seed(db) -> None:
    now = datetime.utcnow()

    cam_a = Camera(id="cam_demo_a", name="Demo Camera A", location="Main St", hex_id=DEMO_HEX, lat=DEMO_LAT, lng=DEMO_LNG)
    cam_b = Camera(id="cam_demo_b", name="Demo Camera B", location="2nd Ave", hex_id=DEMO_HEX, lat=DEMO_LAT + 0.001, lng=DEMO_LNG + 0.001)
    db.add_all([cam_a, cam_b])

    entity = Entity(id="ent_demo_01", kind="vehicle", plate_text="DEMO123GP")
    db.add(entity)
    db.commit()

    # 3 sightings across 2 cameras inside the 14-day F1 recurrence window
    for i, cam_id in enumerate(["cam_demo_a", "cam_demo_b", "cam_demo_a"]):
        db.add(Sighting(
            camera_id=cam_id, entity_id=entity.id,
            ts=now - timedelta(days=13 - i * 4), hex_id=DEMO_HEX,
            kind="vehicle", modality="plate", confidence=0.92,
        ))

    # Real-shape claims at the verified midnight peak hour, same hex,
    # so /v1/risk + /v1/hotspots have honest signal to serve.
    for i in range(6):
        db.add(Claim(
            claim_number=f"DEMO-{i:03d}", claim_type="Theft", suburb="Demo Suburb",
            hex_id=DEMO_HEX, lat=DEMO_LAT, lng=DEMO_LNG,
            claim_date=now - timedelta(days=20 + i * 3), hour=0, hour_known=True,
            amount=12000.0,
        ))

    db.commit()

    # Ingest normally recomputes score per-sighting via the /v1/sightings
    # handler; seeding writes rows directly, so recompute once here to match.
    score_entity(entity.id, db)
    db.commit()


def main() -> None:
    reset_schema()
    db = SessionLocal()
    try:
        seed(db)
    finally:
        db.close()
    print(f"Demo state reset: 2 cameras, 1 recurring entity, 6 claims, all in {DEMO_HEX}.")
    print("Try: GET /v1/entities/ent_demo_01, GET /v1/risk?hex=" + DEMO_HEX + "&hour=0, GET /v1/hotspots")


if __name__ == "__main__":
    main()
