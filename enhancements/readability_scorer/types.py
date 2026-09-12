"""
Pydantic models for Enhancement 4: Readability & Tone Regression Scoring Engine.
Transmute System (SIH 2026 PS 26154)
"""

from pydantic import BaseModel, ConfigDict
from typing import Dict, Any, Optional


class ReadabilityMetrics(BaseModel):
    model_config = ConfigDict(extra="ignore")
    flesch_reading_ease: float
    flesch_kincaid_grade: float
    gunning_fog: float
    word_count: int
    sentence_count: int
    syllable_count: int
    avg_words_per_sentence: float


class ReadabilityResult(BaseModel):
    model_config = ConfigDict(extra="ignore")
    passed: bool
    target_platform: str
    metrics: ReadabilityMetrics
    verdict: str  # "OPTIMAL", "TOO_DENSE", "TOO_SIMPLE"
    details: str
