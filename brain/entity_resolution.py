"""
BEACON brain/ — entity resolution (docs/01 §3).

Answers "is this the same car/person we've seen before?" for plate-bearing
sightings. G2 scope: plates only (confusion-aware match). Face/vehicle-embedding
cosine matching is the same shape (compare against docs/01 §3) but needs
ArcFace/embedding infra from vision/ Tier 2 — not built yet, so not faked here.

Method: normalized Levenshtein edit distance, but character substitutions in
the CONFUSION_PAIRS set cost 0.25 instead of 1.0 — an OCR reading "0" where
the plate says "O" is not a different car (Flock's 0-vs-O false-stop problem,
docs/01 §3). Match quality is 1 - (cost / max(len_a, len_b)), always in [0,1]
and always carried alongside the match — never silently exact-matched.
"""
from __future__ import annotations

MATCH_THRESHOLD = 0.80

CONFUSION_PAIRS = {
    frozenset({"0", "O"}),
    frozenset({"1", "I"}),
    frozenset({"8", "B"}),
    frozenset({"5", "S"}),
}


def _sub_cost(a: str, b: str) -> float:
    if a == b:
        return 0.0
    if frozenset({a, b}) in CONFUSION_PAIRS:
        return 0.25
    return 1.0


def confusion_aware_distance(plate_a: str, plate_b: str) -> float:
    """Levenshtein distance with confusion-aware substitution cost."""
    a, b = plate_a.upper(), plate_b.upper()
    n, m = len(a), len(b)
    if n == 0:
        return float(m)
    if m == 0:
        return float(n)

    prev = list(range(m + 1))
    for i in range(1, n + 1):
        curr = [float(i)] + [0.0] * m
        for j in range(1, m + 1):
            curr[j] = min(
                prev[j] + 1,                              # deletion
                curr[j - 1] + 1,                          # insertion
                prev[j - 1] + _sub_cost(a[i - 1], b[j - 1]),  # substitution
            )
        prev = curr
    return prev[m]


def match_quality(plate_a: str, plate_b: str) -> float:
    """1.0 = identical, 0.0 = no resemblance. Always defined, never None."""
    longest = max(len(plate_a), len(plate_b))
    if longest == 0:
        return 1.0
    dist = confusion_aware_distance(plate_a, plate_b)
    return max(0.0, 1.0 - dist / longest)


def resolve_plate_entity(plate_text: str, known_plates: dict[str, str]) -> tuple[str | None, float]:
    """
    known_plates: {entity_id: plate_text} for existing entities.
    Returns (best_entity_id_or_None, quality). Caller creates a new entity
    when entity_id is None or quality < MATCH_THRESHOLD.
    """
    best_id: str | None = None
    best_quality = 0.0
    for entity_id, known_plate in known_plates.items():
        quality = match_quality(plate_text, known_plate)
        if quality > best_quality:
            best_quality = quality
            best_id = entity_id

    if best_id is not None and best_quality >= MATCH_THRESHOLD:
        return best_id, best_quality
    return None, best_quality
