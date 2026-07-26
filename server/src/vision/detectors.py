"""
Detector backends — one interface, three implementations, chosen at runtime.

WHY THIS REPLACES CALLING THE WORKFLOW SERVICES
The existing vision/backend (:8001) and vision/weapen_backend (:8002) each call
a Roboflow *workflow*. Those workflows run the detection model AND two
visualization steps (bounding_box_visualization, label_visualization) which
render an annotated JPEG server-side and ship it back as base64 — which this
codebase throws away, because every surface draws its own boxes from the
coordinates. We were paying for and waiting on rendering we discard.

MEASURED, on the hijack clip frame at t=15s (960px, same weapon detected):
    workflow via :8002          ~3.7-7.0 s
    direct to model, hosted     ~1.05 s      <- 3.5x, free, no install
    plate + weapon in parallel  ~1.1 s total (they no longer queue)
Local inference targets ~0.1-0.3 s and works with no network at all, which
matters for a product whose whole claim is working when infrastructure doesn't.

The backends are interchangeable because the pipeline only ever sees
Detection objects. Swapping HOSTED for LOCAL changes latency, not behaviour,
and the job record says which one ran so a demo can never silently claim local
speed while calling the cloud.
"""
from __future__ import annotations

import asyncio
import base64
import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Protocol

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# The underlying models the workflows wrap. Read off the workflow specs via the
# Roboflow API rather than guessed — see docs/BUILD-LOG.md.
WEAPON_MODEL_ID = "weapons-detection-xvtjj/1"
PLATE_MODEL_ID = "license-plate-recognition-rxg4e/11"
FACE_MODEL_ID = "face-detection-mik1i/18"

HOSTED_DETECT_URL = "https://detect.roboflow.com"

# Frames are downscaled before inference. Measured: 1920px and 640px return the
# same weapon detection, and 640px is ~25% faster. Long edge 960 is the
# compromise — small plates survive it, and it halves the upload.
INFERENCE_LONG_EDGE = 960

# Roboflow's own default is 0.4; we keep predictions above this and let the
# decision layer decide what a confidence *means*. Filtering hard here would
# hide the model's uncertainty from the thing whose job is to weigh it.
MIN_CONFIDENCE = 0.30


class Backend(str, Enum):
    LOCAL = "local"      # inference package, weights cached on this machine
    HOSTED = "hosted"    # detect.roboflow.com, model directly (no workflow)
    WORKFLOW = "workflow"  # legacy :8001/:8002 services — slow, kept for fallback


@dataclass(frozen=True)
class Detection:
    kind: str                 # "weapon" | "plate" | "face"
    label: str                # model class, e.g. "pistol"
    confidence: float
    # Pixel bbox in the ORIGINAL frame's coordinate space, not the downscaled
    # one — every consumer works in source coordinates, so rescaling belongs
    # here, once, rather than in each caller.
    bbox: dict
    ocr_text: Optional[str] = None


@dataclass
class DetectorRun:
    detections: list[Detection] = field(default_factory=list)
    backend: Backend = Backend.HOSTED
    elapsed_ms: float = 0.0
    errors: list[str] = field(default_factory=list)


class DetectorBackend(Protocol):
    name: Backend
    async def detect(self, frame_bgr: np.ndarray, model_id: str, kind: str) -> list[Detection]: ...


# ── shared helpers ──────────────────────────────────────────────────────────

def _downscale(frame_bgr: np.ndarray) -> tuple[np.ndarray, float]:
    """Returns (resized, scale) where scale maps resized coords -> original."""
    h, w = frame_bgr.shape[:2]
    long_edge = max(h, w)
    if long_edge <= INFERENCE_LONG_EDGE:
        return frame_bgr, 1.0
    f = INFERENCE_LONG_EDGE / long_edge
    return cv2.resize(frame_bgr, (int(w * f), int(h * f)), interpolation=cv2.INTER_AREA), 1 / f


def _to_detection(pred: dict, kind: str, scale: float) -> Optional[Detection]:
    """
    Roboflow object-detection predictions use x/y as the bbox CENTRE plus
    width/height. Treating x/y as the top-left corner is the classic way to get
    boxes that are visibly offset by half their size, so convert explicitly.
    """
    conf = float(pred.get("confidence", 0.0))
    if conf < MIN_CONFIDENCE:
        return None
    cx, cy = float(pred["x"]), float(pred["y"])
    w, h = float(pred["width"]), float(pred["height"])
    return Detection(
        kind=kind,
        label=str(pred.get("class") or pred.get("label") or kind),
        confidence=round(conf, 4),
        bbox={
            "x": round((cx - w / 2) * scale, 1),
            "y": round((cy - h / 2) * scale, 1),
            "w": round(w * scale, 1),
            "h": round(h * scale, 1),
        },
    )


