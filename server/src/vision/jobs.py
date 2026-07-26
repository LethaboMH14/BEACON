"""
Video -> frames -> CLAHE -> detectors -> decision, as a background job.

WHY A JOB AND NOT A REQUEST
Even at the fast path (~1.1 s/frame hosted, faster local), a 45-second clip
sampled at 1 fps is 45 inferences. Holding an HTTP request open for that is how
you get a proxy timeout at the worst possible moment in a demo. So the upload
returns a job id immediately and the results stream out over the existing ops
WebSocket as they happen — which is also the honest shape of the product: a real
camera feed never "finishes", it just keeps telling you things.

PROGRESSIVE, NOT BATCH
Frames are emitted the moment they are decided, and the situation's level is
re-derived after every frame. The operator watches the level climb in step with
the footage instead of staring at a spinner and then being handed a verdict.
That is the difference between a system that shows its reasoning and one that
asks to be trusted.

SAMPLING
Default 1 fps. Enough to catch a weapon that is visible for two seconds, cheap
enough that a 45 s clip is ~45 inferences. Raising this multiplies cost linearly
and buys very little: consecutive frames 200 ms apart are near-duplicates and
their detections are correlated, so they do not corroborate each other the way
frames a second apart do.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

import cv2

from .decision import Level, Situation, observe
from .detectors import DetectorBackend, detect_all, make_backend
from .preprocess import preprocess

logger = logging.getLogger(__name__)

DEFAULT_SAMPLE_FPS = 1.0

# A hard ceiling on frames per job. An hour of footage at 1 fps is 3600
# inferences; nobody means to do that by dragging a file onto a page.
MAX_FRAMES = 240

# Emitter signature: async fn(event_name, payload) -> None
Emitter = Callable[[str, dict], Awaitable[None]]


@dataclass
class VisionJob:
    id: str
    source_name: str
    status: str = "queued"        # queued | running | done | failed | cancelled
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    error: Optional[str] = None

    duration_s: float = 0.0
    fps: float = 0.0
    total_frames_planned: int = 0
    frames_done: int = 0

    situation: Optional[Situation] = None
    frames: list[dict] = field(default_factory=list)
    backend: Optional[str] = None
    clahe_frames: int = 0

    # Rolling mean of detector wall time, so the UI can state a measured
    # per-frame cost instead of a marketing number.
    _elapsed_total_ms: float = 0.0

    @property
    def mean_frame_ms(self) -> Optional[float]:
        return round(self._elapsed_total_ms / self.frames_done, 1) if self.frames_done else None

    @property
    def progress(self) -> float:
        if not self.total_frames_planned:
            return 0.0
        return round(min(self.frames_done / self.total_frames_planned, 1.0), 3)

    def to_dict(self, include_frames: bool = True) -> dict[str, Any]:
        d: dict[str, Any] = {
            "job_id": self.id,
            "source_name": self.source_name,
            "status": self.status,
            "error": self.error,
            "progress": self.progress,
            "frames_done": self.frames_done,
            "frames_planned": self.total_frames_planned,
            "duration_s": round(self.duration_s, 2),
            "video_fps": round(self.fps, 2),
            "backend": self.backend,
            "clahe_frames": self.clahe_frames,
            "mean_frame_ms": self.mean_frame_ms,
            "elapsed_s": round((self.finished_at or time.time()) - (self.started_at or self.created_at), 2)
            if self.started_at else 0.0,
            "situation": self.situation.to_dict() if self.situation else None,
        }
        if include_frames:
            d["frames"] = self.frames
        return d


class JobStore:
    """
    In-process job registry.

    Deliberately in-memory: these are ephemeral analyses of a clip, not records
    of an incident. Anything that matters — an escalation, a sighting — is
    written to the database by the layer above. Restarting the server losing a
    half-finished analysis is the correct behaviour; restarting it losing an
    escalation would not be.
    """

    def __init__(self) -> None:
        self._jobs: dict[str, VisionJob] = {}
        self._tasks: dict[str, asyncio.Task] = {}

    def create(self, source_name: str) -> VisionJob:
        job = VisionJob(id=f"vj_{uuid.uuid4().hex[:12]}", source_name=source_name)
        self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Optional[VisionJob]:
        return self._jobs.get(job_id)

    def list(self, limit: int = 20) -> list[VisionJob]:
        return sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)[:limit]

    def track(self, job_id: str, task: asyncio.Task) -> None:
        self._tasks[job_id] = task

    def cancel(self, job_id: str) -> bool:
        task = self._tasks.get(job_id)
        if task and not task.done():
            task.cancel()
            return True
        return False


store = JobStore()


def probe(path: Path) -> tuple[float, float, int]:
    """(fps, duration_s, frame_count). Opened and closed so the file isn't held."""
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise ValueError(f"Could not open video: {path.name}")
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
        count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        # Some containers report a plausible fps and a nonsense frame count (or
        # vice versa). Guard both rather than trusting either.
        duration = count / fps if fps > 0 and count > 0 else 0.0
        return fps, duration, count
    finally:
        cap.release()


