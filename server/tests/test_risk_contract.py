"""
Contract tests for GET /v1/risk, GET /v1/hotspots.
Contract from docs/01-ARCHITECTURE.md §5. Honesty boundary from
src/risk/forecast.py's module header — these tests lock in that boundary,
not just the shapes.
"""
from datetime import datetime, timedelta

import pytest

from src.db.models import Claim, RiskCell
from src.risk.forecast import (
    estimate_hex_risk,
    rank_hotspots,
    FALLBACK_LABEL,
    NO_DATA_LABEL,
)


def _make_claim(db, hex_id, hour=None, hour_known=False, amount=10000.0, claim_number=None):
    c = Claim(
        claim_number=claim_number or f"C-{hex_id}-{hour}-{amount}",
        claim_type="Theft",
        suburb="Test Suburb",
        hex_id=hex_id,
        claim_date=datetime.utcnow() - timedelta(days=30),
        hour=hour,
        hour_known=hour_known,
        amount=amount,
    )
    db.add(c)
    db.commit()
    return c


def test_no_data_for_a_hex_with_zero_claims(db_session):
    result = estimate_hex_risk("hex_never_seen", 12, db_session)
    assert result.source == "no_data"
    assert result.risk_score == 0.0
    assert result.label == NO_DATA_LABEL


def test_claims_fallback_is_honestly_labelled_not_calibrated(db_session):
    _make_claim(db_session, "hex_a", hour=3, hour_known=True)
    result = estimate_hex_risk("hex_a", 3, db_session)
    assert result.source == "claims_fallback"
    assert result.label == FALLBACK_LABEL
    assert 0.0 < result.risk_score <= 1.0
    assert "not a calibrated probability" in result.label


def test_peak_hour_scores_higher_than_off_peak_for_the_same_claims(db_session):
    # Same claim set, only the QUERIED hour differs — 00:00 is in the real
    # midnight-spike peak set (docs/04), 12:00 is not.
    for i in range(5):
        _make_claim(db_session, "hex_b", hour=0, hour_known=True, claim_number=f"peak-{i}")

    peak = estimate_hex_risk("hex_b", 0, db_session)
    offpeak = estimate_hex_risk("hex_b", 12, db_session)
    assert peak.risk_score > offpeak.risk_score


def test_more_claims_in_a_hex_scores_higher_than_fewer(db_session):
    for i in range(2):
        _make_claim(db_session, "hex_few", claim_number=f"few-{i}")
    for i in range(15):
        _make_claim(db_session, "hex_many", claim_number=f"many-{i}")

    few = estimate_hex_risk("hex_few", 12, db_session)
    many = estimate_hex_risk("hex_many", 12, db_session)
    assert many.risk_score > few.risk_score


def test_real_model_row_wins_over_the_claims_fallback(db_session):
    # Even with claims present in this hex, a real RiskCell row (Ndu's model,
    # once it lands) must be trusted over the fallback — that's the whole
    # point of the tiering.
    _make_claim(db_session, "hex_c", hour=5, hour_known=True)
    cell = RiskCell(
        hex_id="hex_c", forecast_date=datetime.utcnow(), hour=5,
        risk_score=0.42, top_factors={"real": "factor"}, model_version="ndu-v1",
    )
    db_session.add(cell)
    db_session.commit()

    result = estimate_hex_risk("hex_c", 5, db_session)
    assert result.source == "model"
    assert result.risk_score == 0.42
    assert result.model_version == "ndu-v1"
    assert result.label == "model:ndu-v1"


def test_invalid_hour_rejected(db_session):
    with pytest.raises(ValueError):
        estimate_hex_risk("hex_a", 24, db_session)
    with pytest.raises(ValueError):
        estimate_hex_risk("hex_a", -1, db_session)


def test_rank_hotspots_orders_by_score_descending(db_session):
    _make_claim(db_session, "hex_low", claim_number="low-1")
    for i in range(10):
        _make_claim(db_session, "hex_high", claim_number=f"high-{i}")

    ranked = rank_hotspots(12, db_session, limit=10)
    ids = [e.hex_id for e in ranked]
    assert ids.index("hex_high") < ids.index("hex_low")


