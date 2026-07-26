"""
Detection -> decision. The spine that was missing.

THE GAP THIS CLOSES
Before this module, the vision pipeline detected things and then stopped. A
pistol at 53% confidence produced a red box on a screen and nothing else: no
level, no recommendation, no route to a human. A demo can survive that; a
product cannot. This module turns a stream of per-frame detections into one
evolving situation with a level, a reason a person can read, and exactly one
recommended next action.

THE HONESTY RULE, CARRIED OVER FROM THE SUSPICION SCORER
suspicion/scorer.py can reach "candidate" and no further; only a human verify
call reaches "flagged" (ADR-0002). The same ceiling applies here, for the same
reason. The machine's job ends at NOTICE and CANDIDATE. ESCALATED is reachable
only through `escalate()`, which requires a human actor id. There is no
confidence value, no number of corroborating frames, and no combination of
detections that lets this module escalate on its own. If that ever becomes
tempting, the honest fix is to lower the candidate threshold so a human sees it
sooner — not to let the machine decide.

WHY PERSISTENCE, NOT JUST CONFIDENCE
A single frame showing a pistol at 53% is, in practice, about as likely to be a
phone, a wing mirror or a shadow as a weapon. The same detection holding across
several sampled frames is a different claim: uncorrelated false positives do not
usually persist in the same place. So the level is driven by (confidence x
persistence), and a one-frame hit — however confident — is capped below the
candidate line. This is the single most important guard against the demo failure
mode where a stray frame fires an alert at a security company.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Iterable, Optional

from .detectors import Detection


class Level(IntEnum):
    """Ordered so comparisons read naturally; values are stable for the API."""
    QUIET = 0        # nothing above threshold
    NOTICE = 1       # something seen, not yet worth interrupting a person
    CANDIDATE = 2    # machine ceiling — a human should look now
    ESCALATED = 3    # human-only. Never set by this module's scoring.


LEVEL_LABEL = {
    Level.QUIET: "Clear",
    Level.NOTICE: "Something seen",
    Level.CANDIDATE: "Needs a human look",
    Level.ESCALATED: "Escalated by a person",
}

# A weapon is the only detection that can reach the candidate line on its own —
# a plate or a face in view of a camera is ordinary life, not an event.
WEAPON_CANDIDATE_CONFIDENCE = 0.45
WEAPON_NOTICE_CONFIDENCE = 0.30

# Frames (of the sampled track, ~1/sec) a weapon must appear in before it can
# pass NOTICE. Two is deliberately low: at ~1 fps sampling, demanding four
# frames means a 3-second sighting is invisible, and that is a real hijacking.
WEAPON_PERSISTENCE_FRAMES = 2

# Above this, one frame is enough to reach candidate. The model rarely produces
# this on noise, and refusing to act on a 90% weapon because it only appeared
# once would be the wrong kind of caution.
WEAPON_SINGLE_FRAME_CONFIDENCE = 0.80


@dataclass
class Evidence:
    """One reason the situation is at the level it is. Written for a human."""
    code: str
    text: str
    weight_note: str = ""


@dataclass
class Situation:
    """
    The running state of one camera feed or one uploaded clip.

    Deliberately mutable and long-lived: a clip is not a sequence of independent
    frames, and treating it as one is how you end up alerting four times about
    the same pistol.
    """
    source_id: str
    level: Level = Level.QUIET
    level_reason: str = "Nothing detected yet."
    evidence: list[Evidence] = field(default_factory=list)

    # per-kind running tallies across the whole feed
    frames_seen: int = 0
    weapon_frames: int = 0
    weapon_peak_confidence: float = 0.0
    weapon_labels: dict[str, int] = field(default_factory=dict)
    plate_frames: int = 0
    plates_read: list[str] = field(default_factory=list)
    face_frames: int = 0

    first_weapon_at_s: Optional[float] = None
    escalated_by: Optional[str] = None
    escalated_at: Optional[float] = None

    @property
    def machine_ceiling_reached(self) -> bool:
        return self.level >= Level.CANDIDATE

    def recommendation(self) -> str:
        """The ONE action offered. A screen full of options is not a decision."""
        if self.level is Level.ESCALATED:
            return "Escalated — armed response notified."
        if self.level is Level.CANDIDATE:
            return "Review the clip and escalate to armed response if you agree."
        if self.level is Level.NOTICE:
            return "No action needed. Logged for context."
        return "No action needed."

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "level": int(self.level),
            "level_name": self.level.name.lower(),
            "level_label": LEVEL_LABEL[self.level],
            "reason": self.level_reason,
            "recommendation": self.recommendation(),
            "machine_ceiling_reached": self.machine_ceiling_reached,
            "evidence": [{"code": e.code, "text": e.text, "note": e.weight_note} for e in self.evidence],
            "counts": {
                "frames": self.frames_seen,
                "weapon_frames": self.weapon_frames,
                "weapon_peak_confidence": round(self.weapon_peak_confidence, 3),
                "weapon_labels": dict(self.weapon_labels),
                "plate_frames": self.plate_frames,
                "plates_read": list(self.plates_read),
                "face_frames": self.face_frames,
            },
            "first_weapon_at_s": self.first_weapon_at_s,
            "escalated_by": self.escalated_by,
            "escalated_at": self.escalated_at,
        }


def observe(situation: Situation, detections: Iterable[Detection], t_seconds: float) -> Situation:
    """
    Fold one frame's detections into the situation and re-derive the level.

    Re-derives rather than increments so the level is always a pure function of
    everything seen so far — a level that depends on the order frames arrived in
    is impossible to explain to the person being asked to act on it.
    """
    situation.frames_seen += 1

    for d in detections:
        if d.kind == "weapon":
            situation.weapon_frames += 1
            situation.weapon_labels[d.label] = situation.weapon_labels.get(d.label, 0) + 1
            situation.weapon_peak_confidence = max(situation.weapon_peak_confidence, d.confidence)
            if situation.first_weapon_at_s is None:
                situation.first_weapon_at_s = round(t_seconds, 2)
        elif d.kind == "plate":
            situation.plate_frames += 1
            # "Seen" and "read" are different claims (ADR-0006/0007). Only text
            # the OCR actually returned counts as read.
            if d.ocr_text and d.ocr_text not in situation.plates_read:
                situation.plates_read.append(d.ocr_text)
        elif d.kind == "face":
            situation.face_frames += 1

    _derive_level(situation)
    return situation


def _derive_level(s: Situation) -> None:
    """Level + the human-readable reason, from the running tallies."""
    # A human-set escalation is never walked back by the machine. Losing sight
    # of the weapon does not mean the emergency ended.
    if s.level is Level.ESCALATED:
        return

    evidence: list[Evidence] = []
    level = Level.QUIET
    reason = "Nothing above the detection threshold."

    conf = s.weapon_peak_confidence
    if s.weapon_frames:
        label = max(s.weapon_labels, key=lambda k: s.weapon_labels[k]) if s.weapon_labels else "weapon"
        pct = int(round(conf * 100))
        evidence.append(Evidence(
            code="weapon_seen",
            text=f"Possible {label} in {s.weapon_frames} of {s.frames_seen} frames, peak {pct}% confidence.",
            weight_note="Weapon detection is the only signal that can raise this on its own.",
        ))

        persistent = s.weapon_frames >= WEAPON_PERSISTENCE_FRAMES
        very_confident = conf >= WEAPON_SINGLE_FRAME_CONFIDENCE

        if (persistent and conf >= WEAPON_CANDIDATE_CONFIDENCE) or very_confident:
            level = Level.CANDIDATE
            if very_confident and not persistent:
                reason = (f"A {label} was detected at {pct}% confidence — high enough to act on "
                          f"from a single frame.")
            else:
                reason = (f"A {label} held across {s.weapon_frames} frames at up to {pct}% "
                          f"confidence. Repeated detections in the same place are much less "
                          f"likely to be a false positive than one frame.")
        elif conf >= WEAPON_NOTICE_CONFIDENCE:
            level = Level.NOTICE
            if not persistent:
                reason = (f"A possible {label} appeared in a single frame at {pct}% confidence. "
                          f"One frame is not enough to call it — logged, not raised.")
                evidence.append(Evidence(
                    code="single_frame",
                    text="Seen in one frame only.",
                    weight_note=f"Held below the review line: needs {WEAPON_PERSISTENCE_FRAMES} frames "
                                f"or {int(WEAPON_SINGLE_FRAME_CONFIDENCE * 100)}% confidence.",
                ))
            else:
                reason = (f"A possible {label} at {pct}% confidence — below the {int(WEAPON_CANDIDATE_CONFIDENCE * 100)}% "
                          f"line where we ask a person to look.")

    # Plates and faces never raise the level. They are context that makes a
    # weapon sighting actionable — who to look for — not evidence of a crime.
    if s.plate_frames:
        read = f", {len(s.plates_read)} read" if s.plates_read else ", none read"
        evidence.append(Evidence(
            code="plates",
            text=f"{s.plate_frames} plate sightings{read}.",
            weight_note="Context only — a plate in view never raises the level. A read is a lead, "
                        "never an identification.",
        ))
        if level is Level.QUIET:
            level = Level.NOTICE
            reason = "Vehicles seen. Nothing that needs a person."

    if s.face_frames:
        evidence.append(Evidence(
            code="faces",
            text=f"{s.face_frames} face sightings.",
            weight_note="Context only — never raises the level on its own.",
        ))
        if level is Level.QUIET:
            level = Level.NOTICE
            reason = "People seen. Nothing that needs a person."

    s.level = level
    s.level_reason = reason
    s.evidence = evidence


def escalate(situation: Situation, actor: str, note: str = "") -> Situation:
    """
    The only path to ESCALATED. Requires a named human.

    Refusing to escalate from QUIET is not pedantry: the button that sends armed
    response should not be live on a feed showing nothing, or the first real
    alert arrives at a company that has learned to ignore us.
    """
    if not actor:
        raise ValueError("escalate() requires the id of the person doing it — "
                         "an escalation with no one's name on it is not a human decision.")
    if situation.level < Level.CANDIDATE:
        raise ValueError(
            f"Nothing to escalate: {situation.source_id} is at {situation.level.name}, "
            f"below CANDIDATE."
        )
    situation.level = Level.ESCALATED
    situation.escalated_by = actor
    situation.escalated_at = time.time()
    situation.level_reason = (
        f"{actor} reviewed the footage and escalated it." + (f" Note: {note}" if note else "")
    )
    situation.evidence.append(Evidence(
        code="human_escalation",
        text=f"Escalated by {actor}.",
        weight_note="A person made this call, not the model.",
    ))
    return situation
