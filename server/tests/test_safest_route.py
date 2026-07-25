"""
Unit tests for routing/safest.py — the member-facing route exposure score.

Pure math, no DB: HotspotPoint exists precisely so this module can be tested
without seeding claims. The properties tested here are the ones the UI makes
claims about ("29% less claims exposure", "passes 1.4 km through Bryanston"),
so if one of these breaks, a number on screen becomes a lie.
"""
import math

import pytest

from src.routing.safest import (
    EXPOSURE_RADIUS_KM,
    PEAK_HOUR_MULTIPLIER,
    PEAK_SHOULDER_MULTIPLIER,
    HotspotPoint,
    compare_routes,
    densify,
    haversine_km,
    score_route,
)


def _spot(lat, lng, severity=0.8, peak_hour=12, hex_id="hex_a", suburb="TESTBURG"):
    return HotspotPoint(
        hex_id=hex_id, suburb=suburb, lat=lat, lng=lng,
        severity=severity, peak_hour=peak_hour,
        top_claim_type="Theft", incident_count=42,
    )


# --- geometry ---------------------------------------------------------------

def test_haversine_known_distance():
    # Sandton CBD -> Fourways, ~14 km apart in reality.
    d = haversine_km(-26.1076, 28.0567, -26.0167, 28.0093)
    assert 10.0 < d < 14.0


def test_densify_preserves_total_length():
    """The sum of sample weights must equal the polyline's real length —
    otherwise exposed_km, and every distance shown to a member, is wrong."""
    line = [(-26.10, 28.05), (-26.05, 28.02), (-26.01, 28.01)]
    direct = sum(haversine_km(*a, *b) for a, b in zip(line, line[1:]))
    total = sum(s[2] for s in densify(line))
    assert total == pytest.approx(direct, rel=1e-9)


def test_densify_walks_long_straight_segments():
    """A 2-vertex straight leg must produce many samples, not two. This is the
    whole reason densify exists — raw-vertex scoring undercounts long legs."""
    line = [(-26.20, 28.00), (-26.00, 28.00)]  # ~22 km, two vertices
    samples = list(densify(line, spacing_km=0.25))
    assert len(samples) > 50


def test_densify_degenerate_inputs():
    assert list(densify([])) == []
    assert list(densify([(-26.0, 28.0)])) == [(-26.0, 28.0, 0.0)]
    # zero-length segment contributes nothing rather than dividing by zero
    assert list(densify([(-26.0, 28.0), (-26.0, 28.0)])) == []


# --- exposure scoring -------------------------------------------------------

def test_route_far_from_every_hotspot_scores_zero():
    far = _spot(-33.92, 18.42)  # Cape Town
    s = score_route([(-26.10, 28.05), (-26.05, 28.02)], [far])
    assert s.exposure_score == 0.0
    assert s.suburbs == []


def test_hotspot_beyond_radius_is_excluded():
    """Boundary check: the falloff is linear to zero at the edge, so a spot
    just outside must contribute nothing at all, not a small amount."""
    # place the spot ~1.2x the radius away, perpendicular is unnecessary —
    # a point route is enough to isolate the distance test.
    deg_per_km = 1 / 110.574
    spot = _spot(-26.10 + EXPOSURE_RADIUS_KM * 1.2 * deg_per_km, 28.05)
    s = score_route([(-26.10, 28.05), (-26.10, 28.06)], [spot])
    assert s.exposure_score == 0.0


def test_longer_time_inside_a_hotspot_scores_higher():
    """Distance-weighted, not count-weighted: the docstring's core claim."""
    spot = _spot(-26.10, 28.05)
    short = score_route([(-26.10, 28.049), (-26.10, 28.051)], [spot])
    long_ = score_route([(-26.10, 28.03), (-26.10, 28.07)], [spot])
    assert long_.exposure_score > short.exposure_score


def test_severity_scales_contribution_linearly():
    line = [(-26.10, 28.04), (-26.10, 28.06)]
    low = score_route(line, [_spot(-26.10, 28.05, severity=0.2)])
    high = score_route(line, [_spot(-26.10, 28.05, severity=0.8)])
    # abs tolerance, not rel: exposure_score is rounded to 4 dp on the way out,
    # so scaling an already-rounded value can't land inside a 1e-6 relative band.
    assert high.exposure_score == pytest.approx(low.exposure_score * 4, abs=1e-3)