def test_rank_hotspots_respects_limit(db_session):
    for h in range(5):
        _make_claim(db_session, f"hex_{h}", claim_number=f"lim-{h}")
    ranked = rank_hotspots(12, db_session, limit=2)
    assert len(ranked) == 2


# ---- endpoint-level (via TestClient, using conftest's client fixture) ----

def test_get_risk_endpoint_shape(client, db_session):
    _make_claim(db_session, "hex_ep", hour=1, hour_known=True)
    res = client.get("/v1/risk", params={"hex": "hex_ep", "hour": 1})
    assert res.status_code == 200
    body = res.json()
    assert body["hex_id"] == "hex_ep"
    assert body["hour"] == 1
    assert body["source"] == "claims_fallback"
    assert "not a calibrated probability" in body["label"]


def test_get_risk_defaults_hour_to_current_utc_hour_when_omitted(client, db_session):
    res = client.get("/v1/risk", params={"hex": "hex_never_seen"})
    assert res.status_code == 200
    assert res.json()["source"] == "no_data"


def test_get_risk_rejects_out_of_range_hour(client, db_session):
    res = client.get("/v1/risk", params={"hex": "hex_ep", "hour": 24})
    assert res.status_code == 422  # FastAPI query validation, not our ValueError path


def test_get_hotspots_endpoint_shape(client, db_session):
    _make_claim(db_session, "hex_hs", hour=0, hour_known=True)
    res = client.get("/v1/hotspots", params={"window": 0, "limit": 5})
    assert res.status_code == 200
    body = res.json()
    assert body["hour"] == 0
    assert isinstance(body["hotspots"], list)
    assert any(h["hex_id"] == "hex_hs" for h in body["hotspots"])


def test_post_risk_cells_ingest_shape(client, db_session):
    res = client.post("/v1/risk-cells", json={
        "cells": [{
            "hex_id": "hex_ndu_01",
            "forecast_date": datetime.utcnow().isoformat(),
            "hour": 0,
            "risk_score": 0.83,
            "top_factors": {"near_repeat": 0.5, "peak_hour": 0.33},
            "model_version": "ndu-lgbm-v1",
        }],
    })
    assert res.status_code == 201
    assert res.json() == {"inserted": 1}

    row = db_session.query(RiskCell).filter(RiskCell.hex_id == "hex_ndu_01").first()
    assert row is not None
    assert row.model_version == "ndu-lgbm-v1"


def test_post_risk_cells_supersedes_the_claims_fallback(client, db_session):
    # Real claims give the fallback something to say for this hex/hour...
    _make_claim(db_session, "hex_ndu_02", hour=0, hour_known=True)
    fallback = client.get("/v1/risk", params={"hex": "hex_ndu_02", "hour": 0}).json()
    assert fallback["source"] == "claims_fallback"

    # ...but a real model row for the same hex/hour must win over it.
    client.post("/v1/risk-cells", json={
        "cells": [{
            "hex_id": "hex_ndu_02", "forecast_date": datetime.utcnow().isoformat(),
            "hour": 0, "risk_score": 0.91, "model_version": "ndu-lgbm-v1",
        }],
    })
    res = client.get("/v1/risk", params={"hex": "hex_ndu_02", "hour": 0})
    body = res.json()
    assert body["source"] == "model"
    assert body["risk_score"] == 0.91
    assert body["model_version"] == "ndu-lgbm-v1"


def test_post_risk_cells_rejects_out_of_range_score(client, db_session):
    res = client.post("/v1/risk-cells", json={
        "cells": [{
            "hex_id": "hex_bad", "forecast_date": datetime.utcnow().isoformat(),
            "hour": 0, "risk_score": 1.5, "model_version": "v1",
        }],
    })
    assert res.status_code == 422


def test_post_risk_cells_rejects_empty_batch(client, db_session):
    res = client.post("/v1/risk-cells", json={"cells": []})
    assert res.status_code == 422
