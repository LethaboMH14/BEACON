"""
YAMNet audio event classification — the trained-classifier half of the Home
Guard detector.

WHY THIS EXISTS
The browser-side detector (dashboard/app/src/member/audio/glassBreak.ts) is a
transient detector: sudden, loud, high-frequency. That shape is real, but it is
not specific to glass, and the failure it produces in practice is speech.
Fricatives — the s, sh, t and f sounds — are sharp broadband bursts with most
of their energy above 3 kHz, so they satisfy every condition a frequency
heuristic can check. No amount of threshold tuning separates them from glass,
because on those three axes they genuinely look the same.

Telling them apart needs a model that learned what glass sounds like. YAMNet
(vision/assets/models/yamnet.tflite, 521 AudioSet classes) already exists in
this repo and is reused unchanged. The browser detector is demoted from alarm
to *gate*: it decides when to spend an inference, and this decides what the
sound was.

THE DECISION RULE, AND WHY IT IS A MARGIN AND NOT A THRESHOLD
An absolute threshold on the glass score is not enough. Speech does not push
the glass score up; it pushes the *speech* score up, and a permissive glass
threshold will still admit a frame where glass scored 0.15 and speech scored
0.95. So the rule is comparative: glass must clear a floor AND beat the best
competing everyday sound by a margin. When you talk, speech wins by an order of
magnitude and no glass verdict is possible regardless of what the gate thought.

CLASS INDICES ARE READ FROM THE MODEL, NOT HARDCODED
The label list is embedded in the .tflite (it is a zip containing
yamnet_label_list.txt), so indices are resolved by name at load time. This
matters: the hand-written indices previously in models.json were wrong — 195
and 198 were mapped to "glass_break" but are in fact "Bell" and "Bicycle bell".
Resolving by name makes that class of error impossible rather than merely fixed.

PRIVACY
The posted audio window is classified and discarded — never written to disk,
never attached to an incident. Only the derived label and score persist, which
is the same rule vision/ follows for frames.
"""
from __future__ import annotations

import logging
import zipfile
from functools import lru_cache
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

MODEL_PATH = (
    Path(__file__).resolve().parents[3] / "vision" / "assets" / "models" / "yamnet.tflite"
)

#: YAMNet's input is a fixed 0.975 s of 16 kHz mono float32.
SAMPLE_RATE = 16_000
INPUT_SAMPLES = 15_600

#: Sounds that count as breaking glass. Names, not indices — see module docstring.
GLASS_LABELS = ("Glass", "Shatter", "Smash, crash", "Breaking")

#: The everyday sounds a home mic actually produces, which must be able to
#: outvote glass. Speech and its relatives lead the list because speech is the
#: false positive this module was written to kill; the rest are the other things
#: that trip a transient gate (a slammed door, cutlery, typing, a passing car).
COMPETING_LABELS = (
    "Speech", "Child speech, kid speaking", "Conversation", "Narration, monologue",
    "Speech synthesizer", "Hubbub, speech noise, speech babble", "Babbling",
    "Shout", "Yell", "Screaming", "Children shouting", "Laughter", "Cough",
    "Singing", "Music", "Musical instrument", "Television", "Radio",
    "Slam", "Knock", "Door", "Tap", "Thump, thud", "Clapping", "Typing",
    "Dishes, pots, and pans", "Cutlery, silverware",
    "Vehicle", "Car", "Car passing by", "Engine", "Wind", "Wind noise (microphone)",
    "Rain", "Water", "Silence",
)

#: Glass must reach this before a verdict is even considered. Deliberately not
#: high: YAMNet spreads probability across Glass/Shatter/Breaking for one event,
#: so no single class scores like a confident single-label classifier would.
GLASS_FLOOR = 0.08

#: And it must beat the best competing sound by this factor. This is the part
#: that rejects speech, and the number to move if it is still wrong in the room.
GLASS_MARGIN = 1.5


class ClassifierUnavailable(RuntimeError):
    """Raised when the model or its runtime is not usable on this host."""


