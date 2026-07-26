"""
One-off: generate a real detection track for the third Drive clip ("Driving
home") using the server's already-working HostedBackend (server/src/vision/
detectors.py) — same weapon/plate models the rest of the app uses, called
directly rather than through scripts/vision_lens_demo.py's :8001/:8002
workflow services (those need `inference-sdk`, which requires Python <3.13;
this machine runs 3.13, so that path is skipped rather than risked this close
to a demo). Plate OCR text is intentionally left unread here (fast-plate-ocr
is not installed) — plates are still detected and boxed, just not decoded,
same honest "unread" state the UI already handles.

Faces are detected locally via InsightFace (buffalo_l, CPU), same model/
det_size as scripts/vision_lens_demo.py's detect_faces() — installed
separately from the Roboflow inference-sdk path, no Python-version conflict.

Usage: python scripts/generate_drivinghome_track.py <video> --out <track.json>
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parent.parent / "server" / ".env")

from src.vision.detectors import detect_all, make_backend  # noqa: E402

FACE_DET_SIZE = (1024, 1024)


def load_face_analyzer():
    import insightface
    analyzer = insightface.app.FaceAnalysis()
    analyzer.prepare(ctx_id=-1, det_size=FACE_DET_SIZE)
    print(f"[drivinghome] face analyzer ready (buffalo_l, CPU, det_size={FACE_DET_SIZE})")
    return analyzer


def detect_faces(analyzer, frame_bgr) -> list[dict]:
    faces = analyzer.get(frame_bgr)
    out = []
    for face in faces:
        x1, y1, x2, y2 = (float(v) for v in face.bbox)
        out.append({
            "bbox": {"x": (x1 + x2) / 2, "y": (y1 + y2) / 2, "w": x2 - x1, "h": y2 - y1},
            "confidence": float(face.det_score),
        })
    return out


def sample_frames(video_path: Path, interval_s: float):
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    step = max(1, int(round(fps * interval_s)))
    idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % step == 0:
            yield idx, idx / fps, frame
        idx += 1
    cap.release()


async def run(video_path: Path, out_path: Path, interval_s: float) -> None:
    backend = make_backend()
    analyzer = load_face_analyzer()
    print(f"[drivinghome] backend={backend.name} video={video_path.name}")

    counts = {"plate": 0, "plate_read": 0, "weapon": 0, "face": 0}
    track: list[dict] = []

    for idx, ts, frame in sample_frames(video_path, interval_s):
        height, width = frame.shape[:2]
        run_result = await detect_all(frame, backend)
        if run_result.errors:
            print(f"  t={ts:5.1f}s errors: {run_result.errors}")

        frame_detections = []
        for d in run_result.detections:
            if d.kind == "weapon":
                counts["weapon"] += 1
            elif d.kind == "plate":
                counts["plate"] += 1
            print(f"  t={ts:5.1f}s {d.kind.upper()} {d.label} conf={d.confidence:.2f}")
            frame_detections.append({
                "modality": "yolo" if d.kind == "weapon" else "plate",
                "kind": "weapon" if d.kind == "weapon" else "vehicle",
                "label": d.label,
                "confidence": d.confidence,
                "bbox": d.bbox,
                **({"ocr_text": None, "ocr_reason": "local OCR not installed for this run"} if d.kind == "plate" else {}),
            })

        for face in detect_faces(analyzer, frame):
            counts["face"] += 1
            print(f"  t={ts:5.1f}s FACE conf={face['confidence']:.2f}")
            frame_detections.append({
                "modality": "face", "kind": "person", "label": "face",
                "confidence": face["confidence"], "bbox": face["bbox"],
            })

        if frame_detections:
            track.append({"t": round(ts, 2), "frame": idx, "width": width, "height": height, "detections": frame_detections})

    print(f"Done. plates={counts['plate']} weapons={counts['weapon']} faces={counts['face']}")
    out_path.write_text(json.dumps({
        "video": video_path.name,
        "camera_id": "cam_driving_home",
        "interval_s": interval_s,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "counts": counts,
        "frames": track,
    }, indent=2), encoding="utf-8")
    print(f"Wrote {out_path} ({len(track)} frames with detections)")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("video", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--interval", type=float, default=2.0)
    args = parser.parse_args()
    asyncio.run(run(args.video, args.out, args.interval))


if __name__ == "__main__":
    main()