def test_three_clipped_hotspots_can_lose_to_one_sustained_one():
    """The scenario the docstring names explicitly: clipping three corners must
    not automatically beat 4 km inside one severe suburb."""
    deg = 1 / 110.574
    clipped = [
        _spot(-26.10 + 2.3 * deg, 28.05 + i * 0.05, severity=0.9, hex_id=f"h{i}")
        for i in range(3)
    ]
    sustained = _spot(-26.10, 28.05, severity=0.9, hex_id="hs")
    line = [(-26.10, 28.02), (-26.10, 28.16)]
    a = score_route(line, clipped)
    b = score_route(line, [sustained])
    assert b.exposure_score > a.exposure_score


def test_worst_returns_top_contributor():
    line = [(-26.10, 28.04), (-26.10, 28.06)]
    mild = _spot(-26.10, 28.05, severity=0.2, hex_id="mild", suburb="MILD")
    nasty = _spot(-26.10, 28.05, severity=0.9, hex_id="nasty", suburb="NASTY")
    s = score_route(line, [mild, nasty])
    assert s.worst is not None and s.worst.suburb == "NASTY"
    # sorted descending by contribution, so the UI's "top contributor" is [0]
    assert s.suburbs[0].suburb == "NASTY"


def test_exposed_metres_is_reported_in_metres():
    spot = _spot(-26.10, 28.05)
    s = score_route([(-26.10, 28.03), (-26.10, 28.07)], [spot])
    assert s.suburbs[0].exposed_metres > 100  # not 0.x km mislabelled as metres
    assert isinstance(s.suburbs[0].exposed_metres, int)


# --- time weighting ---------------------------------------------------------

def test_departing_at_peak_hour_costs_more():
    spot = _spot(-26.10, 28.05, peak_hour=18)
    line = [(-26.10, 28.04), (-26.10, 28.06)]
    off = score_route(line, [spot], depart_hour=6)
    peak = score_route(line, [spot], depart_hour=18)
    assert peak.exposure_score == pytest.approx(off.exposure_score * PEAK_HOUR_MULTIPLIER, abs=1e-3)
    assert peak.suburbs[0].at_peak_hour is True
    assert off.suburbs[0].at_peak_hour is False


def test_shoulder_hour_gets_partial_boost_not_full():
    spot = _spot(-26.10, 28.05, peak_hour=18)
    line = [(-26.10, 28.04), (-26.10, 28.06)]
    base = score_route(line, [spot], depart_hour=6).exposure_score
    shoulder = score_route(line, [spot], depart_hour=17).exposure_score
    assert shoulder == pytest.approx(base * PEAK_SHOULDER_MULTIPLIER, abs=1e-3)
    # a shoulder hour is not the peak — the flag drives UI copy
    assert score_route(line, [spot], depart_hour=17).suburbs[0].at_peak_hour is False


def test_hour_distance_wraps_around_midnight():
    """23:00 and 00:00 are one hour apart, not 23 — a naive abs() would rank a
    midnight departure through a 23:00-peak suburb as perfectly safe."""
    spot = _spot(-26.10, 28.05, peak_hour=23)
    line = [(-26.10, 28.04), (-26.10, 28.06)]
    base = score_route(line, [spot], depart_hour=6).exposure_score
    midnight = score_route(line, [spot], depart_hour=0).exposure_score
    assert midnight == pytest.approx(base * PEAK_SHOULDER_MULTIPLIER, abs=1e-3)


def test_no_depart_hour_applies_no_time_weighting():
    spot = _spot(-26.10, 28.05, peak_hour=12)
    line = [(-26.10, 28.04), (-26.10, 28.06)]
    assert score_route(line, [spot]).exposure_score == pytest.approx(
        score_route(line, [spot], depart_hour=3).exposure_score
    )


# --- comparison -------------------------------------------------------------

def test_compare_routes_percentage():
    a = score_route([(-26.10, 28.04), (-26.10, 28.06)], [_spot(-26.10, 28.05)])
    b = score_route([(-33.92, 18.42), (-33.90, 18.44)], [_spot(-26.10, 28.05)])
    pct = compare_routes([a, b])
    assert pct == 100.0  # b is clear of everything


def test_compare_routes_needs_two_routes():
    a = score_route([(-26.10, 28.04), (-26.10, 28.06)], [_spot(-26.10, 28.05)])
    assert compare_routes([a]) is None
    assert compare_routes([]) is None


def test_compare_routes_returns_none_when_both_are_clear():
    """Both routes score zero: there is no honest percentage to report, and
    0/0 must not surface as '0% safer' or crash."""
    clear = _spot(-33.92, 18.42)
    a = score_route([(-26.10, 28.04), (-26.10, 28.06)], [clear])
    b = score_route([(-26.11, 28.04), (-26.11, 28.06)], [clear])
    assert compare_routes([a, b]) is None