async def run_job(
    job: VisionJob,
    path: Path,
    *,
    emit: Optional[Emitter] = None,
    sample_fps: float = DEFAULT_SAMPLE_FPS,
    backend: Optional[DetectorBackend] = None,
    clahe: Optional[bool] = None,
) -> VisionJob:
    """
    Decode, preprocess, detect and decide, emitting as it goes.

    `clahe=None` lets the preprocessor decide per frame from the frame's own
    luminance, which is the production behaviour. True/False force it for the
    UI's before/after comparison.
    """
    job.status = "running"
    job.started_at = time.time()
    job.situation = Situation(source_id=job.source_name)
    backend = backend or make_backend()
    job.backend = backend.name.value if hasattr(backend.name, "value") else str(backend.name)

    async def _emit(event: str, payload: dict) -> None:
        if emit:
            try:
                await emit(event, payload)
            except Exception:
                # A dead WebSocket must never kill the analysis. The job's own
                # record is the source of truth; the stream is a convenience.
                logger.warning("vision emit failed for %s", event, exc_info=True)

    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        job.status, job.error = "failed", f"Could not open video: {path.name}"
        job.finished_at = time.time()
        await _emit("vision.failed", job.to_dict(include_frames=False))
        return job

    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        job.fps = fps
        job.duration_s = count / fps if fps > 0 and count > 0 else 0.0

        step = max(int(round(fps / sample_fps)), 1)
        planned = (count // step) if count > 0 else 0
        job.total_frames_planned = min(planned, MAX_FRAMES) if planned else MAX_FRAMES

        await _emit("vision.started", job.to_dict(include_frames=False))

        idx = 0
        while job.frames_done < MAX_FRAMES:
            ok, frame = cap.read()
            if not ok:
                break
            if idx % step:
                idx += 1
                continue
            idx += 1

            t_s = round((idx - 1) / fps, 2) if fps else float(job.frames_done)

            pre = preprocess(frame, force=clahe)
            if pre.applied:
                job.clahe_frames += 1

            run = await detect_all(pre.image, backend=backend)
            job._elapsed_total_ms += run.elapsed_ms
            job.frames_done += 1

            observe(job.situation, run.detections, t_s)

            record = {
                "t": t_s,
                "index": job.frames_done,
                "width": int(frame.shape[1]),
                "height": int(frame.shape[0]),
                "detections": [
                    {
                        "kind": d.kind, "label": d.label,
                        "confidence": d.confidence, "bbox": d.bbox,
                        "ocr_text": d.ocr_text,
                    }
                    for d in run.detections
                ],
                "clahe": {
                    "applied": pre.applied, "reason": pre.reason,
                    "luma_before": pre.mean_luma_before,
                    "luma_after": pre.mean_luma_after,
                    "gain": pre.luma_gain,
                    "ms": pre.elapsed_ms,
                },
                "detector_ms": run.elapsed_ms,
                "errors": run.errors,
            }
            job.frames.append(record)

            await _emit("vision.frame", {
                "job_id": job.id,
                "frame": record,
                "progress": job.progress,
                "situation": job.situation.to_dict(),
            })

            # Yield between frames so a long job can be cancelled and so the
            # event loop can actually flush the events we just queued.
            await asyncio.sleep(0)

        job.status = "done"

    except asyncio.CancelledError:
        job.status = "cancelled"
        job.finished_at = time.time()
        await _emit("vision.cancelled", job.to_dict(include_frames=False))
        raise
    except Exception as exc:
        logger.exception("vision job %s failed", job.id)
        job.status, job.error = "failed", f"{type(exc).__name__}: {exc}"
    finally:
        cap.release()
        job.finished_at = job.finished_at or time.time()

    await _emit(
        "vision.decision" if job.status == "done" else "vision.failed",
        job.to_dict(include_frames=False),
    )
    return job


def start(
    job: VisionJob,
    path: Path,
    **kwargs: Any,
) -> asyncio.Task:
    """Schedule run_job on the running loop and keep a handle for cancellation."""
    task = asyncio.create_task(run_job(job, path, **kwargs))
    store.track(job.id, task)
    return task
