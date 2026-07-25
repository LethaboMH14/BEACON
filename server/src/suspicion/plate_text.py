"""
Plate-text sanitisation — the gate between an OCR string and the entity store.

WHY THIS EXISTS (measured, not hypothetical). Running the plate service over a
1080p SA hijacking clip on 2026-07-25 returned, among 8 "plates":

    '```markdown\\n\\n```'   '1234567890'   '1000000000000'
    'CASE 2000'              'BUSINESS'     '1'   '6'   '0000'

Two failure modes, both real:
  1. The OCR stage in the workflow is LLM-backed and sometimes emits its own
     markdown fencing instead of a reading.
  2. It reads any text in frame — news chyrons, shopfronts — as a plate.

Without this gate every one of those became an Entity with a sighting_count,
a suspicion score, and eligibility to be matched as a returning vehicle. The
confusion-aware matcher would then happily merge '1' and '6' into one "car".
Garbage identity is worse than no identity: it produces confident-looking
repeat-offender claims about things that are not vehicles.

WHAT THIS CANNOT DO: it is a syntactic plausibility filter, not a verifier.
'CASE 2000' has the shape of a plate and passes. Nothing here can tell a real
plate from a plate-shaped piece of background text — only better OCR can. So
callers must keep treating plate_text as evidence to be verified, never as an
identification. See docs/06 honesty ledger.
"""
from __future__ import annotations

import re

# SA civilian plates run ~6-9 chars once separators are stripped
# (e.g. CA123456, ND123456, BX12CDGP). Bounds kept deliberately loose — the
# job here is rejecting the impossible, not enforcing a province format we'd
# then silently drop valid plates for.
MIN_LEN = 5
MAX_LEN = 10

# Markdown fencing the LLM OCR stage sometimes wraps its answer in.
_FENCE_RE = re.compile(r"```[a-zA-Z]*|```")
_ALLOWED_RE = re.compile(r"[^A-Z0-9]")


def normalize_plate_text(raw: str | None) -> str | None:
    """
    Strip to bare A-Z0-9, uppercased. Returns None when nothing usable remains.
    Separators (spaces, dashes, dots) are dropped rather than preserved so that
    'CA 123-456' and 'CA123456' resolve to the same entity.
    """
    if not raw or not isinstance(raw, str):
        return None
    cleaned = _ALLOWED_RE.sub("", _FENCE_RE.sub("", raw).upper())
    return cleaned or None


def is_plausible_plate(raw: str | None) -> bool:
    """
    True only for strings that could be a South African registration.

    Requires BOTH a letter and a digit. That single rule removes most of the
    observed junk ('1234567890', '1000000000000', '0000', '1', '6') and all
    pure-word chyron reads, because every SA civilian plate format mixes the
    two. A plate that is genuinely all-digits does not exist here.
    """
    normalized = normalize_plate_text(raw)
    if normalized is None:
        return False
    if not (MIN_LEN <= len(normalized) <= MAX_LEN):
        return False
    if not any(c.isalpha() for c in normalized):
        return False
    if not any(c.isdigit() for c in normalized):
        return False
    return True


def clean_plate_text(raw: str | None) -> str | None:
    """Normalized plate if plausible, else None. The one call sites should use."""
    return normalize_plate_text(raw) if is_plausible_plate(raw) else None
