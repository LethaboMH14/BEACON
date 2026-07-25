"""
Local plate OCR + the gate that decides whether a read may become an identity.

WHY THIS REPLACED THE WORKFLOW OCR. The Roboflow workflow's OCR stage is LLM-backed.
On a 1080p SA hijacking clip it returned, for eight detected plates:

    '```markdown\\n\\n```'  '1234567890'  '1000000000000'
    'CASE 2000'             'BUSINESS'    '1'  '6'  '0000'

Two structural faults: it emitted its own markdown fencing instead of a reading, and
it read words off the news chyron as plates. Neither is a resolution problem — they
are the failure modes of an open-vocabulary model asked a closed-vocabulary question.

A purpose-built plate recogniser (fast-plate-ocr, `cct-s-v2-global`, ~5 MB ONNX, CPU)
cannot emit either: its output alphabet is plate characters and nothing else. Running
locally also removes a network hop and an API key from the hot path.

WHAT MEASUREMENT ACTUALLY SHOWED — and it is not "better reads". Re-run over the same
eight crops, the local model returned empty for four and plate-shaped junk for the
other four: 'W444', '00314247', '444411', '1W4114'. That junk is *more* dangerous than
the workflow's, because `plate_text.py` cannot reject it — '00314247' has the exact
shape of a real registration.

What saves it is per-character confidence, which the LLM stage never exposed. On all
four junk reads the weakest character scored 0.156-0.287. So the gate below is what
does the real work; swapping the model is what made the gate *possible*.

HONEST LIMIT: this sample contains no correctly-read plates, because none of the eight
plates in that footage are legible at 10-17 px character height. So MIN_CHAR_PROB is
validated as a *junk suppressor* (4 of 4 rejected) and NOT as a true-positive filter —
nothing here shows what a correct read scores. Treat it as provisional until measured
against footage containing plates a human can actually read. No read rate, precision
or accuracy figure may be quoted from this module today.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

# Below this the crop cannot carry legible characters at all, so don't spend the
# inference. Deliberately loose: the confidence gate is the discriminating one, and
# a geometry gate tight enough to matter would also drop legible angled plates.
MIN_CROP_W = 40
MIN_CROP_H = 12

# Weakest character in the read must clear this. Set with margin above the 0.287
# worst-case observed on known-junk reads. See the honest limit in the module
# docstring: this is a suppression threshold, not a calibrated operating point.
MIN_CHAR_PROB = 0.50

MODEL_NAME = "cct-s-v2-global-model"

# Reasons a read was refused. Recorded rather than discarded so OCR quality stays
# measurable after the fact — the previous pipeline stored None and lost the evidence.
REASON_ACCEPTED = "accepted"
REASON_CROP_TOO_SMALL = "crop_too_small"
REASON_EMPTY_READ = "empty_read"
REASON_LOW_CHAR_CONFIDENCE = "low_char_confidence"
REASON_NO_MODEL = "no_model"


@dataclass(frozen=True)
class PlateRead:
    """
    Outcome of one attempted read. `text` is None unless `reason == 'accepted'`;
    everything else is kept for audit even when the read was refused.
    """
    text: Optional[str]
    raw_text: Optional[str]
    min_char_prob: Optional[float]
    mean_char_prob: Optional[float]
    reason: str

    @property
    def accepted(self) -> bool:
        return self.reason == REASON_ACCEPTED


def crop_is_large_enough(width: float, height: float) -> bool:
    """Cheap pre-filter — is it even worth running the model on this crop?"""
    return width >= MIN_CROP_W and height >= MIN_CROP_H


def gate_read(
    raw_text: Optional[str],
    char_probs: Optional[Any],
    width: float,
    height: float,
) -> PlateRead:
    """
    The decision rule, kept pure so it can be tested without the ONNX model.

    `char_probs` has one slot per output position (10 for this model), of which the
    first len(text) align with the returned characters — the trailing slots are
    padding and score high precisely because the model is confident they're padding.
    Taking the min over all ten would therefore read a blank plate as a confident one.
    """
    if not crop_is_large_enough(width, height):
        return PlateRead(None, raw_text, None, None, REASON_CROP_TOO_SMALL)

    text = (raw_text or "").strip()
    if not text:
        return PlateRead(None, raw_text, None, None, REASON_EMPTY_READ)

    probs = [float(p) for p in (char_probs or [])][: len(text)]
    if not probs:
        # Model gave characters but no confidence — refuse rather than trust it blind.
        return PlateRead(None, raw_text, None, None, REASON_LOW_CHAR_CONFIDENCE)

    weakest = min(probs)
    mean = sum(probs) / len(probs)
    if weakest < MIN_CHAR_PROB:
        return PlateRead(None, raw_text, weakest, mean, REASON_LOW_CHAR_CONFIDENCE)

    return PlateRead(text.upper(), raw_text, weakest, mean, REASON_ACCEPTED)


_recognizer: Any = None
_recognizer_tried = False


def load_recognizer() -> Any:
    """
    Lazy-load the ONNX recogniser. Returns None if unavailable rather than raising —
    same contract as the face analyzer, so a missing optional dependency degrades the
    pipeline to "plates detected, none read" instead of killing the run.
    """
    global _recognizer, _recognizer_tried
    if _recognizer_tried:
        return _recognizer
    _recognizer_tried = True
    try:
        from fast_plate_ocr import LicensePlateRecognizer

        _recognizer = LicensePlateRecognizer(MODEL_NAME, device="cpu")
    except Exception as exc:  # noqa: BLE001 - optional dependency, any failure is non-fatal
        print(f"[plate_ocr] recogniser unavailable ({exc}); plates will not be read")
        _recognizer = None
    return _recognizer


def read_plate(crop_bgr: Any) -> PlateRead:
    """
    Read one plate crop (OpenCV BGR, as cropped from the source frame).

    The model wants RGB; passing BGR silently degrades it rather than erroring, which
    is exactly the kind of bug that would look like "OCR is just bad".
    """
    if crop_bgr is None or getattr(crop_bgr, "size", 0) == 0:
        return PlateRead(None, None, None, None, REASON_CROP_TOO_SMALL)

    height, width = crop_bgr.shape[:2]
    if not crop_is_large_enough(width, height):
        return PlateRead(None, None, None, None, REASON_CROP_TOO_SMALL)

    recognizer = load_recognizer()
    if recognizer is None:
        return PlateRead(None, None, None, None, REASON_NO_MODEL)

    import cv2

    rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
    prediction = recognizer.run(rgb, return_confidence=True)[0]
    probs = prediction.char_probs
    flat = [float(p) for p in (probs.ravel() if hasattr(probs, "ravel") else probs or [])]
    return gate_read(prediction.plate, flat, width, height)
