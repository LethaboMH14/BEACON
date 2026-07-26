"""
Tests for the YAMNet glass-break decision rule.

These use constructed 521-class score vectors rather than audio. The behaviour
under test is not "does YAMNet work" (it is a pretrained model) but "does our
rule reject the things that were falsely firing" — above all speech, which is
what a pure frequency heuristic cannot do and which is the reason this module
exists at all.
"""
from __future__ import annotations

import base64

import numpy as np
import pytest

from src.audio.yamnet import (
    COMPETING_LABELS,
    GLASS_LABELS,
    Verdict,
    _index_of,
    decide,
    resolve_indices,
)

GLASS_IDX = resolve_indices(GLASS_LABELS)
COMPETING_IDX = resolve_indices(COMPETING_LABELS)


def scores(**by_label: float) -> np.ndarray:
    """A score vector with the named classes set and everything else near zero."""
    v = np.full(521, 1e-4, dtype=np.float32)
    idx = _index_of()
    for label, score in by_label.items():
        v[idx[label.replace("_", " ")]] = score
    return v


def call(v: np.ndarray) -> dict:
    return decide(v, GLASS_IDX, COMPETING_IDX)


class TestLabelResolution:
    def test_glass_labels_all_exist_in_the_model(self):
        assert len(resolve_indices(GLASS_LABELS)) == len(GLASS_LABELS)

    def test_glass_indices_are_not_the_bell_classes_models_json_claimed(self):
        """models.json had 195/198 as glass_break; they are Bell and Bicycle bell.

        This test is the guard against reintroducing hand-written indices.
        """
        idx = _index_of()
        assert idx["Bell"] == 195
        assert idx["Bicycle bell"] == 198
        assert 195 not in GLASS_IDX and 198 not in GLASS_IDX
        assert idx["Glass"] == 435 and idx["Shatter"] == 437

    def test_speech_is_a_competitor(self):
        """If speech ever stopped competing, the original bug would return."""
        assert _index_of()["Speech"] in COMPETING_IDX

    def test_unknown_labels_are_skipped_not_fatal(self):
        assert resolve_indices(("Glass", "Not A Real AudioSet Class")) == [435]


class TestGlassAccepted:
    def test_clear_glass_break_fires(self):
        r = call(scores(Glass=0.62, Shatter=0.41))
        assert r["verdict"] == Verdict.GLASS
        assert r["glass_label"] == "Glass"

    def test_energy_split_across_glass_classes_still_fires(self):
        """One glass event spreads probability over Glass/Shatter/Breaking, so no
        single class looks confident. The floor is set low for exactly this."""
        r = call(scores(Glass=0.11, Shatter=0.10, Breaking=0.09))
        assert r["verdict"] == Verdict.GLASS


class TestSpeechAndFriendsRejected:
    def test_speech_does_not_fire_even_with_glass_above_the_floor(self):
        """The case the user actually hit: talking near the mic. Glass clears the
        absolute floor, but speech dominates, so the margin rule vetoes it."""
        r = call(scores(Speech=0.94, Glass=0.12))
        assert r["verdict"] == Verdict.OTHER
        assert r["clears_floor"] is True
        assert r["beats_competing"] is False
        assert r["competing_label"] == "Speech"

    @pytest.mark.parametrize(
        "label",
        ["Conversation", "Shout", "Screaming", "Singing", "Music", "Laughter"],
    )
    def test_every_vocal_class_outvotes_a_weak_glass_score(self, label):
        r = call(scores(Glass=0.12, **{label.replace(" ", "_"): 0.8}))
        assert r["verdict"] == Verdict.OTHER

    @pytest.mark.parametrize("label", ["Slam", "Knock", "Clapping", "Typing", "Car"])
    def test_impact_and_ambient_sounds_are_rejected(self, label):
        """A slammed door and a clap are the transients the DSP gate cannot
        distinguish; the classifier is what separates them from glass."""
        r = call(scores(Glass=0.10, **{label: 0.7}))
        assert r["verdict"] == Verdict.OTHER

    def test_silence_does_not_fire(self):
        r = call(scores(Silence=0.99))
        assert r["verdict"] == Verdict.OTHER
        assert r["clears_floor"] is False


class TestMarginBoundary:
    def test_glass_must_beat_the_competitor_by_the_margin_not_merely_tie(self):
        # Glass ahead, but not by 1.5x — deliberately not enough.
        assert call(scores(Glass=0.30, Speech=0.25))["verdict"] == Verdict.OTHER
        assert call(scores(Glass=0.30, Speech=0.15))["verdict"] == Verdict.GLASS

    def test_below_the_floor_never_fires_however_clean_the_field(self):
        r = call(scores(Glass=0.05))
        assert r["clears_floor"] is False
        assert r["verdict"] == Verdict.OTHER

    def test_top_five_is_returned_so_a_wrong_call_is_diagnosable(self):
        r = call(scores(Speech=0.9, Glass=0.12, Music=0.3))
        assert [t["label"] for t in r["top"]][:3] == ["Speech", "Music", "Glass"]


class TestEndpointContract:
    """The endpoint's validation, which must not depend on the model loading."""

    @pytest.fixture()
    def client(self):
        from fastapi.testclient import TestClient

        from src.main import app

        return TestClient(app)

    def test_rejects_a_non_16k_sample_rate_rather_than_guessing(self, client):
        body = {"pcm16": base64.b64encode(b"\x00\x00" * 100).decode(), "sample_rate": 44100}
        r = client.post("/v1/audio/classify", json=body)
        assert r.status_code == 422
        assert "16000" in r.json()["detail"]

    def test_rejects_malformed_base64(self, client):
        r = client.post("/v1/audio/classify", json={"pcm16": "not!base64!", "sample_rate": 16000})
        assert r.status_code == 422

    def test_rejects_an_odd_byte_count_that_cannot_be_int16(self, client):
        r = client.post(
            "/v1/audio/classify",
            json={"pcm16": base64.b64encode(b"\x01\x02\x03").decode(), "sample_rate": 16000},
        )
        assert r.status_code == 422

    def test_a_real_window_classifies_as_not_glass(self, client):
        """White noise is not glass. Also proves the model actually loads and the
        response matches the declared schema — skipped where litert is absent."""
        pytest.importorskip("ai_edge_litert")
        rng = np.random.default_rng(0)
        pcm = (rng.normal(0, 0.05, 15_600) * 32767).astype("<i2")
        r = client.post(
            "/v1/audio/classify",
            json={"pcm16": base64.b64encode(pcm.tobytes()).decode(), "sample_rate": 16000},
        )
        assert r.status_code == 200, r.text
        assert r.json()["verdict"] == Verdict.OTHER
        assert len(r.json()["top"]) == 5
