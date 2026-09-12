"""
Enhancement 2: NLI Cross-Encoder Provenance Verification Engine.
Transmute System (SIH 2026 PS 26154)
"""

from typing import Dict, Any
from .types import CitationVerdict, NLIVerificationResult
from .engine import NLICrossEncoderGuard, _default_guard


def verify_citations(draft_text: str, source_context: str, threshold: float = 0.65) -> Dict[str, Any]:
    """
    Parses sentences with citation markers, runs entailment checks against source_context,
    and returns NLIVerificationResult dict.
    """
    result = _default_guard.verify(draft_text, source_context, threshold=threshold)
    return result.model_dump()


__all__ = [
    "verify_citations",
    "NLICrossEncoderGuard",
    "CitationVerdict",
    "NLIVerificationResult",
]
