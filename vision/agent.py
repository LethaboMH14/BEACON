"""
BEACON vision agent (docs/01 §2.1, §5) — one process per camera.
G0: webcam -> YOLOv8n person/vehicle boxes -> POST /v1/sightings.
G2 will add the Tier-1 weapon/plate classes (Sali) and Tier-2 face/plate
crops (embedding_ref, plate_text) — this file stays the single place a
camera's raw frame is touched, per the privacy-at-source rule (CLAUDE.md §4.5).

Run: python agent.py --camera-id cam_1 --server http://localhost:8000
"""
from __future__ import annotations

import argparse
import time
from datetime import datetime, timezone

import cv2
import requests

# Tier 0 gate (CLAUDE.md §4.2): skip inference on a near-static scene.
MOTION_THRESHOLD = 12.0
# Only these YOLO classes are useful sightings at G0 — weapon/plate classes
# land when Sali's fine-tuned weights replace yolov8n.pt (docs/03 §3).
WATCHED_CLASSES = {"person", "car", "truck", "motorcycle", "bicycle"}


def motion_score(prev_gray, gray) -> float:
    if prev_gray is None:
        return MOTION_THRESHOLD + 1
    diff = cv2.absdiff(prev_gray, gray)
    return diff.mean()


def build_sighting_payload(
    camera_id: str,
    ts: str,
    hex_id: str,
    kind: str,
    xyxy: tuple[float, float, float, float],
    confidence: float,
) -> dict:
    """
    Shapes a detection into the exact POST /v1/sightings contract
    (SightingCreate in server/src/api/sightings.py). Pulled out of run()'s
    loop so it's unit-testable against the real schema — the inline version
    once drifted (hex vs hex_id, missing modality, bbox as a list not
    {x,y,w,h}) and 422'd silently since post_sighting only caught network
    errors, not HTTP status.
    """
    x1, y1, x2, y2 = [round(v) for v in xyxy]
    return {
        "camera_id": camera_id,
        "ts": ts,
        "hex_id": hex_id,
        "kind": kind,
        "modality": "yolo",
        "bbox": {"x": x1, "y": y1, "w": x2 - x1, "h": y2 - y1},
        "confidence": round(float(confidence), 3),
        # embedding_ref / plate_text / clip_ref arrive at G2 (Tier 2, ArcFace + EasyOCR)
    }


def post_sighting(server: str, sighting: dict) -> None:
    try:
        resp = requests.post(f"{server}/v1/sightings", json=sighting, timeout=1.5)
        if not resp.ok:
            # A schema mismatch here fails silently otherwise — POST succeeds at the
            # transport level (no RequestException) while the server 422s and drops it.
            print(f"[agent] server rejected sighting {resp.status_code}: {resp.text}")
    except requests.RequestException as exc:
        print(f"[agent] server unreachable, queuing dropped for G0 ({exc})")


def run(camera_id: str, server: str, hex_id: str, source: int | str) -> None:
    # Deferred so importing this module (e.g. to unit-test build_sighting_payload)
    # doesn't require the ultralytics/torch stack to be installed.
    from ultralytics import YOLO

    model = YOLO("yolov8n.pt")
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        raise SystemExit(f"could not open camera source {source!r}")

    prev_gray = None
    print(f"[agent] {camera_id} watching source={source} -> {server}")

    while True:
        ok, frame = cap.read()
        if not ok:
            break

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, (160, 90))
        score = motion_score(prev_gray, gray)
        prev_gray = gray

        if score < MOTION_THRESHOLD:
            continue  # Tier 0: still scene, nothing expensive runs

        results = model.predict(frame, verbose=False, conf=0.4)[0]
        now = datetime.now(timezone.utc).isoformat()

        for box in results.boxes:
            cls_name = model.names[int(box.cls[0])]
            if cls_name not in WATCHED_CLASSES:
                continue

            kind = "person" if cls_name == "person" else "vehicle"
            sighting = build_sighting_payload(
                camera_id=camera_id,
                ts=now,
                hex_id=hex_id,
                kind=kind,
                xyxy=tuple(box.xyxy[0].tolist()),
                confidence=float(box.conf[0]),
            )
            print(f"[agent] sighting {kind} conf={sighting['confidence']} bbox={sighting['bbox']}")
            post_sighting(server, sighting)

        time.sleep(0.05)  # ease demo-laptop CPU; drop once profiled (docs/06 §budgets)

    cap.release()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BEACON vision agent (G0)")
    parser.add_argument("--camera-id", default="cam_1")
    parser.add_argument("--server", default="http://localhost:8000")
    parser.add_argument("--hex", default="sim_hex_0", help="H3 cell this camera covers (real snap lands with docs/02)")
    parser.add_argument("--source", default=0, help="cv2 VideoCapture source: webcam index or RTSP/file path")
    args = parser.parse_args()

    source = args.source
    if isinstance(source, str) and source.isdigit():
        source = int(source)

    run(args.camera_id, args.server, args.hex, source)
