"""
Tests for the plate-read gate.

These exercise `gate_read` only — the pure decision rule — so they run without the
ONNX model, without cv2 and without a download. The model wrapper (`read_plate`) is
a thin BGR→RGB + slice around it and is covered by the live re-run recorded in
docs/BUILD-LOG.md, not here.

The confidence numbers below are the ones actually measured on 2026-07-25 against the
1080p hijacking clip, not invented examples: every one of the eight detected plates in
that footage produced either an empty read or plate-shaped junk.
"""
import pytest

from vision.plate_ocr import (
    MIN_CHAR_PROB,
    MIN_CROP_H,
    MIN_CROP_W,
    REASON_CROP_TOO_SMALL,
    REASON_EMPTY_READ,
    REASON_LOW_CHAR_CONFIDENCE,
    gate_read,
)

# text, weakest character probability — the four junk reads the local model returned.
# '00314247' is the dangerous one: syntactically it is a perfectly plausible
# registration, so plate_text.py cannot reject it. Confidence is the only thing that can.
OBSERVED_JUNK = [
    ("W444", 0.287),
    ("00314247", 0.201),
    ("444411", 0.164),
    ("1W4114", 0.156),
]


@pytest.mark.parametrize("text,weakest", OBSERVED_JUNK)
def test_observed_junk_reads_are_refused(text, weakest):
    probs = [0.95] * len(text)
    probs[0] = weakest
    read = gate_read(text, probs, width=120, height=60)
    assert not read.accepted
    assert read.reason == REASON_LOW_CHAR_CONFIDENCE
    # Refused, but not forgotten — the raw read stays available for audit.
    assert read.raw_text == text
    assert read.min_char_prob == pytest.approx(weakest)


def test_padding_slots_cannot_rescue_an_empty_read():
    """
    The model always returns 10 confidence slots. On an empty read the trailing
    padding slots score ~0.89 because the model is confident they are padding — so a
    min() over all ten would score a blank plate as a confident one. An empty read
    must be refused as empty regardless of how high those slots are.
    """
    read = gate_read("", [0.89] * 10, width=120, height=60)
    assert not read.accepted
    assert read.reason == REASON_EMPTY_READ
    assert read.min_char_prob is None


def test_padding_slots_beyond_the_text_are_ignored():
    """Only the first len(text) slots align with returned characters."""
    read = gate_read("CA123456", [0.9] * 8 + [0.05, 0.05], width=120, height=60)
    assert read.accepted
    assert read.min_char_prob == pytest.approx(0.9)


def test_whitespace_only_read_is_empty():
    assert gate_read("   ", [0.9] * 10, width=120, height=60).reason == REASON_EMPTY_READ


def test_crop_below_minimum_is_not_read():
    read = gate_read("CA123456", [0.99] * 8, width=MIN_CROP_W - 1, height=MIN_CROP_H)
    assert read.reason == REASON_CROP_TOO_SMALL
    read = gate_read("CA123456", [0.99] * 8, width=MIN_CROP_W, height=MIN_CROP_H - 1)
    assert read.reason == REASON_CROP_TOO_SMALL


def test_missing_confidences_are_refused_not_trusted():
    """A read with no confidence at all is unverifiable, so it is refused."""
    for probs in (None, []):
        read = gate_read("CA123456", probs, width=120, height=60)
        assert not read.accepted
        assert read.reason == REASON_LOW_CHAR_CONFIDENCE


def test_confident_read_is_accepted_and_uppercased():
    read = gate_read("ca123456", [0.9, 0.8, 0.95, 0.9, 0.9, 0.9, 0.9, 0.9], 120, 60)
    assert read.accepted
    assert read.text == "CA123456"
    assert read.min_char_prob == pytest.approx(0.8)
    assert read.mean_char_prob == pytest.approx(0.89375)


def test_threshold_is_a_floor_not_a_ceiling():
    """Exactly at the threshold passes; a hair below does not."""
    assert gate_read("AB12", [MIN_CHAR_PROB] * 4, 120, 60).accepted
    assert not gate_read("AB12", [MIN_CHAR_PROB - 0.001] * 4, 120, 60).accepted
