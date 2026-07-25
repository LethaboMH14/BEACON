"""
BEACON risk forecast (docs/01-ARCHITECTURE.md §2.4, §5) — GET /v1/risk, /v1/hotspots.

HONESTY BOUNDARY (CLAUDE.md D10, ADR-0002's spirit extended to forecasting):
Ndu's real model (docs/02-DATA-FORECASTING.md — seasonal baseline + near-repeat
kernel + LightGBM with context covariates) has not landed on `data/` yet at the
time this was written. Rather than block G2's endpoints on that, or invent a
fake-calibrated number, this module does exactly what VUKA's `compute_risk`
did in the same situation: serves the best REAL signal actually available
today, labelled honestly as provisional, with an explicit path for the real
model to slot in without changing the contract.

Two tiers, tried in order:
  1. `RiskCell` table — if Ndu's forecast pipeline has written a row for this
     (hex_id, hour), trust it and pass through its own model_version/label.
     This is the tier that becomes authoritative once G2's real forecast lands
     — nothing here needs to change when it does.
  2. Fallback: a real (not fabricated) score derived directly from `Claim` rows
     in that hex — claim count + severity, with a same-hour proximity boost
     matching scorer.py's own {0,1,22,23} peak-hour set (docs/04 — the real
     midnight spike in the claims data). This is NOT a calibrated probability;
     every response is explicitly labelled "provisional".
  3. Zero claims ever recorded for that hex → risk_score=0.0, labelled
     "no_data", not silently omitted or guessed at.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db.models import Claim, RiskCell

# Same peak-hour set as suspicion/scorer.py's F2 — the real 00:00 claims spike
# (docs/04 §1's midnight peak, verified against Gradhack_Insure_Data.xlsx).
_PEAK_HOURS = {0, 1, 22, 23}
_PEAK_HOUR_BOOST = 1.4

# Claim-count normalisation: a hex needs this many historical claims before its
# fallback score approaches 1.0. Not fitted — a display-scaling constant, not a
# calibration claim (same honesty boundary as scorer.py's own log-odds weights).
_SATURATION_CLAIM_COUNT = 20.0

FALLBACK_LABEL = (
    "provisional — derived from raw historical claim counts in this hex, "
    "not Ndu's calibrated forecast model (not yet integrated); "
    "not a calibrated probability"
)
NO_DATA_LABEL = "no_data — no claims on record for this hex"


@dataclass
class RiskEstimate:
    hex_id: str
    hour: int
    risk_score: float          # 0..1 display score
    label: str                 # honesty caveat, or the real model's own label
    source: str                # "model" | "claims_fallback" | "no_data"
    top_factors: Optional[dict] = None
    model_version: Optional[str] = None


def estimate_hex_risk(hex_id: str, hour: int, db: Session) -> RiskEstimate:
    """Real forecast if it exists; otherwise an honestly-labelled claims fallback."""
    if not (0 <= hour < 24):
        raise ValueError("hour must be in [0, 24)")

    # Tier 1: a real forecast row, if Ndu's pipeline has written one.
    cell = (
        db.query(RiskCell)
        .filter(RiskCell.hex_id == hex_id, RiskCell.hour == hour)
        .order_by(RiskCell.generated_at.desc())
        .first()
    )
    if cell is not None:
        return RiskEstimate(
            hex_id=hex_id,
            hour=hour,
            risk_score=cell.risk_score,
            label=f"model:{cell.model_version}",
            source="model",
            top_factors=cell.top_factors,
            model_version=cell.model_version,
        )

    # Tier 2/3: fall back to real claim counts in this hex.
    claims = db.query(Claim.hour, Claim.hour_known).filter(Claim.hex_id == hex_id).all()
    if not claims:
        return RiskEstimate(
            hex_id=hex_id, hour=hour, risk_score=0.0,
            label=NO_DATA_LABEL, source="no_data",
        )

    return _score_from_claims(hex_id, hour, claims)


def _score_from_claims(hex_id: str, hour: int, claims: list) -> RiskEstimate:
    """Tier 2 scoring shared by estimate_hex_risk and rank_hotspots's batched path."""
    same_hour = sum(1 for claim_hour, hour_known in claims if hour_known and claim_hour == hour)
    base = min(len(claims) / _SATURATION_CLAIM_COUNT, 1.0)
    boost = _PEAK_HOUR_BOOST if hour in _PEAK_HOURS else 1.0
    hour_weight = 1.0 + (same_hour / len(claims))
    risk_score = min(base * boost * hour_weight / 2.0, 0.99)  # /2.0 keeps boosts from saturating trivially

    return RiskEstimate(
        hex_id=hex_id, hour=hour, risk_score=round(risk_score, 3),
        label=FALLBACK_LABEL, source="claims_fallback",
        top_factors={"claim_count": len(claims), "same_hour_claims": same_hour},
    )


def rank_hotspots(hour: int, db: Session, limit: int = 20) -> list[RiskEstimate]:
    """
    Rank every hex with at least one recorded claim by the same tiering logic
    as estimate_hex_risk, for the given hour. Batches the DB access (one query
    for tier-1 RiskCell rows, one for tier-2/3 claim rows, both filtered to
    the known hex_ids) instead of issuing one query pair per hex — with ~700+
    distinct hexes, the naive per-hex version took ~60s per request.
    """
    if not (0 <= hour < 24):
        raise ValueError("hour must be in [0, 24)")

    hex_ids = {
        row[0] for row in db.query(Claim.hex_id).filter(Claim.hex_id.isnot(None)).distinct().all()
    }
    hex_ids |= {
        row[0] for row in db.query(RiskCell.hex_id).filter(RiskCell.hour == hour).distinct().all()
    }
    if not hex_ids:
        return []

    # Tier 1: latest RiskCell row per hex, for this hour, in one query.
    cells = (
        db.query(RiskCell)
        .filter(RiskCell.hex_id.in_(hex_ids), RiskCell.hour == hour)
        .order_by(RiskCell.generated_at.desc())
        .all()
    )
    cell_by_hex: dict[str, RiskCell] = {}
    for cell in cells:
        cell_by_hex.setdefault(cell.hex_id, cell)  # first seen = latest, since ordered desc

    # Tier 2/3: every claim for the remaining hexes, in one query.
    remaining = hex_ids - cell_by_hex.keys()
    claims_by_hex: dict[str, list] = {}
    if remaining:
        rows = (
            db.query(Claim.hex_id, Claim.hour, Claim.hour_known)
            .filter(Claim.hex_id.in_(remaining))
            .all()
        )
        for hex_id, claim_hour, hour_known in rows:
            claims_by_hex.setdefault(hex_id, []).append((claim_hour, hour_known))

    estimates: list[RiskEstimate] = []
    for hex_id in hex_ids:
        cell = cell_by_hex.get(hex_id)
        if cell is not None:
            estimates.append(RiskEstimate(
                hex_id=hex_id, hour=hour, risk_score=cell.risk_score,
                label=f"model:{cell.model_version}", source="model",
                top_factors=cell.top_factors, model_version=cell.model_version,
            ))
            continue

        claims = claims_by_hex.get(hex_id)
        if not claims:
            estimates.append(RiskEstimate(
                hex_id=hex_id, hour=hour, risk_score=0.0,
                label=NO_DATA_LABEL, source="no_data",
            ))
            continue

        estimates.append(_score_from_claims(hex_id, hour, claims))

    estimates.sort(key=lambda e: e.risk_score, reverse=True)
    return estimates[:limit]
