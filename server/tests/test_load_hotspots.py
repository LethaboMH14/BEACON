"""
Tests for scripts/load_hotspots.py — the loader that connects Ndu's real
hotspot_pipeline/hotspots_geocoded.csv output to the server's RiskCell table
and backfills hex_id/lat/lng onto existing Claim rows (team/SBU.md 2026-07-25:
"see what Ndu/Sali built and see how it connects").

Uses a small in-memory CSV fixture, not the real 709-row file, so this test
doesn't depend on hotspot_pipeline/ being present or unchanged.
"""
import csv
from datetime import datetime, timedelta

import pytest

from src.db.models import Claim, RiskCell
from scripts.load_hotspots import load, suburb_hex_id


def _write_csv(path, rows):
    fieldnames = [
        "SUBURB", "incident_count", "top_claim_type", "top_claim_type_count",
        "claim_type_breakdown", "peak_month", "peak_day_of_week", "peak_hour",
        "total_claim_cost", "avg_claim_cost", "anomalous_claims_excluded_from_cost",
        "freq_normalized", "cost_normalized", "severity_score", "lat", "lon",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _base_row(**overrides):
    row = {
        "SUBURB": "TESTSUBURB", "incident_count": "10", "top_claim_type": "Theft",
        "top_claim_type_count": "8", "claim_type_breakdown": "Theft:8",
        "peak_month": "May", "peak_day_of_week": "Friday", "peak_hour": "12",
        "total_claim_cost": "100000", "avg_claim_cost": "10000",
        "anomalous_claims_excluded_from_cost": "0", "freq_normalized": "0.5",
        "cost_normalized": "0.5", "severity_score": "0.65",
        "lat": "-26.1", "lon": "28.05",
    }
    row.update(overrides)
    return row


def test_suburb_hex_id_is_short_and_deterministic():
    a = suburb_hex_id("BRYANSTON")
    b = suburb_hex_id("BRYANSTON")
    c = suburb_hex_id("SANDTON")
    assert a == b
    assert a != c
    assert len(a) <= 15


def test_load_backfills_matching_claims_and_writes_risk_cell(tmp_path, db_session, monkeypatch):
    csv_path = tmp_path / "hotspots_geocoded.csv"
    _write_csv(csv_path, [_base_row()])

    claim = Claim(
        claim_number="TEST-001", claim_type="Theft", suburb="TESTSUBURB",
        hex_id=None, lat=None, lng=None,
        claim_date=datetime.utcnow() - timedelta(days=10), hour=12, hour_known=True,
        amount=5000.0,
    )
    db_session.add(claim)
    db_session.commit()

    import scripts.load_hotspots as loader
    monkeypatch.setattr(loader, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(loader, "init_db", lambda: None)
    # db_session.close() would end the test's own session — no-op it for this call
    monkeypatch.setattr(db_session, "close", lambda: None)

    load(csv_path)

    expected_hex = suburb_hex_id("TESTSUBURB")
    db_session.refresh(claim)
    assert claim.hex_id == expected_hex
    assert claim.lat == -26.1
    assert claim.lng == 28.05

    cell = db_session.query(RiskCell).filter(RiskCell.hex_id == expected_hex).first()
    assert cell is not None
    assert cell.hour == 12
    assert cell.risk_score == 0.65
    assert cell.model_version == "ndu-hotspot-v1"
    assert cell.top_factors["top_claim_type"] == "Theft"


def test_load_does_not_overwrite_claims_that_already_have_a_hex_id(tmp_path, db_session, monkeypatch):
    csv_path = tmp_path / "hotspots_geocoded.csv"
    _write_csv(csv_path, [_base_row(SUBURB="ALREADYGEOCODED")])

    claim = Claim(
        claim_number="TEST-002", claim_type="Theft", suburb="ALREADYGEOCODED",
        hex_id="hex_already_set", lat=1.0, lng=2.0,
        claim_date=datetime.utcnow() - timedelta(days=10), hour=12, hour_known=True,
        amount=5000.0,
    )
    db_session.add(claim)
    db_session.commit()

    import scripts.load_hotspots as loader
    monkeypatch.setattr(loader, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(loader, "init_db", lambda: None)
    monkeypatch.setattr(db_session, "close", lambda: None)

    load(csv_path)

    db_session.refresh(claim)
    assert claim.hex_id == "hex_already_set"  # untouched, not clobbered
    assert claim.lat == 1.0
