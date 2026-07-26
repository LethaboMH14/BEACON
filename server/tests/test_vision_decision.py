"""
Tests for vision/decision.py.

The machine ceiling is the thing under test. Every other property here matters,
but the one that must never regress is: no sequence of detections, at any
confidence, reaches ESCALATED without a named human. If that test ever needs
"fixing" to make a demo smoother, the demo is what's wrong.
"""
import pytest

from src.vision.decision import (
    WEAPON_CANDIDATE_CONFIDENCE,
    WEAPON_PERSISTENCE_FRAMES,
    WEAPON_SINGLE_FRAME_CONFIDENCE,
    Level,
    Situation,
    escalate,
    observe,
)
from src.vision.detectors import Detection


def _det(kind="weapon", label="pistol", confidence=0.6, ocr_text=None):
    return Detection(kind=kind, label=label, confidence=confidence,
                     bbox={"x": 10, "y": 10, "w": 40, "h": 40}, ocr_text=ocr_text)


def _sit():
    return Situation(source_id="cam_test")


# --- the machine ceiling ----------------------------------------------------

def test_machine_never_reaches_escalated():
    """The guarantee. 60 frames of a 99% weapon is still only CANDIDATE."""
    s = _sit()
    for i in range(60):
        observe(s, [_det(confidence=0.99)], t_seconds=float(i))
    assert s.level is Level.CANDIDATE
    assert s.escalated_by is None


def test_escalate_requires_an_actor():
    s = _sit()
    observe(s, [_det(confidence=0.9)], 1.0)
    with pytest.raises(ValueError, match="requires the id"):
        escalate(s, actor="")


def test_escalate_refuses_below_candidate():
    """The escalate path must not be live on a feed showing nothing."""
    s = _sit()
    observe(s, [], 1.0)
    with pytest.raises(ValueError, match="Nothing to escalate"):
        escalate(s, actor="op_lethabo")


def test_escalate_records_the_human():
    s = _sit()
    for i in range(3):
        observe(s, [_det(confidence=0.7)], float(i))
    escalate(s, actor="op_lethabo", note="armed, two suspects")
    assert s.level is Level.ESCALATED
    assert s.escalated_by == "op_lethabo"
    assert "op_lethabo" in s.level_reason
    assert "armed, two suspects" in s.level_reason
    assert any(e.code == "human_escalation" for e in s.evidence)


def test_machine_cannot_walk_back_a_human_escalation():
    """Losing sight of the weapon does not mean the emergency ended."""
    s = _sit()
    for i in range(3):
        observe(s, [_det(confidence=0.7)], float(i))
    escalate(s, actor="op_sbu")
    for i in range(10):
        observe(s, [], float(10 + i))   # nothing at all for ten frames
    assert s.level is Level.ESCALATED


# --- persistence vs confidence ---------------------------------------------

def test_single_frame_mid_confidence_stays_below_candidate():
    """The demo failure mode: one stray frame must not summon armed response."""
    s = _sit()
    observe(s, [_det(confidence=WEAPON_CANDIDATE_CONFIDENCE + 0.05)], 1.0)
    assert s.level is Level.NOTICE
    assert any(e.code == "single_frame" for e in s.evidence)


def test_persistent_mid_confidence_reaches_candidate():
    s = _sit()
    for i in range(WEAPON_PERSISTENCE_FRAMES):
        observe(s, [_det(confidence=WEAPON_CANDIDATE_CONFIDENCE + 0.05)], float(i))
    assert s.level is Level.CANDIDATE


def test_very_confident_single_frame_reaches_candidate():
    """Refusing to act on a 90% weapon because it appeared once is the wrong
    kind of caution."""
    s = _sit()
    observe(s, [_det(confidence=WEAPON_SINGLE_FRAME_CONFIDENCE + 0.05)], 1.0)
    assert s.level is Level.CANDIDATE


def test_persistent_but_low_confidence_stays_at_notice():
    s = _sit()
    for i in range(6):
        observe(s, [_det(confidence=0.35)], float(i))
    assert s.level is Level.NOTICE


def test_peak_confidence_not_last_confidence_drives_level():
    """A weapon that was clearly visible then partially occluded is still the
    same weapon — the level must not drop because the last frame was worse."""
    s = _sit()
    observe(s, [_det(confidence=0.9)], 0.0)
    observe(s, [_det(confidence=0.31)], 1.0)
    assert s.level is Level.CANDIDATE
    assert s.weapon_peak_confidence == pytest.approx(0.9)


# --- what plates and faces may and may not do -------------------------------

def test_plates_never_raise_past_notice():
    s = _sit()
    for i in range(40):
        observe(s, [_det(kind="plate", label="plate", confidence=0.99)], float(i))
    assert s.level is Level.NOTICE


def test_faces_never_raise_past_notice():
    s = _sit()
    for i in range(40):
        observe(s, [_det(kind="face", label="face", confidence=0.99)], float(i))
    assert s.level is Level.NOTICE


def test_seen_and_read_are_different_claims():
    """A plate in frame is 'seen'. Only OCR text counts as 'read' (ADR-0006)."""
    s = _sit()
    observe(s, [_det(kind="plate", confidence=0.9)], 0.0)
    observe(s, [_det(kind="plate", confidence=0.9, ocr_text="CA 123 456")], 1.0)
    assert s.plate_frames == 2
    assert s.plates_read == ["CA 123 456"]


def test_repeated_plate_read_is_not_double_counted():
    s = _sit()
    for i in range(5):
        observe(s, [_det(kind="plate", ocr_text="CA 123 456")], float(i))
    assert s.plates_read == ["CA 123 456"]


# --- reporting --------------------------------------------------------------

def test_empty_feed_is_quiet_with_no_action():
    s = _sit()
    for i in range(5):
        observe(s, [], float(i))
    assert s.level is Level.QUIET
    assert s.recommendation() == "No action needed."


def test_first_weapon_timestamp_is_the_first_not_the_latest():
    s = _sit()
    observe(s, [], 1.0)
    observe(s, [_det()], 7.0)
    observe(s, [_det()], 19.0)
    assert s.first_weapon_at_s == 7.0


def test_candidate_recommendation_asks_a_human_to_decide():
    s = _sit()
    for i in range(3):
        observe(s, [_det(confidence=0.7)], float(i))
    assert "escalate" in s.recommendation().lower()
    assert s.machine_ceiling_reached is True


def test_reason_quotes_a_real_confidence_number():
    """UI copy is generated from this string, so it must carry the actual
    number, not a vague adjective."""
    s = _sit()
    for i in range(3):
        observe(s, [_det(confidence=0.53)], float(i))
    assert "53%" in s.level_reason


def test_to_dict_is_json_shaped():
    s = _sit()
    observe(s, [_det(confidence=0.7)], 1.0)
    observe(s, [_det(kind="plate", ocr_text="CA 1")], 2.0)
    d = s.to_dict()
    assert d["level_name"] == "notice"
    assert d["counts"]["weapon_frames"] == 1
    assert d["counts"]["plates_read"] == ["CA 1"]
    assert isinstance(d["evidence"], list) and d["evidence"]
    assert d["escalated_by"] is None


def test_level_ordering_is_usable_for_comparisons():
    assert Level.QUIET < Level.NOTICE < Level.CANDIDATE < Level.ESCALATED
