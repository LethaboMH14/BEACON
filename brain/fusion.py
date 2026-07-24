"""
BEACON brain/ — Sighting Graph fusion + human gate (docs/01 §4, ADR-0002).

G2 scope: F1 (recurrence) only — the core rule ("3+ sightings, 2+ cameras,
14 days, not whitelisted = territory-scanning"). F2-F6 need inputs this repo
doesn't have yet (claims-peak-hour histogram, near-repeat kernel, per-camera
dwell baseline, road-network graph, weapon/audio events) and are listed as
TODO stubs so the escalation ladder and thresholds are provable now, and
plugging in a factor later is additive, not a rewrite.

Method: calibrated log-odds (VUKA fusion pattern, ported). Each factor
contributes a log-odds delta; total score = sum, converted to a probability
for display via the standard logistic. The MACHINE CEILING is watch_candidate
— no code path in this file can set state to "flagged". Only human_verify()
can, and it requires an operator_id (ADR-0002, human-gate architecture).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

RECURRENCE_MIN_SIGHTINGS = 3
RECURRENCE_MIN_CAMERAS = 2
RECURRENCE_WINDOW_DAYS = 14
F1_LOG_ODDS = 2.2  # calibrated placeholder — tuned on eval set at G3, docs/01 §4

MODAL_CORROBORATION_WINDOW_MINUTES = 10  # audio cue must be tightly co-located in time
F6_LOG_ODDS = {
    "gunshot": 3.0,       # independent channel, high weight — same rationale as docs/01 §4 F6
    "glass_break": 2.5,
    "scream": 2.5,
    "raised_voices": 1.0,  # weakest corroborator — could be innocuous, still independent evidence
}

WATCH_CANDIDATE_THRESHOLD = 2.0  # logistic(2.0) ~= 0.88

STATE_OBSERVED = "observed"
STATE_WATCH_CANDIDATE = "watch_candidate"
STATE_FLAGGED = "flagged"
STATE_DISMISSED = "dismissed"
STATE_WHITELISTED = "whitelisted"


@dataclass
class Entity:
    entity_id: str
    plate_text: str | None = None
    sightings: list[dict] = field(default_factory=list)
    state: str = STATE_OBSERVED
    score_log_odds: float = 0.0
    factors: list[str] = field(default_factory=list)  # which factor codes fired, e.g. ["F1"]

    @property
    def score(self) -> float:
        """Calibrated probability for display (docs, CLAUDE.md §4 principle 3: no invented precision)."""
        return 1.0 / (1.0 + math.exp(-self.score_log_odds))


def _parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def factor_f1_recurrence(entity: Entity, is_whitelisted: bool) -> bool:
    """docs/01 §4 F1: >=3 sightings, >=2 distinct cameras, within 14 days, not whitelisted."""
    if is_whitelisted:
        return False
    if len(entity.sightings) < RECURRENCE_MIN_SIGHTINGS:
        return False

    distinct_cameras = {s["camera_id"] for s in entity.sightings}
    if len(distinct_cameras) < RECURRENCE_MIN_CAMERAS:
        return False

    now = _parse_ts(entity.sightings[-1]["ts"])
    window_start = now - timedelta(days=RECURRENCE_WINDOW_DAYS)
    in_window = [s for s in entity.sightings if _parse_ts(s["ts"]) >= window_start]
    distinct_cameras_in_window = {s["camera_id"] for s in in_window}
    return len(in_window) >= RECURRENCE_MIN_SIGHTINGS and len(distinct_cameras_in_window) >= RECURRENCE_MIN_CAMERAS


def factor_f6_modal_corroboration(entity: Entity, audio_cues: list[dict]) -> str | None:
    """docs/01 §4 F6: an independent-channel audio event (gunshot/glass/scream)
    co-located in hex and tightly co-located in time with this entity's most
    recent sighting. Independent physical channel (mic, not camera) — this is
    corroboration, never a standalone trigger for this entity (CLAUDE.md-
    equivalent Principle 6: never stack correlated layers)."""
    if not entity.sightings or not audio_cues:
        return None

    latest = entity.sightings[-1]
    latest_ts = _parse_ts(latest["ts"])
    latest_hex = latest["hex"]
    window = timedelta(minutes=MODAL_CORROBORATION_WINDOW_MINUTES)

    best_label: str | None = None
    best_weight = 0.0
    for cue in audio_cues:
        if cue["hex"] != latest_hex:
            continue
        if abs(_parse_ts(cue["ts"]) - latest_ts) > window:
            continue
        weight = F6_LOG_ODDS.get(cue["label"], 0.0)
        if weight > best_weight:
            best_weight = weight
            best_label = cue["label"]
    return best_label


def recompute(entity: Entity, is_whitelisted: bool = False, audio_cues: list[dict] | None = None) -> Entity:
    """Recompute score + factors + machine-ceiling state after a new sighting.
    Never sets state to flagged/dismissed — those only come from human_verify()."""
    if entity.state in (STATE_FLAGGED, STATE_DISMISSED, STATE_WHITELISTED):
        return entity  # human decision stands; new sightings still logged, score frozen

    log_odds = 0.0
    factors: list[str] = []

    if factor_f1_recurrence(entity, is_whitelisted):
        log_odds += F1_LOG_ODDS
        factors.append("F1")

    audio_label = factor_f6_modal_corroboration(entity, audio_cues or [])
    if audio_label is not None:
        log_odds += F6_LOG_ODDS[audio_label]
        factors.append(f"F6:{audio_label}")

    # F2-F5: TODO — need claims-peak histogram / near-repeat kernel / dwell
    # baseline / road graph (docs/01 §4). Not built yet.

    entity.score_log_odds = log_odds
    entity.factors = factors

    if is_whitelisted:
        entity.state = STATE_WHITELISTED
    elif log_odds >= WATCH_CANDIDATE_THRESHOLD:
        entity.state = STATE_WATCH_CANDIDATE
    else:
        entity.state = STATE_OBSERVED

    return entity


def human_verify(entity: Entity, action: str, operator_id: str) -> Entity:
    """The only place state can become flagged/dismissed/whitelisted (ADR-0002 human gate)."""
    if not operator_id:
        raise ValueError("human_verify requires an operator_id — no anonymous escalation")
    if action == "flag":
        entity.state = STATE_FLAGGED
    elif action == "dismiss":
        entity.state = STATE_DISMISSED
    elif action == "whitelist":
        entity.state = STATE_WHITELISTED
    else:
        raise ValueError(f"unknown verify action: {action}")
    return entity
