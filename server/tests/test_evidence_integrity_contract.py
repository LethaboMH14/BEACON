"""
Contract tests for evidence chain integrity.
VUKA style: validate hash chain is unbroken; tampering is detected.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from datetime import datetime
import hashlib
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import asyncio

from src.db.models import Base, EvidenceChain
from src.db.evidence_integrity import verify_chain
from src.api.entities import _write_evidence


@pytest.fixture
def db_session():
    """In-memory DB for integrity tests."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _hash_event(action, actor_id, target_type, target_id, details, ts, prev_hash):
    """Recreate the hash used when writing evidence."""
    data = {
        "action": action,
        "actor_id": actor_id,
        "target_type": target_type,
        "target_id": target_id,
        "details": details,
        "ts": ts.isoformat(),
        "prev_hash": prev_hash,
    }
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def test_empty_chain_is_intact(db_session):
    """Empty evidence chain should report is_intact=True."""
    result = verify_chain(db_session)
    assert result.is_intact is True
    assert result.total_events == 0


def test_single_event_chain_intact(db_session):
    """Single evidence entry (prev_hash=None) should be intact."""
    ts = datetime.utcnow()
    h = _hash_event("verify_flag", "op_001", "entity", "ent_001", {"note": "ok"}, ts, None)

    ev = EvidenceChain(
        action="verify_flag",
        actor_id="op_001",
        target_type="entity",
        target_id="ent_001",
        details={"note": "ok"},
        ts=ts,
        prev_hash=None,
        event_hash=h,
    )
    db_session.add(ev)
    db_session.commit()

    result = verify_chain(db_session)
    assert result.is_intact is True
    assert result.total_events == 1


def test_multi_event_chain_intact(db_session):
    """Chain of 3 events with correct prev_hash linkage is intact."""
    events = [
        ("verify_flag", "op_001", "entity", "ent_001"),
        ("alert_created", "system", "alert", "alrt_001"),
        ("alert_acked", "op_002", "alert", "alrt_001"),
    ]

    prev = None
    for i, (action, actor, ttype, tid) in enumerate(events):
        ts = datetime.utcnow()
        h = _hash_event(action, actor, ttype, tid, {}, ts, prev)
        ev = EvidenceChain(
            action=action,
            actor_id=actor,
            target_type=ttype,
            target_id=tid,
            details={},
            ts=ts,
            prev_hash=prev,
            event_hash=h,
        )
        db_session.add(ev)
        db_session.commit()
        prev = h

    result = verify_chain(db_session)
    assert result.is_intact is True
    assert result.total_events == 3


def test_write_evidence_produces_a_row_that_actually_verifies(db_session):
    """
    Integration test through the REAL write path (`_write_evidence`), not a
    hand-built row with a hash computed the same way the writer *should* work.
    Every other test in this file constructs its own EvidenceChain rows with
    ts/event_hash kept consistent by hand — none of them would have caught a
    real bug in `_write_evidence` itself.

    This test caught exactly that: `_write_evidence` called datetime.utcnow()
    twice — once for the hash input, again for the stored `ts` column — so
    every real row it wrote failed verify_chain() on the very next read
    (confirmed live before the fix: is_intact=False on a single legitimate
    write). Fixed by computing ts once and reusing it for both. This is the
    "who verified what when" evidence for the ethics pitch — it must be
    intact by construction, not just in hand-crafted test fixtures.
    """
    asyncio.run(_write_evidence(
        db=db_session, action="verify_flag", actor_id="op_001",
        target_type="entity", target_id="ent_001", details={"note": "test"},
    ))
    db_session.commit()

    result = verify_chain(db_session)
    assert result.is_intact is True, result.detail
    assert result.total_events == 1

    # And a second write correctly chains off the first's real event_hash.
    asyncio.run(_write_evidence(
        db=db_session, action="verify_dismiss", actor_id="op_002",
        target_type="entity", target_id="ent_002", details=None,
    ))
    db_session.commit()

    result = verify_chain(db_session)
    assert result.is_intact is True, result.detail
    assert result.total_events == 2


def test_tampered_event_hash_detected(db_session):
    """
    If an event_hash is changed after writing, verify_chain detects the break.
    """
    ts = datetime.utcnow()
    h = _hash_event("verify_flag", "op_001", "entity", "ent_001", {}, ts, None)

    ev = EvidenceChain(
        action="verify_flag",
        actor_id="op_001",
        target_type="entity",
        target_id="ent_001",
        details={},
        ts=ts,
        prev_hash=None,
        event_hash=h,
    )
    db_session.add(ev)
    db_session.commit()

    # Tamper with the hash
    ev.event_hash = "tampered_hash_12345"
    db_session.commit()

    result = verify_chain(db_session)
    assert result.is_intact is False
    assert result.broken_at_id == ev.id
    assert "mismatch" in result.detail.lower()


def test_broken_prev_hash_link_detected(db_session):
    """
    If prev_hash doesn't match the previous event_hash, chain is broken.
    """
    ts1 = datetime.utcnow()
    h1 = _hash_event("verify_flag", "op_001", "entity", "ent_001", {}, ts1, None)
    ev1 = EvidenceChain(
        action="verify_flag",
        actor_id="op_001",
        target_type="entity",
        target_id="ent_001",
        details={},
        ts=ts1,
        prev_hash=None,
        event_hash=h1,
    )
    db_session.add(ev1)
    db_session.commit()

    ts2 = datetime.utcnow()
    # Intentionally wrong prev_hash
    h2 = _hash_event("alert_acked", "op_002", "alert", "alrt_001", {}, ts2, "WRONG_PREV")
    ev2 = EvidenceChain(
        action="alert_acked",
        actor_id="op_002",
        target_type="alert",
        target_id="alrt_001",
        details={},
        ts=ts2,
        prev_hash="WRONG_PREV",
        event_hash=h2,
    )
    db_session.add(ev2)
    db_session.commit()

    result = verify_chain(db_session)
    assert result.is_intact is False
    assert result.broken_at_id == ev2.id
    assert "prev_hash mismatch" in result.detail.lower()
