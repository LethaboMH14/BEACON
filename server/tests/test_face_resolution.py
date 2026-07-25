"""
Face-embedding matching + plate-text sanitisation.

The plate-text cases are not invented: every string in test_rejects_observed_ocr_junk
was actually returned by the plate service when run over a 1080p SA hijacking
clip on 2026-07-25. That run is the reason the sanitiser exists.
"""
import numpy as np
import pytest

from src.suspicion.face_resolution import (
    EMBEDDING_DIM,
    MATCH_THRESHOLD,
    cosine_similarity,
    is_valid_embedding,
    normalize,
    resolve_face_entity,
)
from src.suspicion.plate_text import clean_plate_text, is_plausible_plate


def _vec(seed: int) -> list[float]:
    rng = np.random.default_rng(seed)
    return rng.normal(size=EMBEDDING_DIM).tolist()


def _nudge(vector: list[float], amount: float, seed: int = 99) -> list[float]:
    """A slightly different view of the same face."""
    rng = np.random.default_rng(seed)
    noise = rng.normal(size=EMBEDDING_DIM) * amount
    return (np.asarray(vector) + noise).tolist()


class TestNormalize:
    def test_produces_unit_vector(self):
        assert np.linalg.norm(normalize(_vec(1))) == pytest.approx(1.0)

    def test_zero_vector_survives_without_nan(self):
        # A NaN here would silently poison every later comparison.
        result = normalize([0.0] * EMBEDDING_DIM)
        assert np.all(np.isfinite(result))


class TestCosineSimilarity:
    def test_identical_vectors_score_one(self):
        v = _vec(2)
        assert cosine_similarity(v, v) == pytest.approx(1.0)

    def test_opposite_vectors_score_minus_one(self):
        v = _vec(3)
        assert cosine_similarity(v, [-x for x in v]) == pytest.approx(-1.0)

    def test_scale_invariant(self):
        # Magnitude carries no identity information — only direction does.
        v = _vec(4)
        assert cosine_similarity(v, [x * 7.5 for x in v]) == pytest.approx(1.0)

    def test_degenerate_input_scores_zero_not_nan(self):
        assert cosine_similarity(_vec(5), [0.0] * EMBEDDING_DIM) == 0.0

    def test_mismatched_dimensions_score_zero(self):
        assert cosine_similarity(_vec(6), [0.1, 0.2]) == 0.0


class TestIsValidEmbedding:
    def test_accepts_correct_width(self):
        assert is_valid_embedding(_vec(7))

    def test_rejects_wrong_width(self):
        assert not is_valid_embedding([0.1] * 128)

    def test_rejects_nan_and_inf(self):
        bad = _vec(8)
        bad[0] = float("nan")
        assert not is_valid_embedding(bad)
        bad[0] = float("inf")
        assert not is_valid_embedding(bad)

    def test_rejects_zero_vector(self):
        assert not is_valid_embedding([0.0] * EMBEDDING_DIM)

    def test_rejects_non_sequence(self):
        assert not is_valid_embedding(None)
        assert not is_valid_embedding("not an embedding")


class TestResolveFaceEntity:
    def test_no_known_faces_means_new_entity(self):
        entity_id, similarity = resolve_face_entity(_vec(10), {})
        assert entity_id is None
        assert similarity == 0.0

    def test_same_face_matches_itself(self):
        v = _vec(11)
        entity_id, similarity = resolve_face_entity(v, {"ent_a": [v]})
        assert entity_id == "ent_a"
        assert similarity == pytest.approx(1.0)

    def test_near_identical_view_matches(self):
        v = _vec(12)
        entity_id, similarity = resolve_face_entity(_nudge(v, 0.01), {"ent_a": [v]})
        assert entity_id == "ent_a"
        assert similarity >= MATCH_THRESHOLD

    def test_unrelated_face_does_not_match(self):
        # Two independent random 512-d directions are near-orthogonal, which is
        # the whole reason a cosine threshold separates people at all.
        entity_id, similarity = resolve_face_entity(_vec(13), {"ent_a": [_vec(14)]})
        assert entity_id is None
        assert similarity < MATCH_THRESHOLD

    def test_picks_the_closest_of_several_entities(self):
        target = _vec(15)
        known = {
            "ent_far": [_vec(16)],
            "ent_target": [target],
            "ent_other": [_vec(17)],
        }
        entity_id, similarity = resolve_face_entity(_nudge(target, 0.01), known)
        assert entity_id == "ent_target"

    def test_matches_against_any_stored_view_not_an_average(self):
        # An entity holding two very different views must still match the one
        # the new sighting actually resembles. A centroid would sit between
        # them and match neither — the reason max-over-views is used.
        view_a, view_b = _vec(18), _vec(19)
        entity_id, _ = resolve_face_entity(_nudge(view_b, 0.01), {"ent_a": [view_a, view_b]})
        assert entity_id == "ent_a"

    def test_similarity_returned_even_when_below_threshold(self):
        # Near-misses stay inspectable rather than collapsing to "no data".
        entity_id, similarity = resolve_face_entity(_vec(20), {"ent_a": [_vec(21)]})
        assert entity_id is None
        assert similarity != 0.0

    def test_invalid_query_embedding_never_matches(self):
        assert resolve_face_entity([0.1] * 10, {"ent_a": [_vec(22)]}) == (None, 0.0)

    def test_corrupt_stored_vectors_are_skipped_not_fatal(self):
        good = _vec(23)
        known = {"ent_bad": [[0.1] * 8], "ent_good": [good]}
        entity_id, _ = resolve_face_entity(good, known)
        assert entity_id == "ent_good"

    def test_all_stored_vectors_corrupt_yields_no_match(self):
        assert resolve_face_entity(_vec(24), {"ent_bad": [[0.0] * EMBEDDING_DIM]}) == (None, 0.0)


class TestPlateTextSanitiser:
    @pytest.mark.parametrize(
        "junk",
        [
            "```markdown\n\n```",  # LLM OCR emitted its own fencing
            "1234567890",          # no letters
            "1000000000000",       # no letters, over length
            "BUSINESS",            # chyron word, no digits
            "1",
            "6",
            "0000",
        ],
    )
    def test_rejects_observed_ocr_junk(self, junk):
        assert clean_plate_text(junk) is None

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("CA 123-456", "CA123456"),
            ("ca123456", "CA123456"),
            ("ND123456", "ND123456"),
            ("BX12CDGP", "BX12CDGP"),
        ],
    )
    def test_keeps_real_plates_and_normalises_separators(self, raw, expected):
        assert clean_plate_text(raw) == expected

    def test_separator_variants_collapse_to_one_identity(self):
        # Otherwise the same car becomes two entities.
        assert clean_plate_text("CA 123-456") == clean_plate_text("ca123.456")

    def test_plate_shaped_background_text_still_passes(self):
        # Documented limitation, asserted so it can't regress silently: this is
        # a plausibility filter, not a verifier. 'CASE 2000' was read off a news
        # chyron and nothing syntactic can reject it.
        assert clean_plate_text("CASE 2000") == "CASE2000"

    def test_none_and_empty_are_safe(self):
        assert clean_plate_text(None) is None
        assert clean_plate_text("") is None
        assert not is_plausible_plate(None)
