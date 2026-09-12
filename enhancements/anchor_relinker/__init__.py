"""
Enhancement 3: Semantic Anchor Re-Linker (User Edit Protection Engine).
Transmute System (SIH 2026 PS 26154)
"""

from typing import Tuple, List
from .types import RelinkMatch, RelinkResult
from .relinker import SemanticAnchorRelinker, _default_relinker


def relink_citations(
    edited_text: str, original_text: str, threshold: float = 0.55
) -> Tuple[str, List[RelinkMatch]]:
    """
    Re-attaches dropped citation tags onto edited text.
    Returns (relinked_text, matches_list).
    """
    res = _default_relinker.relink(edited_text, original_text, threshold=threshold)
    return res.relinked_text, res.matches


__all__ = [
    "relink_citations",
    "SemanticAnchorRelinker",
    "RelinkMatch",
    "RelinkResult",
]
