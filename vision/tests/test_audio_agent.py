import numpy as np
import pytest

from vision.audio_agent import CONFIDENCE_MIN, map_yamnet_class

CLASSES = {"427": "gunshot", "195": "glass_break", "395": "scream", "39": "raised_voices"}


def _scores(hits: dict[int, float]) -> np.ndarray:
    scores = np.zeros(521, dtype=np.float32)
    for idx, val in hits.items():
        scores[idx] = val
    return scores


def test_gunshot_class_wins():
    scores = _scores({427: 0.9, 195: 0.1})
    label, confidence = map_yamnet_class(scores, CLASSES)
    assert label == "gunshot"
    assert confidence == pytest.approx(0.9)


def test_below_confidence_min_returns_none():
    scores = _scores({427: CONFIDENCE_MIN - 0.01})
    label, _ = map_yamnet_class(scores, CLASSES)
    assert label is None


def test_ignores_classes_outside_interest_set():
    scores = _scores({100: 0.99, 427: 0.4})  # class 100 not in CLASSES, must be ignored
    label, confidence = map_yamnet_class(scores, CLASSES)
    assert label == "gunshot"
    assert confidence == pytest.approx(0.4)


def test_no_hits_returns_none():
    scores = _scores({})
    label, _ = map_yamnet_class(scores, CLASSES)
    assert label is None
