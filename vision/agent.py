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
import uuid
from datetime import datetime, timezone

import cv2
import requests
from ultralytics import YOLO

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


def post_sighting(server: str, sighting: dict) -> None:
    try:
        requests.post(f"{server}/v1/sightings", json=sighting, timeout=1.5)
    except requests.RequestException as exc:
        print(f"[agent] server unreachable, queuing dropped for G0 ({exc})")


def run(camera_id: str, server: str, hex_id: str, source: int | str) -> None:
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
            x1, y1, x2, y2 = [round(v) for v in box.xyxy[0].tolist()]
            sighting = {
                "sighting_id": str(uuid.uuid4()),
                "camera_id": camera_id,
                "ts": now,
                "hex": hex_id,
                "kind": kind,
                "bbox": [x1, y1, x2, y2],
                "confidence": round(float(box.conf[0]), 3),
                # embedding_ref / plate_text / clip_ref arrive at G2 (Tier 2, ArcFace + EasyOCR)
            }
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
