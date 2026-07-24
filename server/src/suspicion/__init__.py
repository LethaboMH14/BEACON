"""Suspicion scoring — F1–F6 log-odds fusion + conflict gate."""
from .scorer import score_entity, SuspicionResult, CANDIDATE_THRESHOLD

__all__ = ["score_entity", "SuspicionResult", "CANDIDATE_THRESHOLD"]
