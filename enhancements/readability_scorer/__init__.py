"""
Enhancement 4: Readability & Tone Regression Scoring Engine.
Transmute System (SIH 2026 PS 26154)

Pure Python linguistic analyzer evaluating Flesch Reading Ease,
Flesch-Kincaid Grade Level, and Gunning Fog for audience compliance.
"""

from .types import ReadabilityMetrics, ReadabilityResult
from .scorer import ReadabilityScorer, score_readability

__all__ = [
    "score_readability",
    "ReadabilityScorer",
    "ReadabilityMetrics",
    "ReadabilityResult",
]