# ── hosted: model directly, no workflow ─────────────────────────────────────

class HostedBackend:
    """detect.roboflow.com, straight at the model. ~1.05 s/frame measured."""
    name = Backend.HOSTED

    def __init__(self, api_key: Optional[str] = None):
        self._api_key = api_key or os.getenv("ROBOFLOW_API_KEY")
        if not self._api_key:
            raise RuntimeError(
                "ROBOFLOW_API_KEY not set. Add it to server/.env — never to the repo."
            )

    async def detect(self, frame_bgr, model_id: str, kind: str) -> list[Detection]:
        import httpx

        small, scale = _downscale(frame_bgr)
        ok, buf = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if not ok:
            raise RuntimeError("frame would not encode to JPEG")
        payload = base64.b64encode(buf.tobytes()).decode()

        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                f"{HOSTED_DETECT_URL}/{model_id}",
                params={"api_key": self._api_key},
                content=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        r.raise_for_status()
        preds = r.json().get("predictions", []) or []
        return [d for d in (_to_detection(p, kind, scale) for p in preds) if d]


# ── local: weights on this machine ──────────────────────────────────────────

class LocalBackend:
    """
    inference package, weights cached locally after first run.

    Models are loaded once and held: the load is the expensive part, and
    re-loading per frame would make local *slower* than hosted, which is the
    opposite of the point.
    """
    name = Backend.LOCAL

    def __init__(self, api_key: Optional[str] = None):
        self._api_key = api_key or os.getenv("ROBOFLOW_API_KEY")
        self._models: dict[str, object] = {}

    def _model(self, model_id: str):
        if model_id not in self._models:
            from inference import get_model
            self._models[model_id] = get_model(model_id=model_id, api_key=self._api_key)
        return self._models[model_id]

    async def detect(self, frame_bgr, model_id: str, kind: str) -> list[Detection]:
        small, scale = _downscale(frame_bgr)
        model = self._model(model_id)

        # Inference is CPU-bound and synchronous; run it off the event loop or
        # it blocks every other request on the server for its whole duration.
        def _run():
            return model.infer(small)[0]

        result = await asyncio.to_thread(_run)
        preds = [p.dict() if hasattr(p, "dict") else dict(p) for p in result.predictions]
        return [d for d in (_to_detection(p, kind, scale) for p in preds) if d]


# ── selection ───────────────────────────────────────────────────────────────

def available_backend(preferred: Optional[str] = None) -> Backend:
    """
    LOCAL if the package is importable, else HOSTED. Explicit `preferred` wins
    but is verified rather than trusted — asking for local on a machine without
    it should degrade loudly to hosted, not crash mid-demo.
    """
    want = (preferred or os.getenv("VISION_BACKEND") or "").lower()
    if want == "hosted":
        return Backend.HOSTED
    try:
        import inference  # noqa: F401
        return Backend.LOCAL
    except ImportError:
        if want == "local":
            logger.warning("VISION_BACKEND=local but `inference` is not installed — using hosted")
        return Backend.HOSTED


def make_backend(which: Optional[Backend] = None) -> DetectorBackend:
    which = which or available_backend()
    return LocalBackend() if which is Backend.LOCAL else HostedBackend()


async def detect_all(frame_bgr: np.ndarray, backend: Optional[DetectorBackend] = None) -> DetectorRun:
    """
    Run every detector on one frame CONCURRENTLY.

    The old pipeline ran plate then weapon in sequence, so a frame cost the sum
    of both. They are independent models with no shared state, so the frame
    should cost the slower of the two, not the total.

    One detector failing must not lose the other's result — a weapon detection
    is not worth discarding because the plate service 500'd, which is exactly
    what happened during an earlier demo run.
    """
    backend = backend or make_backend()
    t0 = time.perf_counter()

    jobs = [("weapon", WEAPON_MODEL_ID), ("plate", PLATE_MODEL_ID), ("face", FACE_MODEL_ID)]
    results = await asyncio.gather(
        *(backend.detect(frame_bgr, mid, kind) for kind, mid in jobs),
        return_exceptions=True,
    )

    out, errors = [], []
    for (kind, _), res in zip(jobs, results):
        if isinstance(res, BaseException):
            errors.append(f"{kind}: {type(res).__name__}: {res}")
            logger.warning("detector %s failed: %s", kind, res)
        else:
            out.extend(res)

    return DetectorRun(
        detections=out,
        backend=backend.name,
        elapsed_ms=round((time.perf_counter() - t0) * 1000, 1),
        errors=errors,
    )
