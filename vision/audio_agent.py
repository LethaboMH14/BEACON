"""
BEACON audio agent (docs/01 §2.1 "sim_audio (YAMNet port)", §4 F6) — one
process per microphone-equipped node.

YAMNet (assets/models/yamnet.tflite, models.json) already exists and is
validated — it was sourced for the personal-safety app's Tier 2 audio path
and is reused here unchanged, doing a different job: corroborating a camera
sighting (F6), never standing alone as a phone trigger the way it does there.

Pipeline per ~1s audio block:
1. Tier 0 gate: RMS amplitude — skip inference on ordinary quiet/ambient
   sound (cascade-before-compute, same philosophy as vision/agent.py).
2. Tier 2: YAMNet inference (521-class softmax) -> map top class to a
   BEACON cue label via CLASSES_OF_INTEREST (models.json).
3. POST /v1/sightings: {camera_id: node_id, ts, hex_id, kind: label,
   modality: "audio", confidence}. Never posts raw audio — label + confidence
   only (privacy-at-source, same rule as vision/ not persisting raw frames).
   Uses the same sightings contract as vision/agent.py (server/src/) — an
   unknown node_id auto-registers as a sensor on first sighting.

Run: python audio_agent.py --node-id node_1 --server http://localhost:8000
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import requests
import sounddevice as sd
from ai_edge_litert.interpreter import Interpreter

MODEL_PATH = Path(__file__).parent / "assets" / "models" / "yamnet.tflite"
REGISTRY_PATH = Path(__file__).parent / "assets" / "models" / "models.json"

SAMPLE_RATE = 16000
BLOCK_SAMPLES = 15600  # confirmed via interpreter introspection, ~0.975s
RMS_GATE = 0.01  # Tier 0 threshold — silence/ambient noise never reaches YAMNet
CONFIDENCE_MIN = 0.3  # below this, treat as noise, do not emit a cue


def load_classes_of_interest() -> dict[str, str]:
    registry = json.loads(REGISTRY_PATH.read_text())
    model = next(m for m in registry["models"] if m["name"] == "yamnet_audio_classifier")
    return model["classes_of_interest"]


def map_yamnet_class(scores: np.ndarray, classes_of_interest: dict[str, str]) -> tuple[str | None, float]:
    """Top-1 over the classes BEACON cares about, not the full 521 — an
    ambient class winning globally (e.g. 'Speech') shouldn't crowd out a
    lower-ranked but relevant hit."""
    best_label: str | None = None
    best_score = 0.0
    for idx_str, label in classes_of_interest.items():
        score = float(scores[int(idx_str)])
        if score > best_score:
            best_score = score
            best_label = label
    if best_score < CONFIDENCE_MIN:
        return None, best_score
    return best_label, best_score


def post_cue(server: str, cue: dict) -> None:
    try:
        requests.post(f"{server}/v1/sightings", json=cue, timeout=2)
    except requests.RequestException as exc:
        print(f"[audio_agent] cue post failed (server offline?): {exc}")


def run(node_id: str, server: str, hex_id: str) -> None:
    classes_of_interest = load_classes_of_interest()
    interpreter = Interpreter(model_path=str(MODEL_PATH))
    interpreter.allocate_tensors()
    input_index = interpreter.get_input_details()[0]["index"]
    output_index = interpreter.get_output_details()[0]["index"]

    print(f"[audio_agent] {node_id} listening (Tier 0 RMS gate={RMS_GATE}) -> {server}")

    def on_block(indata: np.ndarray, frames: int, time_info, status) -> None:
        waveform = indata[:, 0].astype(np.float32)
        rms = float(np.sqrt(np.mean(waveform**2)))
        if rms < RMS_GATE:
            return  # Tier 0: skip, nothing expensive runs on ambient quiet

        interpreter.set_tensor(input_index, waveform)
        interpreter.invoke()
        scores = interpreter.get_tensor(output_index)[0]

        label, confidence = map_yamnet_class(scores, classes_of_interest)
        if label is None:
            return

        cue = {
            "camera_id": node_id,
            "ts": datetime.now(timezone.utc).isoformat(),
            "hex_id": hex_id,
            "kind": label,
            "modality": "audio",
            "confidence": round(confidence, 3),
        }
        print(f"[audio_agent] cue: {label} ({confidence:.2f})")
        post_cue(server, cue)

    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        blocksize=BLOCK_SAMPLES,
        callback=on_block,
    ):
        while True:
            time.sleep(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node-id", default="node_1")
    parser.add_argument("--server", default="http://localhost:8000")
    parser.add_argument("--hex", default="sim_hex_0", help="H3 hex for this microphone's fixed location")
    args = parser.parse_args()
    run(args.node_id, args.server, args.hex)
