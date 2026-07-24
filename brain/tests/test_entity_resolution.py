from brain.entity_resolution import confusion_aware_distance, match_quality, resolve_plate_entity


def test_identical_plates_full_quality():
    assert match_quality("CA123456", "CA123456") == 1.0


def test_ocr_confusion_scores_high_not_perfect():
    # "0" read where plate has "O" — same car, OCR noise (docs/01 §3 Flock cautionary tale)
    q = match_quality("CA0123456", "CAO123456")
    assert 0.9 < q < 1.0


def test_different_plate_scores_low():
    q = match_quality("CA123456", "GP999000")
    assert q < 0.3


def test_resolve_creates_new_when_no_match():
    entity_id, quality = resolve_plate_entity("CA123456", {})
    assert entity_id is None


def test_resolve_matches_existing_within_threshold():
    known = {"entity-1": "CA0123456"}
    entity_id, quality = resolve_plate_entity("CAO123456", known)
    assert entity_id == "entity-1"
    assert quality >= 0.8


def test_confusion_distance_symmetric():
    assert confusion_aware_distance("CA0123", "CAO123") == confusion_aware_distance("CAO123", "CA0123")
