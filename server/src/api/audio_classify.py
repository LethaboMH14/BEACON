"""
POST /v1/audio/classify — confirm (or reject) a browser audio gate with YAMNet.

WHY THE CLASSIFIER IS HERE AND NOT IN THE BROWSER
YAMNet is a 4 MB TFLite model. Running it client-side means shipping it plus a
WASM runtime into the bundle and paying that download on a phone, to do a job
the server already has the model and runtime for. And it is only ever needed on
demand: the browser's transient detector gates it, so this runs on the rare
window that looked like an impact, not continuously.

WHY AUDIO IS SENT AS BASE64 INT16 AND NOT A JSON FLOAT ARRAY
15,600 float32 samples serialise to roughly 200 KB of JSON text. The same window
as 16-bit PCM is 31 KB, ~42 KB base64. At the latency this sits in front of —
a person deciding whether their window just broke — that difference matters, and
16-bit is already beyond what the microphone resolves.

WHAT IS NOT STORED
The window is classified and dropped. It is never written to disk and never
attached to an incident; only the label and score leave this function.
"""
from __future__ import annotations

import base64
import logging

import numpy as np
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from ..audio import ClassifierUnavailable, classify

logger = logging.getLogger(__name__)

router = APIRouter()

#: One YAMNet window is 15,600 samples => 31,200 bytes => ~41,600 base64 chars.
#: The cap is generous enough for a slightly long window and small enough that
#: this endpoint cannot be used to post arbitrary payloads.
MAX_B64_CHARS = 120_000


class ClassifyRequest(BaseModel):
    """A single mono window, 16-bit PCM little-endian, base64-encoded."""

    pcm16: str = Field(..., description="base64 of int16 mono samples")
    sample_rate: int = Field(16_000, description="must be 16000 — YAMNet's rate")


class ClassifyResponse(BaseModel):
    verdict: str  # "glass_break" | "gunshot" | "other"
    glass_label: str
    glass_score: float
    competing_label: str
    competing_score: float
    clears_floor: bool
    beats_competing: bool
    # Gunshot fields present whenever the model is available (always alongside glass).
    gunshot_label: str = ""
    gunshot_score: float = 0.0
    gunshot_clears_floor: bool = False
    gunshot_beats_competing: bool = False
    top: list[dict]


@router.post("/audio/classify", response_model=ClassifyResponse)
def classify_audio(req: ClassifyRequest) -> dict:
    if req.sample_rate != 16_000:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"sample_rate must be 16000, got {req.sample_rate}; resample client-side",
        )
    if len(req.pcm16) > MAX_B64_CHARS:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="window too long")

    try:
        raw = base64.b64decode(req.pcm16, validate=True)
    except Exception as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"bad base64: {exc}")
    if len(raw) < 2 or len(raw) % 2:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="not int16 PCM")

    # int16 -> float32 in [-1, 1), which is the range YAMNet was trained on.
    waveform = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0

    samples = len(waveform)
    duration_ms = round(samples / 16_000 * 1000)
    print(f"\n🎙  AUDIO WINDOW RECEIVED  ({samples} samples / {duration_ms} ms)")
    print(f"    Running YAMNet classifier...")

    try:
        result = classify(waveform)
    except ClassifierUnavailable as exc:
        print(f"    ✗ Classifier unavailable: {exc}")
        logger.warning("audio classify unavailable: %s", exc)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))

    verdict = result["verdict"]
    top = result.get("top", [])[:3]
    top_str = "  |  ".join(f"{t['label']} {t['score']:.3f}" for t in top)

    if verdict == "glass_break":
        print(f"    ⚠  VERDICT: GLASS BREAK  (score {result['glass_score']:.3f})")
        print(f"    Top labels: {top_str}")
        print(f"    → ALARM TRIGGERED")
    elif verdict == "gunshot":
        print(f"    ⚠  VERDICT: GUNSHOT  (score {result['gunshot_score']:.3f})")
        print(f"    Top labels: {top_str}")
        print(f"    → ALARM TRIGGERED")
    else:
        print(f"    ✓ verdict: other  (glass {result['glass_score']:.3f} / "
              f"gunshot {result.get('gunshot_score', 0):.3f})")
        print(f"    Top labels: {top_str}")

    return result


class AudioAlertRequest(BaseModel):
    verdict: str          # "glass_break" | "gunshot"
    label: str            # e.g. "Glass" or "Gunshot, gunfire"
    score: float
    property_address: str = "14 Ballyclare Drive, Bryanston"


class AudioAlertResponse(BaseModel):
    ok: bool
    provider: str
    to: list[str]
    detail: str


@router.post("/audio/alert", response_model=AudioAlertResponse)
async def send_audio_alert(req: AudioAlertRequest) -> AudioAlertResponse:
    """
    Called by the Home Guard client the moment the classifier confirms an alarm.
    Sends an immediate notification email — no human review required, because
    this is a sensor notification, not a dispatch order.
    """
    from ..notify.email import NotConfigured, send_audio_alert as _send

    kind = "GLASS BREAK" if req.verdict == "glass_break" else "GUNSHOT"
    print(f"\n📧  ALERT EMAIL  — {kind} at {req.property_address}")
    print(f"    Label: {req.label}  |  Score: {req.score:.3f}")

    try:
        res = await _send(
            verdict=req.verdict,
            label=req.label,
            score=req.score,
            property_address=req.property_address,
        )
        if res.ok:
            print(f"    ✓ Email sent via {res.provider} → {', '.join(res.to)}")
        else:
            print(f"    ✗ Email failed: {res.detail}")
        return AudioAlertResponse(ok=res.ok, provider=res.provider, to=res.to, detail=res.detail)
    except NotConfigured as exc:
        print(f"    ✗ Email not configured: {exc}")
        return AudioAlertResponse(ok=False, provider="unconfigured", to=[], detail=str(exc))
