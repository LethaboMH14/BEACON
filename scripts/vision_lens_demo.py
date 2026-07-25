"""
BEACON vision-lens analyzer.

Samples frames from a video, runs all three detection modalities over each
frame, and POSTs whatever is actually detected into the real server pipeline
(POST /v1/sightings, http://localhost:8000) so detections flow through the same
entity-resolution / suspicion-scoring / evidence path as everything else —
not a separate demo silo.

Three modalities, two of them remote and one local:
  - PLATES   — vision/backend        (Roboflow workflow, port 8001)
  - WEAPONS  — vision/weapen_backend (Roboflow workflow, port 8002)
  - FACES    — InsightFace buffalo_l, IN-PROCESS on CPU, no API key, no
               network. Deliberately not a fourth microservice: it is a local
               model with no credential to manage, and a demo that needs four
               servers up has four ways to fail on stage.

Routing (real, not simulated):
  - A weapon detection fires a critical alert to private security immediately.
    Hard signal, no entity resolution in the way — the same "deliberate trigger
    bypasses inference" principle the rest of the platform follows.
  - A plate or face resolves to an Entity server-side. A FIRST sighting is
    logged only. A REPEAT sighting (server returns an entity whose count has
    grown) is what routes onward, because "seen here before" is the signal —
    a single passer-by is not.

WHAT THE DETECTORS ACTUALLY DO, measured 2026-07-25 on a 1080p SA hijacking
clip (48s, 24 frames sampled at 2s):
  - weapons: 5 pistol detections, confidence 0.47-0.63. Real and useful.
  - faces:   2 detections, det_score 0.52 and 0.76. Real, but small in frame
             (16x22 and 32x42 px) — embeddings from faces that size are weak
             and should not be presented as reliable recognition.
  - plates:  8 detections but the OCR is unreliable — it returned
             '```markdown', '1234567890', 'BUSINESS' and 'CASE 2000' (reading
             the news chyron). The server sanitises these away
             (server/src/suspicion/plate_text.py); do not claim working plate
             recognition on footage like this.
Resolution is the binding constraint, not configuration: the same pipeline on
240p CCTV returned zero of everything, including after 4x upscaling.

Usage:
    python scripts/vision_lens_demo.py <video> [--camera-id cam_lens_demo]
                                              [--interval 2.0]
                                              [--out detections.json]
                                              [--no-faces] [--dry-run]

--out writes a per-timestamp detection track the lens UI replays in sync with
the video. --dry-run detects and writes that file without touching the server.

Prereqs:
    server:   uvicorn src.main:app --port 8000   (from server/)
    plates:   uvicorn app:app --port 8001        (from vision/backend/)
    weapons:  uvicorn app:app --port 8002        (from vision/weapen_backend/)
    faces:    pip install insightface onnxruntime  (model auto-downloads once)
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import cv2
import requests

SERVER_URL = "http://localhost:8000"
PLATE_SERVICE_URL = "http://localhost:8001/detect"
WEAPON_SERVICE_URL = "http://localhost:8002/detect"

REQUEST_TIMEOUT_S = 60

# InsightFace detector input size. Larger than the 640 default on purpose:
# subjects in CCTV are small in frame, and 640 misses faces that 1024 finds.
FACE_DET_SIZE = (1024, 1024)


def log(msg: str) -> None:
    print(f"[vision-lens] {msg}", flush=True)


# ---------------------------------------------------------------- frame source

def sample_frames(video_path: Path, interval_s: float):
    """Yield (frame_index, video_timestamp_s, frame_bgr) every interval_s."""
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    frame_step = max(1, int(round(fps * interval_s)))

    idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % frame_step == 0:
            yield idx, idx / fps, frame
        idx += 1
    cap.release()


# ------------------------------------------------------------------- detectors

def call_detector(url: str, frame_bgr, filename: str) -> Optional[dict[str, Any]]:
    """
    Returns the first item of the workflow's response list (confirmed live
    against both services on 2026-07-25): a dict shaped like
    {"output_image": <base64 jpeg>, "predictions": {"image": {...},
    "predictions": [...]}, ...service-specific extras}. Not a guess — this is
    the real shape both services returned on real video frames. The response is
    a LIST, not a dict; calling .get() on it directly raises.
    """
    ok, buf = cv2.imencode(".jpg", frame_bgr)
    if not ok:
        log(f"WARN: failed to encode frame for {filename}")
        return None
    files = {"file": (filename, buf.tobytes(), "image/jpeg")}
    try:
        resp = requests.post(url, files=files, timeout=REQUEST_TIMEOUT_S)
        resp.raise_for_status()
        body = resp.json()
        if isinstance(body, list) and body and isinstance(body[0], dict):
            return body[0]
        log(f"WARN: unexpected {url} response shape: {str(body)[:200]}")
        return None
    except requests.RequestException as e:
        log(f"WARN: {url} call failed: {e}")
        return None


def extract_predictions(result: Optional[dict[str, Any]]) -> list[dict[str, Any]]:
    """Real predictions live at result["predictions"]["predictions"]."""
    if not result:
        return []
    preds = result.get("predictions")
    if isinstance(preds, dict) and isinstance(preds.get("predictions"), list):
        return preds["predictions"]
    return []


def load_face_analyzer():
    """
    InsightFace on CPU (ctx_id=-1). Returns None if unavailable so the plate and
    weapon paths still run — a missing optional dependency shouldn't take the
    whole demo down mid-pitch.
    """
    try:
        import insightface
    except ImportError:
        log("WARN: insightface not installed — face detection disabled "
            "(pip install insightface onnxruntime)")
        return None
    try:
        analyzer = insightface.app.FaceAnalysis()
        analyzer.prepare(ctx_id=-1, det_size=FACE_DET_SIZE)
        log(f"Face analyzer ready (buffalo_l, CPU, det_size={FACE_DET_SIZE})")
        return analyzer
    except Exception as e:
        log(f"WARN: could not initialise InsightFace — face detection disabled: {e}")
        return None


def detect_faces(analyzer, frame_bgr) -> list[dict[str, Any]]:
    """[{bbox, confidence, embedding(512 floats)}] — [] if unavailable."""
    if analyzer is None:
        return []
    try:
        faces = analyzer.get(frame_bgr)
    except Exception as e:
        log(f"WARN: face detection failed on a frame: {e}")
        return []

    out = []
    for face in faces:
        x1, y1, x2, y2 = (float(v) for v in face.bbox)
        out.append({
            "bbox": {"x": (x1 + x2) / 2, "y": (y1 + y2) / 2, "w": x2 - x1, "h": y2 - y1},
            "confidence": float(face.det_score),
            "embedding": [float(v) for v in face.embedding],
        })
    return out


def to_bbox(pred: dict[str, Any]) -> Optional[dict]:
    """Roboflow object-detection predictions use x/y (CENTRE) + width/height."""
    if all(k in pred for k in ("x", "y", "width", "height")):
        return {"x": pred["x"], "y": pred["y"], "w": pred["width"], "h": pred["height"]}
    return None


# --------------------------------------------------------------- server client

def post_sighting(camera_id: str, ts: datetime, kind: str, modality: str,
                  confidence: float, bbox: Optional[dict],
                  plate_text: Optional[str] = None,
                  embedding: Optional[list[float]] = None) -> Optional[dict]:
    payload: dict[str, Any] = {
        "camera_id": camera_id,
        "ts": ts.isoformat(),
        "kind": kind,
        "modality": modality,
        "confidence": confidence,
    }
    if bbox:
        payload["bbox"] = bbox
    if plate_text:
        payload["plate_text"] = plate_text
    if embedding:
        payload["embedding"] = embedding
    try:
        resp = requests.post(f"{SERVER_URL}/v1/sightings", json=payload, timeout=REQUEST_TIMEOUT_S)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        log(f"WARN: POST /v1/sightings failed: {e}")
        return None


def get_entity(entity_id: str) -> Optional[dict]:
    try:
        resp = requests.get(f"{SERVER_URL}/v1/entities/{entity_id}", timeout=REQUEST_TIMEOUT_S)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException:
        return None


def post_alert(camera_id: str, message: str, severity: str, recipient_id: str,
               recipient_type: str, entity_id: Optional[str] = None) -> Optional[dict]:
    payload = {
        "alert_type": "suspicious_activity",
        "recipient_id": recipient_id,
        "recipient_type": recipient_type,
        "message": message,
        "severity": severity,
        "camera_id": camera_id,
    }
    if entity_id:
        payload["entity_id"] = entity_id
    try:
        resp = requests.post(f"{SERVER_URL}/v1/alerts", json=payload, timeout=REQUEST_TIMEOUT_S)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        log(f"WARN: POST /v1/alerts failed: {e}")
        return None


# ------------------------------------------------------------------------- run

def run(video_path: Path, camera_id: str, interval_s: float,
        out_path: Optional[Path], use_faces: bool, dry_run: bool) -> None:
    log(f"video={video_path.name} camera_id={camera_id} interval={interval_s}s "
        f"faces={'on' if use_faces else 'off'} dry_run={dry_run}")

    analyzer = load_face_analyzer() if use_faces else None

    counts = {"plate": 0, "weapon": 0, "face": 0}
    repeats = 0
    alerts_sent = 0
    track: list[dict[str, Any]] = []

    for idx, video_ts, frame in sample_frames(video_path, interval_s):
        wall_ts = datetime.now(timezone.utc)
        height, width = frame.shape[:2]
        frame_detections: list[dict[str, Any]] = []

        # ---- weapons: hard signal, routed immediately, no entity in the way
        weapon_preds = extract_predictions(
            call_detector(WEAPON_SERVICE_URL, frame, f"frame_{idx}.jpg")
        )
        for pred in weapon_preds:
            counts["weapon"] += 1
            confidence = float(pred.get("confidence", 0.0))
            bbox = to_bbox(pred)
            label = pred.get("class") or pred.get("class_name") or "weapon"
            log(f"  t={video_ts:5.1f}s WEAPON {label} conf={confidence:.2f}")
            frame_detections.append({
                "modality": "yolo", "kind": "weapon", "label": str(label),
                "confidence": confidence, "bbox": bbox,
            })
            if dry_run:
                continue
            sighting = post_sighting(camera_id, wall_ts, "weapon", "yolo", confidence, bbox)
            alert = post_alert(
                camera_id=camera_id,
                message=(f"Weapon detected ({label}, {confidence:.0%} confidence) "
                         f"on {camera_id} — routed to private security."),
                severity="critical",
                recipient_id="private_security_demo",
                recipient_type="ops",
                entity_id=(sighting or {}).get("entity_id"),
            )
            if alert:
                alerts_sent += 1
                log(f"    -> CRITICAL alert to private security (id={alert.get('id')})")

        # ---- plates
        plate_result = call_detector(PLATE_SERVICE_URL, frame, f"frame_{idx}.jpg")
        plate_preds = extract_predictions(plate_result)
        # Top-level plate_text list is the workflow's own OCR, index-aligned
        # with predictions — confirmed live. Prefer it over guessing from the
        # prediction dict. The server decides whether it's a plausible plate.
        ocr_texts = (plate_result or {}).get("plate_text") or []

        for i, pred in enumerate(plate_preds):
            counts["plate"] += 1
            raw_text = ocr_texts[i] if i < len(ocr_texts) else None
            confidence = float(pred.get("confidence", 0.0))
            bbox = to_bbox(pred)
            log(f"  t={video_ts:5.1f}s PLATE ocr={raw_text!r} conf={confidence:.2f}")
            frame_detections.append({
                "modality": "plate", "kind": "vehicle", "label": "plate",
                "confidence": confidence, "bbox": bbox, "ocr_raw": raw_text,
            })
            if dry_run:
                continue
            sighting = post_sighting(camera_id, wall_ts, "vehicle", "plate",
                                     confidence, bbox, plate_text=raw_text)
            repeats += _route_entity(sighting, camera_id, "vehicle", video_ts)

        # ---- faces (local)
        for face in detect_faces(analyzer, frame):
            counts["face"] += 1
            log(f"  t={video_ts:5.1f}s FACE det={face['confidence']:.2f} "
                f"box={ _fmt_box(face['bbox']) }")
            frame_detections.append({
                "modality": "face", "kind": "person", "label": "face",
                "confidence": face["confidence"], "bbox": face["bbox"],
            })
            if dry_run:
                continue
            sighting = post_sighting(camera_id, wall_ts, "person", "face",
                                     face["confidence"], face["bbox"],
                                     embedding=face["embedding"])
            repeats += _route_entity(sighting, camera_id, "person", video_ts)

        if frame_detections:
            track.append({
                "t": round(video_ts, 2),
                "frame": idx,
                "width": width,
                "height": height,
                "detections": frame_detections,
            })

    log(f"Done. plates={counts['plate']} weapons={counts['weapon']} faces={counts['face']} "
        f"| repeat-entity routings={repeats} alerts={alerts_sent}")

    if out_path:
        payload = {
            "video": video_path.name,
            "camera_id": camera_id,
            "interval_s": interval_s,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "counts": counts,
            "frames": track,
        }
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        log(f"Detection track written to {out_path} ({len(track)} frames with detections)")


def _fmt_box(bbox: Optional[dict]) -> str:
    if not bbox:
        return "-"
    return f"{bbox['w']:.0f}x{bbox['h']:.0f}"


def _route_entity(sighting: Optional[dict], camera_id: str, kind: str, video_ts: float) -> int:
    """
    Route a resolved entity. Returns 1 if this was a repeat sighting worth
    routing, else 0.

    Only repeats route onward: a first-ever sighting is one data point, and
    alerting on it is how you train an operator to ignore the system.
    """
    if not sighting:
        return 0
    entity_id = sighting.get("entity_id")
    if not entity_id:
        return 0

    entity = get_entity(entity_id) or {}
    count = entity.get("sighting_count", 0)
    state = entity.get("state", "observed")
    log(f"    -> entity {entity_id} count={count} state={state}")

    if count is None or count <= 1:
        return 0

    noun = "vehicle" if kind == "vehicle" else "person"
    post_alert(
        camera_id=camera_id,
        message=(f"Repeat {noun} sighting on {camera_id} "
                 f"(entity {entity_id}, seen {count}x, state={state})."),
        severity="warning" if state != "flagged" else "critical",
        recipient_id="private_security_demo",
        recipient_type="ops",
        entity_id=entity_id,
    )
    return 1


def main() -> None:
    parser = argparse.ArgumentParser(description="BEACON vision-lens analyzer")
    parser.add_argument("video", type=Path, help="Path to the video file")
    parser.add_argument("--camera-id", default="cam_lens_demo")
    parser.add_argument("--interval", type=float, default=2.0,
                        help="Seconds of video between sampled frames")
    parser.add_argument("--out", type=Path, default=None,
                        help="Write a per-timestamp detection track here for UI replay")
    parser.add_argument("--no-faces", action="store_true",
                        help="Skip face detection (faster; plates+weapons only)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Detect and write --out, but POST nothing to the server")
    args = parser.parse_args()

    if not args.video.exists():
        log(f"ERROR: video not found: {args.video}")
        sys.exit(1)

    run(args.video, args.camera_id, args.interval, args.out,
        use_faces=not args.no_faces, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
