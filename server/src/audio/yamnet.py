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

#: Sounds that count as a gunshot or explosion. Covered separately because a
#: gunshot and a glass break are both impact transients and a single competing
#: list would let one suppress the other. They run independently and the
#: loudest positive verdict wins.
GUNSHOT_LABELS = ("Gunshot, gunfire", "Machine gun", "Artillery fire", "Explosion")

#: The everyday sounds a home mic actually produces, which must be able to
#: outvote glass. Speech and its relatives lead the list because speech is the
#: false positive this module was written to kill; the rest are the other things
#: that trip a transient gate (a slammed door, cutlery, typing, a passing car).
#: Gunshot is NOT in this list — a simultaneous glass-and-gunshot event should
#: not be suppressed by its own co-label.
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

#: And it must beat the best competing sound by this factor.
GLASS_MARGIN = 1.5

#: Gunshot floor. Gunshot, gunfire is one of YAMNet's cleaner classes — it
#: doesn't spread across several labels the way glass does, so the floor can be
#: lower and the margin tighter without letting false positives through.
GUNSHOT_FLOOR = 0.10
GUNSHOT_MARGIN = 1.5


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
    GUNSHOT = "gunshot"
    OTHER = "other"


def _score_event(
    scores: np.ndarray,
    event_idx: list[int],
    competing_idx: list[int],
    floor: float,
    margin: float,
) -> tuple[str, float, bool, bool, str, float]:
    """Score one event type against the competing list. Returns
    (best_label, best_score, clears_floor, beats_competing, competing_label, competing_score).
    """
    event_scores = {_labels()[i]: float(scores[i]) for i in event_idx}
    best_label, best_score = max(event_scores.items(), key=lambda kv: kv[1])

    competing = {_labels()[i]: float(scores[i]) for i in competing_idx}
    best_comp_label, best_comp = (
        max(competing.items(), key=lambda kv: kv[1]) if competing else ("none", 0.0)
    )
    return (best_label, best_score,
            best_score >= floor, best_score > best_comp * margin,
            best_comp_label, best_comp)


def decide(
    scores: np.ndarray,
    glass_idx: list[int],
    competing_idx: list[int],
    floor: float = GLASS_FLOOR,
    margin: float = GLASS_MARGIN,
    gunshot_idx: Optional[list[int]] = None,
    gunshot_floor: float = GUNSHOT_FLOOR,
    gunshot_margin: float = GUNSHOT_MARGIN,
) -> dict:
    """Turns a 521-class score vector into a verdict.

    Checks glass and gunshot independently. Each must clear its own floor and
    beat the everyday competing list by its own margin. The final verdict is
    whichever positive event has the higher peak score, so a 0.25 gunshot
    won't be suppressed by a co-occurring 0.09 glass signal.
    """
    (g_label, g_score, g_floor, g_margin,
     comp_label, comp_score) = _score_event(scores, glass_idx, competing_idx, floor, margin)

    is_glass = g_floor and g_margin

    gunshot_result: Optional[dict] = None
    is_gunshot = False
    if gunshot_idx:
        (gs_label, gs_score, gs_floor, gs_margin,
         gs_comp_label, gs_comp_score) = _score_event(
            scores, gunshot_idx, competing_idx, gunshot_floor, gunshot_margin)
        is_gunshot = gs_floor and gs_margin
        gunshot_result = {
            "gunshot_label": gs_label,
            "gunshot_score": round(gs_score, 4),
            "gunshot_clears_floor": gs_floor,
            "gunshot_beats_competing": gs_margin,
        }

    # When both fire, the higher-scoring event wins the primary verdict.
    if is_glass and is_gunshot and gunshot_result:
        gs_score_val = gunshot_result["gunshot_score"]
        verdict = Verdict.GUNSHOT if gs_score_val > g_score else Verdict.GLASS
    elif is_gunshot:
        verdict = Verdict.GUNSHOT
    elif is_glass:
        verdict = Verdict.GLASS
    else:
        verdict = Verdict.OTHER

    top_idx = np.argsort(scores)[::-1][:5]
    result: dict = {
        "verdict": verdict,
        "glass_label": g_label,
        "glass_score": round(g_score, 4),
        "competing_label": comp_label,
        "competing_score": round(comp_score, 4),
        "clears_floor": g_floor,
        "beats_competing": g_margin,
        "top": [
            {"label": _labels()[int(i)], "score": round(float(scores[int(i)]), 4)}
            for i in top_idx
        ],
    }
    if gunshot_result:
        result.update(gunshot_result)
    return result


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

    return decide(
        scores,
        glass_idx=resolve_indices(GLASS_LABELS),
        competing_idx=resolve_indices(COMPETING_LABELS),
        gunshot_idx=resolve_indices(GUNSHOT_LABELS),
    )
