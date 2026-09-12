"""
Backward-compatible re-exports for schema models.
"""
from .schema import (
    BoundingBox,
    ImageProvenance,
    GroundingAnchor,
    EntitiesDetected,
    PipelineResult,
)

__all__ = [
    "BoundingBox",
    "ImageProvenance",
    "GroundingAnchor",
    "EntitiesDetected",
    "PipelineResult",
]
