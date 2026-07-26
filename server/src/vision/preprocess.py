"""
CLAHE preprocessing for low-light frames.

WHY THIS EXISTS
South African vehicle crime is disproportionately a night-time and load-shedding
problem, and that is exactly when a dashcam or doorbell camera produces frames a
detector cannot use: the plate is a white blob, the person is a silhouette.
CLAHE (Contrast Limited Adaptive Histogram Equalisation) redistributes local
contrast so detail in those regions comes back.

WHY CLAHE AND NOT PLAIN HISTOGRAM EQUALISATION
Global equalisation stretches the whole frame by one curve. A frame with a
bright headlight and a dark number plate has its histogram dominated by the
headlight, so the plate barely moves. CLAHE works on tiles (8x8 here) so the
dark region gets its own curve. The "contrast limited" half matters just as
much: without a clip limit, a near-uniform dark tile has its sensor noise
amplified into visible grain, and a detector will happily find edges in noise.

WHY ON L, NOT ON RGB
Equalising R, G and B independently shifts the colour balance — skin goes green,
a white car goes pink. Converting to LAB and equalising only L changes lightness
and leaves chroma alone, so the frame gets brighter without changing what colour
anything is.

HONESTY BOUNDARY
CLAHE recovers detail that is present but compressed into a few luminance
levels. It cannot recover detail that was never captured — a fully blown-out or
fully black region stays gone. It is a legibility aid, not enhancement in the
television sense, and nothing downstream should describe it as "enhancing" a
plate into readability that was not there. If a plate is unreadable after CLAHE,
the honest answer is still "seen, not read" (ADR-0006/0007).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np

# 8x8 tiles over a 1080p frame is ~240x135 px per tile — small enough that a
# dark number plate gets its own curve, large enough that the tile still has
# enough pixels for its histogram to mean something.
DEFAULT_TILE_GRID = (8, 8)

# Clip limit 2.0 is deliberately conservative. Higher values look more dramatic
# in a side-by-side and produce more false edges for the detector to chew on.
DEFAULT_CLIP_LIMIT = 2.0

# Below this mean luminance (0-255) a frame is treated as low-light. Chosen so
# an ordinary daylight frame is never touched: running CLAHE on a well-exposed
# frame costs time and can *reduce* detector confidence by amplifying noise.
LOW_LIGHT_MEAN_THRESHOLD = 110.0


@dataclass(frozen=True)
class PreprocessResult:
    """What we did and why — surfaced in the UI so the operator isn't guessing."""
    image: np.ndarray
    applied: bool
    reason: str
    mean_luma_before: float
    mean_luma_after: float
    elapsed_ms: float

    @property
    def luma_gain(self) -> float:
        return round(self.mean_luma_after - self.mean_luma_before, 2)


def mean_luma(frame_bgr: np.ndarray) -> float:
    """Mean L channel in LAB space, 0-255. Cheap enough to run on every frame."""
    lab = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2LAB)
    return float(np.mean(lab[:, :, 0]))


def apply_clahe(
    frame_bgr: np.ndarray,
    clip_limit: float = DEFAULT_CLIP_LIMIT,
    tile_grid: tuple[int, int] = DEFAULT_TILE_GRID,
) -> np.ndarray:
    """CLAHE on the L channel only. Returns a new BGR frame; input untouched."""
    lab = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=tile_grid)
    return cv2.cvtColor(cv2.merge((clahe.apply(l), a, b)), cv2.COLOR_LAB2BGR)


def preprocess(
    frame_bgr: np.ndarray,
    *,
    force: Optional[bool] = None,
    threshold: float = LOW_LIGHT_MEAN_THRESHOLD,
    clip_limit: float = DEFAULT_CLIP_LIMIT,
) -> PreprocessResult:
    """
    Apply CLAHE only when the frame is actually dark enough to need it.

    `force=True` applies regardless (the UI's before/after toggle uses this so a
    user can see what it does to a daylight frame); `force=False` skips
    regardless. `None` = decide from the frame, which is the pipeline default.
    """
    t0 = cv2.getTickCount()
    before = mean_luma(frame_bgr)

    if force is True:
        do_it, reason = True, "forced on"
    elif force is False:
        do_it, reason = False, "forced off"
    elif before < threshold:
        do_it, reason = True, f"low light (mean luma {before:.0f} < {threshold:.0f})"
    else:
        # Saying why we skipped matters as much as saying why we ran: an
        # operator seeing "CLAHE: off" needs to know it's a decision, not a bug.
        do_it, reason = False, f"well exposed (mean luma {before:.0f}), left alone"

    out = apply_clahe(frame_bgr, clip_limit=clip_limit) if do_it else frame_bgr
    elapsed_ms = (cv2.getTickCount() - t0) / cv2.getTickFrequency() * 1000.0

    return PreprocessResult(
        image=out,
        applied=do_it,
        reason=reason,
        mean_luma_before=round(before, 2),
        mean_luma_after=round(mean_luma(out) if do_it else before, 2),
        elapsed_ms=round(elapsed_ms, 2),
    )
