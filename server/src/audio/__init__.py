"""Audio event classification (YAMNet)."""
from .yamnet import ClassifierUnavailable, Verdict, classify, decide

__all__ = ["ClassifierUnavailable", "Verdict", "classify", "decide"]
