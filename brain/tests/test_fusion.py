import pytest

from brain.fusion import (
    STATE_FLAGGED,
    STATE_OBSERVED,
    STATE_WATCH_CANDIDATE,
    STATE_WHITELISTED,
    Entity,
    human_verify,
    recompute,
)


def _sighting(camera_id: str, ts: str) -> dict:
    return {"camera_id": camera_id, "ts": ts, "plate_text": "CA123456"}


def test_below_recurrence_stays_observed():
    e = Entity(entity_id="e1", plate_text="CA123456")
    e.sightings = [_sighting("cam_1", "2026-07-24T00:00:00Z")]
    recompute(e)
    assert e.state == STATE_OBSERVED
    assert e.factors == []


def test_recurrence_two_cameras_crosses_ceiling():
    e = Entity(entity_id="e1", plate_text="CA123456")
    e.sightings = [
        _sighting("cam_1", "2026-07-24T00:00:00Z"),
        _sighting("cam_2", "2026-07-24T00:05:00Z"),
        _sighting("cam_1", "2026-07-24T00:14:00Z"),
    ]
    recompute(e)
    assert e.state == STATE_WATCH_CANDIDATE
    assert "F1" in e.factors
    assert 0.0 < e.score < 1.0


def test_single_camera_never_crosses_ceiling():
    e = Entity(entity_id="e1", plate_text="CA123456")
    e.sightings = [_sighting("cam_1", f"2026-07-24T00:0{i}:00Z") for i in range(5)]
    recompute(e)
    assert e.state == STATE_OBSERVED  # F1 needs >=2 distinct cameras


def test_whitelist_suppresses_f1():
    e = Entity(entity_id="e1", plate_text="CA123456")
    e.sightings = [
        _sighting("cam_1", "2026-07-24T00:00:00Z"),
        _sighting("cam_2", "2026-07-24T00:05:00Z"),
        _sighting("cam_1", "2026-07-24T00:14:00Z"),
    ]
    recompute(e, is_whitelisted=True)
    assert e.state == STATE_WHITELISTED
    assert e.factors == []


def test_machine_can_never_reach_flagged():
    e = Entity(entity_id="e1", plate_text="CA123456")
    e.sightings = [_sighting("cam_1", "2026-07-24T00:00:00Z")] * 20
    recompute(e)
    assert e.state != STATE_FLAGGED  # ADR-0002: only human_verify can flag


def test_human_verify_requires_operator_id():
    e = Entity(entity_id="e1", state=STATE_WATCH_CANDIDATE)
    with pytest.raises(ValueError):
        human_verify(e, "flag", operator_id="")


def test_human_verify_flag():
    e = Entity(entity_id="e1", state=STATE_WATCH_CANDIDATE)
    human_verify(e, "flag", operator_id="op_1")
    assert e.state == STATE_FLAGGED


def test_frozen_state_ignores_new_sightings_after_human_decision():
    e = Entity(entity_id="e1", plate_text="CA123456", state=STATE_FLAGGED, score_log_odds=5.0, factors=["F1"])
    e.sightings = [_sighting("cam_1", "2026-07-24T00:00:00Z")]
    recompute(e)
    assert e.state == STATE_FLAGGED
    assert e.score_log_odds == 5.0
