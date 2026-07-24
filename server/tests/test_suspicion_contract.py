"""
Contract tests for suspicion scorer.
VUKA style: validate factor computation, conflict gate, machine ceiling.
Contract from docs/01-ARCHITECTURE.md §4, ADR-0002.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from datetime import datetime, timedelta
import pytest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.db.models import Base, Entity, Sighting, Camera, Whitelist, Claim
from src.suspicion.scorer import score_entity, CANDIDATE_THRESHOLD


@pytest.fixture
def db_session():
    """In-memory DB for scorer tests."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _make_camera(db, cam_id: str, hex_id: str = "881f1d4a9ffffff", lat: float = -26.0, lng: float = 28.0):
    cam = Camera(
        id=cam_id,
        name=f"Camera {cam_id}",
        hex_id=hex_id,
        lat=lat,
        lng=lng,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(cam)
    db.commit()
    return cam


def _make_entity(db, entity_id: str, plate: str = None):
    ent = Entity(
        id=entity_id,
        kind="vehicle",
        plate_text=plate,
        first_seen=datetime.utcnow(),
        last_seen=datetime.utcnow(),
        sighting_count=0,
    )
    db.add(ent)
    db.commit()
    return ent


def _make_sighting(db, entity_id: str, camera_id: str, ts: datetime, hex_id: str = "881f1d4a9ffffff"):
    s = Sighting(
        camera_id=camera_id,
        entity_id=entity_id,
        ts=ts,
        hex_id=hex_id,
        kind="vehicle",
        modality="plate",
        confidence=0.9,
        created_at=datetime.utcnow(),
    )
    db.add(s)
    db.commit()
    return s


def test_f1_recurrence_basic(db_session):
    """
    F1: >=3 sightings, >=2 cameras, within 14 days → recurrence factor fires.
    """
    _make_camera(db_session, "cam_001")
    _make_camera(db_session, "cam_002")
    ent = _make_entity(db_session, "ent_001", plate="ABC123")

    now = datetime.utcnow()
    _make_sighting(db_session, "ent_001", "cam_001", now - timedelta(days=1))
    _make_sighting(db_session, "ent_001", "cam_001", now - timedelta(hours=12))
    _make_sighting(db_session, "ent_001", "cam_002", now)

    result = score_entity("ent_001", db_session)
    db_session.commit()

    assert result.factors["F1_recurrence"] > 0, "F1 should fire for >=3 sightings across >=2 cameras"
    assert result.base_score >= CANDIDATE_THRESHOLD
    assert result.new_state == "candidate"


def test_f1_suppressed_by_whitelist(db_session):
    """
    Conflict gate: if entity is on whitelist for any sighted hex, score zeroes.
    """
    _make_camera(db_session, "cam_001")
    ent = _make_entity(db_session, "ent_002", plate="XYZ999")

    now = datetime.utcnow()
    _make_sighting(db_session, "ent_002", "cam_001", now - timedelta(days=1))
    _make_sighting(db_session, "ent_002", "cam_001", now - timedelta(hours=12))
    _make_sighting(db_session, "ent_002", "cam_001", now)

    # Add whitelist entry
    wl = Whitelist(
        entity_id="ent_002",
        hex_id="881f1d4a9ffffff",
        kind="resident",
        added_by="op_001",
        added_at=datetime.utcnow(),
    )
    db_session.add(wl)
    db_session.commit()

    result = score_entity("ent_002", db_session)
    db_session.commit()

    assert result.conflict_gate_fired, "Conflict gate should fire when entity is whitelisted"
    assert result.base_score == 0.0
    assert result.new_state == "observed"


def test_f2_time_anomaly_peak_hours(db_session):
    """
    F2: sightings concentrated in claim-peak hours (0, 1, 22, 23) → factor fires.
    """
    _make_camera(db_session, "cam_010")
    ent = _make_entity(db_session, "ent_010", plate="TIME001")

    now = datetime.utcnow()
    # 3 sightings all in peak hours (22:00, 23:00, 00:00)
    _make_sighting(db_session, "ent_010", "cam_010", now.replace(hour=22, minute=0))
    _make_sighting(db_session, "ent_010", "cam_010", now.replace(hour=23, minute=0))
    _make_sighting(db_session, "ent_010", "cam_010", now.replace(hour=0, minute=0))

    result = score_entity("ent_010", db_session)
    db_session.commit()

    assert result.factors["F2_time_anomaly"] > 0, "F2 should fire for peak-hour concentration"


def test_f3_crime_correlation_near_repeat(db_session):
    """
    F3: sighting within 400m and 14 days of a claim → factor fires.
    """
    cam = _make_camera(db_session, "cam_020", lat=-26.1, lng=28.1)
    ent = _make_entity(db_session, "ent_020", plate="NEAR001")

    now = datetime.utcnow()
    _make_sighting(db_session, "ent_020", "cam_020", now)

    # Add a claim within 400m
    claim = Claim(
        claim_number="CLM001",
        claim_type="Theft",
        suburb="Test Suburb",
        lat=-26.10001,  # Very close to camera
        lng=28.10001,
        claim_date=now - timedelta(days=5),
    )
    db_session.add(claim)
    db_session.commit()

    result = score_entity("ent_020", db_session)
    db_session.commit()

    assert result.factors["F3_crime_corr"] > 0, "F3 should fire for near-repeat claim"


def test_f4_casing_behaviour(db_session):
    """
    F4: >=2 sightings at same camera within 60 minutes → casing factor fires.
    """
    _make_camera(db_session, "cam_030")
    ent = _make_entity(db_session, "ent_030", plate="CASE001")

    now = datetime.utcnow()
    _make_sighting(db_session, "ent_030", "cam_030", now - timedelta(minutes=30))
    _make_sighting(db_session, "ent_030", "cam_030", now)

    result = score_entity("ent_030", db_session)
    db_session.commit()

    assert result.factors["F4_casing"] > 0, "F4 should fire for sightings within 60 min at same camera"


def test_f5_territory_roaming(db_session):
    """
    F5: same entity across >=2 distinct hexes within 7 days → roaming factor fires.
    """
    _make_camera(db_session, "cam_040a", hex_id="881f1d4a9ffffff")
    _make_camera(db_session, "cam_040b", hex_id="881f1d4b9ffffff")  # Different hex
    ent = _make_entity(db_session, "ent_040", plate="ROAM001")

    now = datetime.utcnow()
    _make_sighting(db_session, "ent_040", "cam_040a", now - timedelta(days=1), hex_id="881f1d4a9ffffff")
    _make_sighting(db_session, "ent_040", "cam_040b", now, hex_id="881f1d4b9ffffff")

    result = score_entity("ent_040", db_session)
    db_session.commit()

    assert result.factors["F5_roaming"] > 0, "F5 should fire for roaming across distinct hexes"


def test_f6_modal_corroboration_weapon(db_session):
    """
    F6: weapon detection co-located in time+hex with entity's sighting → factor fires.
    """
    _make_camera(db_session, "cam_060")
    ent = _make_entity(db_session, "ent_060", plate="WEAPON001")

    now = datetime.utcnow()
    _make_sighting(db_session, "ent_060", "cam_060", now)

    # Add weapon sighting in same hex, overlapping time window (±15 min)
    weapon = Sighting(
        camera_id="cam_060",
        entity_id=None,
        ts=now + timedelta(minutes=5),
        hex_id="881f1d4a9ffffff",
        kind="weapon",
        modality="yolo",
        confidence=0.85,
        created_at=datetime.utcnow(),
    )
    db_session.add(weapon)
    db_session.commit()

    result = score_entity("ent_060", db_session)
    db_session.commit()

    assert result.factors["F6_modal_corrob"] > 0, "F6 should fire for co-located weapon detection"


def test_machine_ceiling_never_flagged(db_session):
    """
    Machine ceiling: even with all factors firing, state never exceeds 'candidate'.
    Only a human verify call can promote to 'flagged'.

    Fixture deliberately satisfies every factor's actual trigger condition
    (checked against scorer.py, not assumed):
      F1 recurrence   — >=3 sightings across >=2 distinct cameras
      F2 time anomaly — >=50% of sightings in the {0,1,22,23} peak-hour set
      F3 crime corr   — a Claim within the 400m/14d near-repeat kernel
      F4 casing       — >=2 sightings at the same camera <=60 min apart
      F5 roaming      — >=2 distinct hexes within 7 days
      F6 modal corrob — a weapon sighting in the same hex within 15 min
    Previous version only actually satisfied F4+F5 (single camera → F1 never
    fires; no weapon sighting → F6 never fires) and depended on the real
    wall-clock hour landing in the peak set for F2 — flaky by construction,
    not a genuine "all factors" case. Anchored to a fixed midnight timestamp
    instead of datetime.utcnow() so F2 fires deterministically regardless of
    when the suite runs.
    """
    cam_a = _make_camera(db_session, "cam_999a", hex_id="881f1d4a9ffffff", lat=-26.2, lng=28.2)
    cam_b = _make_camera(db_session, "cam_999b", hex_id="881f1d4aaffffff", lat=-26.2001, lng=28.2001)
    ent = _make_entity(db_session, "ent_999", plate="MAX999")

    # Anchored to "1 day ago, at 00:30" rather than a fixed calendar date — the
    # scorer's F1/F3 windows are real `datetime.utcnow()`-relative cutoffs (14
    # days), so a hardcoded past date silently ages out of every window as
    # real time passes. Still lands on hour 0 (inside the {0,1,22,23} peak set)
    # for F2, deterministically, regardless of what day the suite runs.
    anchor = (datetime.utcnow() - timedelta(days=1)).replace(hour=0, minute=30, second=0, microsecond=0)

    # F1 (>=2 cameras) + F4 (<=60min gap, same camera) + F5 (>=2 hexes) together:
    _make_sighting(db_session, "ent_999", "cam_999a", anchor,                        hex_id="881f1d4a9ffffff")
    _make_sighting(db_session, "ent_999", "cam_999a", anchor + timedelta(minutes=30), hex_id="881f1d4a9ffffff")
    _make_sighting(db_session, "ent_999", "cam_999b", anchor + timedelta(hours=1),    hex_id="881f1d4aaffffff")

    # F2: all three sightings above sit at hour 0 or 1 — peak_ratio = 1.0.

    # F3: a claim inside the 400m/14d near-repeat kernel of cam_999a.
    claim = Claim(
        claim_number="TEST-CLAIM-999",
        claim_type="Theft",
        suburb="Test Suburb",
        claim_date=anchor - timedelta(days=2),
        lat=-26.2005, lng=28.2005,  # ~70m from cam_999a — well inside 400m
        amount=15000.0,
    )
    db_session.add(claim)

    # F6: a weapon sighting co-located in hex + time with one of the entity's sightings.
    weapon = Sighting(
        camera_id="cam_999a", entity_id=None, ts=anchor + timedelta(minutes=5),
        hex_id="881f1d4a9ffffff", kind="weapon", modality="vision", confidence=0.8,
        created_at=datetime.utcnow(),
    )
    db_session.add(weapon)
    db_session.commit()

    result = score_entity("ent_999", db_session)
    db_session.commit()

    expected_factors = {
        "F1_recurrence", "F2_time_anomaly", "F3_crime_corr",
        "F4_casing", "F5_roaming", "F6_modal_corrob",
    }
    fired = {k for k, v in result.factors.items() if v > 0}
    assert fired == expected_factors, f"expected every factor to fire, got: {fired}"
    assert result.new_state == "candidate", "Scorer should only promote to candidate, never flagged"
    assert result.base_score >= CANDIDATE_THRESHOLD

    # Verify that the entity in DB is still 'candidate'
    db_session.refresh(ent)
    assert ent.state == "candidate", "Entity state in DB should be candidate, not flagged"
