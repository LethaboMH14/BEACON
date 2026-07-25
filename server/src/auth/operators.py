"""
Operator token check (team/SBU.md backlog, 2026-07-25).

Previously `operator_id` in POST /v1/entities/{id}/verify was free text
from the request body, written verbatim into the hash-chained
evidence_chain (WHO verified WHAT WHEN) with no check the caller actually
was that operator. The pitch's ethics story rests on that field being
trustworthy — this makes it true rather than assumed, without needing
full OAuth for a hackathon: a static roster in OPERATOR_TOKENS (.env,
never committed), a required X-Operator-Token header, reject on mismatch.
"""
import json
import os

from fastapi import HTTPException, status


def _load_roster() -> dict[str, str]:
    """OPERATOR_TOKENS env var: JSON object {operator_id: token}."""
    raw = os.getenv("OPERATOR_TOKENS", "")
    if not raw:
        return {}
    try:
        roster = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return roster if isinstance(roster, dict) else {}


def require_operator_token(operator_id: str, x_operator_token: str | None) -> None:
    """
    Raise 401 unless x_operator_token matches the roster entry for operator_id.
    Plain function, not a FastAPI dependency — operator_id comes from the
    request body, so the route handler reads the X-Operator-Token header
    itself and calls this once both values are in hand.
    """
    roster = _load_roster()
    if not roster:
        # No roster configured — fail closed, not open. An unconfigured
        # roster must not silently accept every operator_id as valid.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="OPERATOR_TOKENS not configured on the server — no operator can be verified",
        )
    expected = roster.get(operator_id)
    if not expected or not x_operator_token or x_operator_token != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or missing X-Operator-Token for operator_id={operator_id}",
        )