@lru_cache(maxsize=1)
def _labels() -> list[str]:
    """Label list extracted from the model file's embedded metadata."""
    with zipfile.ZipFile(MODEL_PATH) as z:
        return z.read("yamnet_label_list.txt").decode().splitlines()


@lru_cache(maxsize=1)
def _index_of() -> dict[str, int]:
    return {label: i for i, label in enumerate(_labels())}


def resolve_indices(names: tuple[str, ...]) -> list[int]:
    """Maps label names to indices, skipping any this model build lacks.

    Skipping rather than raising is deliberate: a missing competitor should
    weaken the rejection slightly, not take the whole detector offline.
    """
    idx = _index_of()
    missing = [n for n in names if n not in idx]
    if missing:
        logger.warning("yamnet: labels not in this model, ignored: %s", missing)
    return [idx[n] for n in names if n in idx]


class Verdict:
    """Named for readability at the call site; carries no behaviour."""

    GLASS = "glass_break"
    OTHER = "other"


def decide(
    scores: np.ndarray,
    glass_idx: list[int],
    competing_idx: list[int],
    floor: float = GLASS_FLOOR,
    margin: float = GLASS_MARGIN,
) -> dict:
    """Turns a 521-class score vector into a verdict.

    Separated from inference so it can be tested against constructed score
    vectors — the speech-rejection behaviour is the whole point of this module
    and must be pinned by tests, not just observed in a room.
    """
    glass_scores = {_labels()[i]: float(scores[i]) for i in glass_idx}
    best_glass_label, best_glass = max(glass_scores.items(), key=lambda kv: kv[1])

    competing = {_labels()[i]: float(scores[i]) for i in competing_idx}
    best_competing_label, best_competing = (
        max(competing.items(), key=lambda kv: kv[1]) if competing else ("none", 0.0)
    )

    clears_floor = best_glass >= floor
    beats_competing = best_glass > best_competing * margin
    is_glass = clears_floor and beats_competing

    # The whole top-5 goes back to the client so a wrong call is diagnosable —
    # "it heard Speech at 0.91" is actionable; "not glass" is not.
    top_idx = np.argsort(scores)[::-1][:5]
    return {
        "verdict": Verdict.GLASS if is_glass else Verdict.OTHER,
        "glass_label": best_glass_label,
        "glass_score": round(best_glass, 4),
        "competing_label": best_competing_label,
        "competing_score": round(best_competing, 4),
        "clears_floor": clears_floor,
        "beats_competing": beats_competing,
        "top": [
            {"label": _labels()[int(i)], "score": round(float(scores[int(i)]), 4)}
            for i in top_idx
        ],
    }


@lru_cache(maxsize=1)
def _interpreter():
    if not MODEL_PATH.exists():
        raise ClassifierUnavailable(f"model not found at {MODEL_PATH}")
    try:
        from ai_edge_litert.interpreter import Interpreter
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise ClassifierUnavailable(f"litert runtime unavailable: {exc}") from exc

    interp = Interpreter(model_path=str(MODEL_PATH))
    interp.allocate_tensors()
    return interp


def classify(waveform: np.ndarray) -> dict:
    """Runs YAMNet on one 16 kHz mono window and returns `decide()`'s verdict.

    Shorter windows are zero-padded and longer ones truncated, because YAMNet's
    input tensor is a fixed size — a client whose sample rate divided unevenly
    should still get an answer rather than a 422.
    """
    interp = _interpreter()
    buf = np.zeros(INPUT_SAMPLES, dtype=np.float32)
    n = min(len(waveform), INPUT_SAMPLES)
    buf[:n] = waveform[:n].astype(np.float32)

    interp.set_tensor(interp.get_input_details()[0]["index"], buf)
    interp.invoke()
    scores = interp.get_tensor(interp.get_output_details()[0]["index"])[0]

    return decide(scores, resolve_indices(GLASS_LABELS), resolve_indices(COMPETING_LABELS))
