"""
Face-embedding entity matching — the face-modality counterpart to
entity_resolution.py's confusion-aware plate matching.

Method: cosine similarity between L2-normalized 512-d face embeddings
(InsightFace `buffalo_l`, an ArcFace-family model — see vision/face_backend/).
A new face sighting resolves to an existing Entity when its similarity to any
embedding already stored for that entity is >= MATCH_THRESHOLD. Max-over-
embeddings rather than centroid: a person's stored views vary by pose and
lighting, and averaging them blurs exactly the detail that distinguishes
people. Cheaper to keep several real views than one smeared average.

HONESTY BOUNDARY (docs/06 honesty ledger, same discipline as forecast.py):
MATCH_THRESHOLD is NOT calibrated — not on South African faces, not on this
demo's cameras, not on any held-out set. It is the common default operating
point for ArcFace-family embeddings, nothing more. Until a real ROC/DET curve
is measured on representative footage:
  - never quote a false-match rate for this matcher
  - never present a match as identification of a *named* person; there is no
    identity database here, only "this camera has seen this face before"
  - a match is a lead for human verification, never a conclusion
As with plate matching, the similarity score always travels with the match and
is never silently dropped by callers.

Why this matters more than for plates: a wrong plate match names a car, a wrong
face match accuses a person. The threshold is deliberately on the strict side
of the usual range for that reason.
"""
from __future__ import annotations

import numpy as np

# Cosine similarity in [-1, 1]; same-person pairs for ArcFace-family embeddings
# typically land well above this and different-person pairs well below, but see
# the honesty boundary above — this is a default, not a measurement.
MATCH_THRESHOLD = 0.40

# Expected embedding dimensionality for buffalo_l. Guarded rather than assumed:
# a silently truncated or wrong-model vector would otherwise produce confident
# nonsense similarities.
EMBEDDING_DIM = 512

# Cap on stored views per entity (oldest dropped first by the caller). Keeps the
# match cost bounded and stops one heavily-seen person from dominating the scan.
MAX_EMBEDDINGS_PER_ENTITY = 10


def normalize(vector: list[float] | np.ndarray) -> np.ndarray:
    """
    L2-normalize to a unit vector so a dot product IS the cosine similarity.
    A zero (or near-zero) vector has no direction and therefore no meaningful
    similarity to anything — returned as-is so callers see 0.0 similarity
    rather than a divide-by-zero NaN that would compare falsely.
    """
    arr = np.asarray(vector, dtype=np.float64)
    norm = float(np.linalg.norm(arr))
    if norm < 1e-12:
        return arr
    return arr / norm


def cosine_similarity(a: list[float] | np.ndarray, b: list[float] | np.ndarray) -> float:
    """Cosine similarity of two embeddings, always in [-1, 1]; 0.0 if either is degenerate."""
    va, vb = normalize(a), normalize(b)
    if va.shape != vb.shape or va.size == 0:
        return 0.0
    if float(np.linalg.norm(va)) < 1e-12 or float(np.linalg.norm(vb)) < 1e-12:
        return 0.0
    return float(np.clip(np.dot(va, vb), -1.0, 1.0))


def is_valid_embedding(vector: object) -> bool:
    """
    True only for a finite, non-degenerate vector of the expected width.
    Rejects NaN/inf explicitly: a NaN slipping into the matrix would poison
    every comparison in the vectorized path, not just its own row.
    """
    if not isinstance(vector, (list, tuple, np.ndarray)):
        return False
    arr = np.asarray(vector, dtype=np.float64)
    if arr.ndim != 1 or arr.shape[0] != EMBEDDING_DIM:
        return False
    if not np.all(np.isfinite(arr)):
        return False
    return float(np.linalg.norm(arr)) >= 1e-12


def resolve_face_entity(
    embedding: list[float],
    known_embeddings: dict[str, list[list[float]]],
) -> tuple[str | None, float]:
    """
    known_embeddings: {entity_id: [embedding, ...]} for entities that already
    have at least one stored face view.

    Returns (best_entity_id_or_None, similarity). The caller creates a new
    entity when entity_id is None. Similarity is returned even when it falls
    below threshold so the caller can log/inspect near-misses rather than
    treating "no match" as "no information".

    All candidate vectors are stacked into one matrix and compared in a single
    matmul — a per-candidate Python loop over 512-d vectors is the same N+1
    shape of mistake that made rank_hotspots take 58s (docs/BUILD-LOG.md,
    2026-07-25), just in numpy form.
    """
    if not is_valid_embedding(embedding):
        return None, 0.0
    if not known_embeddings:
        return None, 0.0

    query = normalize(embedding)

    entity_ids: list[str] = []
    rows: list[np.ndarray] = []
    for entity_id, vectors in known_embeddings.items():
        for vector in vectors:
            if not is_valid_embedding(vector):
                continue
            entity_ids.append(entity_id)
            rows.append(normalize(vector))

    if not rows:
        return None, 0.0

    matrix = np.vstack(rows)                      # (n_views, 512), all unit-norm
    similarities = np.clip(matrix @ query, -1.0, 1.0)

    best_index = int(np.argmax(similarities))
    best_similarity = float(similarities[best_index])
    best_entity_id = entity_ids[best_index]

    if best_similarity >= MATCH_THRESHOLD:
        return best_entity_id, best_similarity
    return None, best_similarity
