"""
Evidence chain integrity verifier.

Walks every row of evidence_chain in insertion order and re-computes each
event_hash from (action, actor_id, target_type, target_id, details, ts,
prev_hash) — the same inputs used when the row was written.

Returns an IntegrityResult so callers can decide what to do:
  - is_intact=True  → chain is unbroken, safe to export
  - is_intact=False → first broken link identified; do not export

Exposed as GET /v1/evidence/integrity (ops only — added in G1 router below).
Used internally before any court-ready evidence export.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from .models import EvidenceChain


@dataclass
class IntegrityResult:
    is_intact: bool
    total_events: int
    broken_at_id: Optional[int]    # pk of first bad row, or None
    broken_at_seq: Optional[int]   # 1-based sequence number, or None
    detail: Optional[str]


def _recompute_hash(row: EvidenceChain) -> str:
    """Re-derive the event_hash from the stored row fields."""
    event_data = {
        "action":      row.action,
        "actor_id":    row.actor_id,
        "target_type": row.target_type,
        "target_id":   row.target_id,
        "details":     row.details,
        "ts":          row.ts.isoformat(),
        "prev_hash":   row.prev_hash,
    }
    return hashlib.sha256(
        json.dumps(event_data, sort_keys=True).encode()
    ).hexdigest()


def verify_chain(db: Session) -> IntegrityResult:
    """
    Walk the full evidence_chain in insertion order (ascending id) and verify:
      1. Each row's event_hash matches a fresh recomputation of its fields.
      2. Each row's prev_hash equals the event_hash of the preceding row
         (except the first row, whose prev_hash must be None).

    Returns as soon as the first broken link is found.
    """
    rows: list[EvidenceChain] = (
        db.query(EvidenceChain)
        .order_by(EvidenceChain.id.asc())
        .all()
    )

    if not rows:
        return IntegrityResult(
            is_intact=True,
            total_events=0,
            broken_at_id=None,
            broken_at_seq=None,
            detail=None,
        )

    prev_hash: Optional[str] = None

    for seq, row in enumerate(rows, start=1):
        # Check 1: stored hash matches recomputed hash
        expected_hash = _recompute_hash(row)
        if row.event_hash != expected_hash:
            return IntegrityResult(
                is_intact=False,
                total_events=len(rows),
                broken_at_id=row.id,
                broken_at_seq=seq,
                detail=(
                    f"Row id={row.id} event_hash mismatch: "
                    f"stored={row.event_hash[:12]}… "
                    f"expected={expected_hash[:12]}…"
                ),
            )

        # Check 2: prev_hash pointer is correct
        if row.prev_hash != prev_hash:
            return IntegrityResult(
                is_intact=False,
                total_events=len(rows),
                broken_at_id=row.id,
                broken_at_seq=seq,
                detail=(
                    f"Row id={row.id} prev_hash mismatch: "
                    f"stored={str(row.prev_hash)[:12]}… "
                    f"expected={str(prev_hash)[:12]}…"
                ),
            )

        prev_hash = row.event_hash

    return IntegrityResult(
        is_intact=True,
        total_events=len(rows),
        broken_at_id=None,
        broken_at_seq=None,
        detail=None,
    )
