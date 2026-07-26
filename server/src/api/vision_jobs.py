"""
Vision job API — upload a clip, watch it get analysed, decide what to do.

THE FLOW THIS EXPOSES
  POST /v1/vision/jobs              upload a clip -> job id, returns immediately
  GET  /v1/vision/jobs              recent jobs (the "repeat offenders" shelf)
  GET  /v1/vision/jobs/{id}         full result incl. every frame's boxes
  POST /v1/vision/jobs/{id}/escalate  a NAMED HUMAN escalates; optionally emails
  DELETE /v1/vision/jobs/{id}       cancel a running analysis
  GET  /v1/vision/backend           what engine is live and how fast it measured

Progress streams over the existing ops WebSocket as vision.started /
vision.frame / vision.decision, so the UI does not poll.

WHY UPLOAD RETURNS BEFORE THE WORK IS DONE
See jobs.py — a 45 s clip is ~45 inferences and holding the request open for
that invites a proxy timeout mid-demo. The 202 + stream shape is also the honest
one: a camera feed is a stream, not a request.

THE ESCALATE ENDPOINT IS THE POINT
Everything else here is plumbing. This is the endpoint where a machine
observation becomes a human decision with a name attached, and it is the only
route by which anything leaves BEACON for a security provider. It requires an
operator token for exactly the reason the verify endpoint does: without it,
anyone could put any operator's name on an escalation.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Header, UploadFile, status
from pydantic import BaseModel, Field

from ..vision import jobs as jobs_mod
from ..vision.decision import Level, escalate
from ..vision.detectors import available_backend
from ..ws.manager import ws_manager

router = APIRouter()

# Kept modest on purpose: a 200 MB upload on a demo network takes longer to
# transfer than the analysis takes to run, which makes the product look slow
# for a reason that has nothing to do with the product.
MAX_UPLOAD_BYTES = 60 * 1024 * 1024
ALLOWED_SUFFIXES = {".mp4", ".mov", ".avi", ".mkv", ".webm"}

# Uploads live in a temp dir, never in the repo. Several of the demo clips are
# copyrighted broadcast footage; a path that could end up committed is a
# licensing problem, not just an untidy one.
UPLOAD_DIR = Path(tempfile.gettempdir()) / "beacon_vision_uploads"
UPLOAD_DIR.mkdir(exist_ok=True)


def _operator_tokens() -> dict[str, str]:
    raw = os.getenv("OPERATOR_TOKENS")
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def _require_operator(operator_id: str, token: Optional[str]) -> None:
    """
    Same rule as POST /v1/entities/{id}/verify. When no roster is configured
    (local dev) the check is skipped — but the escalation still records who
    claimed to do it, so the record is never anonymous.
    """
    roster = _operator_tokens()
    if not roster:
        return
    if roster.get(operator_id) != token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            "Operator token missing or does not match this operator_id.")


async def _emit(event: str, payload: dict) -> None:
    await ws_manager.broadcast_to_ops({"event": event, "data": payload})


class JobCreated(BaseModel):
    job_id: str
    status: str
    backend: str
    sample_fps: float
    estimated_frames: int
    estimated_seconds: Optional[float] = Field(
        None, description="Rough wall time, from the backend's measured per-frame cost. "
                          "Null on the first run of a backend, when we have nothing to measure yet."
    )
    note: str


class EscalateRequest(BaseModel):
    operator_id: str = Field(..., min_length=1)
    note: str = ""
    location: str = "Unknown location"
    camera_label: Optional[str] = None
    send_email: bool = False
    email_to: Optional[list[str]] = None


class EscalateResponse(BaseModel):
    job_id: str
    situation: dict
    email: Optional[dict] = None


class MemberReportRequest(BaseModel):
    """
    The Cam tab's "Report to security" action. Distinct from EscalateRequest:
    that endpoint escalates a real jobs.py Situation and requires an operator
    token (the ops-console gate). This one is the member's own recorded-clip
    tab — there is no Situation because the clip was never run through
    jobs.py, only the offline detector script. The member tapping the button
    IS the named human decision; no operator token applies to their own report.
    """
    clip_label: str
    level: str
    title: str
    detail: str
    confidence: Optional[float] = None
    timestamp_s: Optional[float] = None


class MemberReportResponse(BaseModel):
    ok: bool
    provider: str
    to: list[str]
    detail: str


@router.post("/vision/report", response_model=MemberReportResponse)
async def report_from_member(body: MemberReportRequest) -> MemberReportResponse:
    from ..notify.email import NotConfigured, send_member_report

    subject = f"BEACON member report — {body.title} ({body.clip_label})"
    lines = [
        f"BEACON MEMBER REPORT — {body.title}",
        "",
        f"Clip: {body.clip_label}",
        f"Level: {body.level}",
        f"Detail: {body.detail}",
    ]
    if body.confidence is not None:
        lines.append(f"Model confidence: {round(body.confidence * 100)}%")
    if body.timestamp_s is not None:
        lines.append(f"Seen at: {body.timestamp_s:.0f}s into the clip")
    lines += [
        "",
        "This is a recorded clip (not a live camera) reviewed and reported by a "
        "member from the BEACON app. It is a machine detection, not a verified "
        "identification, and BEACON has no dispatch authority — this is a request "
        "for a person to look, not an automated alarm.",
    ]
    text = "\n".join(lines)

    try:
        res = await send_member_report(subject=subject, text=text)
    except NotConfigured as exc:
        return MemberReportResponse(ok=False, provider="unconfigured", to=[], detail=str(exc))

    return MemberReportResponse(ok=res.ok, provider=res.provider, to=res.to, detail=res.detail)


@router.get("/vision/backend")
def get_backend() -> dict:
    """What engine will run, so a demo can never claim local speed while
    silently calling the cloud."""
    b = available_backend()
    return {
        "backend": b.value,
        "local_available": b.value == "local",
        "note": (
            "Local: model weights on this machine, no network needed."
            if b.value == "local" else
            "Hosted: calls the model directly at detect.roboflow.com. Measured ~1.1s per "
            "frame with plate and weapon models running in parallel."
        ),
    }


@router.post("/vision/jobs", status_code=status.HTTP_202_ACCEPTED, response_model=JobCreated)
async def create_job(
    file: UploadFile = File(...),
    sample_fps: float = Form(jobs_mod.DEFAULT_SAMPLE_FPS),
    clahe: Optional[bool] = Form(None),
) -> JobCreated:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            f"{suffix or 'that file type'} is not a video we can decode. "
            f"Accepted: {', '.join(sorted(ALLOWED_SUFFIXES))}",
        )

    job = jobs_mod.store.create(source_name=file.filename or "upload")
    dest = UPLOAD_DIR / f"{job.id}{suffix}"

    # Streamed to disk with a running size check rather than read() into memory:
    # a 60 MB video held in RAM per concurrent upload is avoidable.
    written = 0
    with dest.open("wb") as out:
        while chunk := await file.read(1024 * 1024):
            written += len(chunk)
            if written > MAX_UPLOAD_BYTES:
                out.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(
                    status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    f"Clip is over {MAX_UPLOAD_BYTES // (1024 * 1024)} MB. Trim it — on a demo "
                    f"network the upload would take longer than the analysis.",
                )
            out.write(chunk)

    try:
        fps, duration, count = jobs_mod.probe(dest)
    except ValueError as exc:
        dest.unlink(missing_ok=True)
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))

    step = max(int(round(fps / sample_fps)), 1) if fps else 1
    estimated = min(count // step if count else 0, jobs_mod.MAX_FRAMES)

    backend = available_backend()
    jobs_mod.start(job, dest, emit=_emit, sample_fps=sample_fps, clahe=clahe)

    # Estimate from a previously completed job on this backend rather than a
    # hardcoded number — the honest estimate is the one we measured here.
    prior = [j.mean_frame_ms for j in jobs_mod.store.list(20)
             if j.backend == backend.value and j.mean_frame_ms]
    est_s = round(estimated * (sum(prior) / len(prior)) / 1000, 1) if prior else None

    return JobCreated(
        job_id=job.id,
        status=job.status,
        backend=backend.value,
        sample_fps=sample_fps,
        estimated_frames=estimated,
        estimated_seconds=est_s,
        note=f"Analysing {duration:.0f}s of footage at {sample_fps:g} frame/s. "
             f"Watch /ws/ops for vision.frame events.",
    )


@router.get("/vision/jobs")
def list_jobs(limit: int = 20) -> dict:
    return {"jobs": [j.to_dict(include_frames=False) for j in jobs_mod.store.list(limit)]}


@router.get("/vision/jobs/{job_id}")
def get_job(job_id: str, frames: bool = True) -> dict:
    job = jobs_mod.store.get(job_id)
    if not job:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No job {job_id}")
    return job.to_dict(include_frames=frames)


@router.delete("/vision/jobs/{job_id}")
def cancel_job(job_id: str) -> dict:
    job = jobs_mod.store.get(job_id)
    if not job:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No job {job_id}")
    cancelled = jobs_mod.store.cancel(job_id)
    return {"job_id": job_id, "cancelled": cancelled, "status": job.status}


@router.post("/vision/jobs/{job_id}/escalate", response_model=EscalateResponse)
async def escalate_job(
    job_id: str,
    body: EscalateRequest,
    x_operator_token: Optional[str] = Header(None),
) -> EscalateResponse:
    job = jobs_mod.store.get(job_id)
    if not job or not job.situation:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No job {job_id}")

    _require_operator(body.operator_id, x_operator_token)

    try:
        escalate(job.situation, actor=body.operator_id, note=body.note)
    except ValueError as exc:
        # 409, not 400: the request is well-formed, the situation just isn't in
        # a state where escalation means anything.
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))

    email_result = None
    if body.send_email:
        from ..notify.email import NotConfigured, send_escalation
        try:
            res = await send_escalation(
                job.situation,
                location=body.location,
                camera_label=body.camera_label or job.source_name,
                to=body.email_to,
            )
            email_result = {"ok": res.ok, "provider": res.provider, "to": res.to,
                            "detail": res.detail, "message_id": res.message_id}
        except NotConfigured as exc:
            # The escalation itself already happened and stands. A missing API
            # key must not roll back a human's decision — it just means the
            # handoff didn't leave the building, and the UI has to say so.
            email_result = {"ok": False, "provider": "unconfigured", "to": [], "detail": str(exc)}

    payload = {"job_id": job_id, "situation": job.situation.to_dict(), "email": email_result}
    await _emit("vision.escalated", payload)
    return EscalateResponse(**payload)
