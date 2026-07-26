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

    try:
        return classify(waveform)
    except ClassifierUnavailable as exc:
        # 503 rather than 500: the request was fine, this host just cannot serve
        # it, and the client's documented fallback is to stay on the gate alone.
        logger.warning("audio classify unavailable: %s", exc)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
