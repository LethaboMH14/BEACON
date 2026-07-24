import os
import sys

import pytest

from vision.agent import build_sighting_payload

# Validate the payload shape directly against the real server contract
# (SightingCreate), not a hand-copied assumption of it — this is exactly the
# check that would have caught the hex/hex_id + bbox-shape drift that broke
# every live webcam sighting silently (agent.py never surfaced the 422s).
SERVER_SRC = os.path.join(os.path.dirname(__file__), "..", "..", "server")
sys.path.insert(0, SERVER_SRC)
from src.api.sightings import SightingCreate  # noqa: E402


def test_build_sighting_payload_matches_server_contract():
    payload = build_sighting_payload(
        camera_id="cam_1",
        ts="2026-07-25T12:00:00+00:00",
        hex_id="881f1d4a9ffffff",
        kind="person",
        xyxy=(10.4, 20.6, 110.4, 220.6),
        confidence=0.876,
    )

    # Must validate cleanly against the real Pydantic model — not just "look right"
    validated = SightingCreate(**payload)
    assert validated.camera_id == "cam_1"
    assert validated.hex_id == "881f1d4a9ffffff"
    assert validated.modality == "yolo"
    assert validated.kind == "person"
    assert validated.confidence == pytest.approx(0.876)


def test_build_sighting_payload_bbox_shape():
    payload = build_sighting_payload(
        camera_id="cam_1",
        ts="2026-07-25T12:00:00+00:00",
        hex_id="sim_hex_0",
        kind="vehicle",
        xyxy=(0.0, 0.0, 50.0, 30.0),
        confidence=0.5,
    )

    # bbox must be {x, y, w, h}, not [x1, y1, x2, y2] — the exact drift that
    # 422'd silently before post_sighting() checked resp.ok
    assert payload["bbox"] == {"x": 0, "y": 0, "w": 50, "h": 30}
    assert "hex" not in payload
