"""
Pydantic Schemas for Image Pipeline.
Zero-bloat semantic visual grounding contracts replacing numeric 2D bounding boxes.
"""
from typing import List, Optional, Tuple, Dict, Any
from pydantic import BaseModel, Field


class BoundingBox(BaseModel):
    """
    Normalized 2D bounding box representing coordinates as percentages (0.0 to 100.0%).
    Ensures seamless responsive scaling across all viewports and image aspect ratios.
    """
    x: float = Field(..., description="Left coordinate as percentage (0.0 - 100.0)")
    y: float = Field(..., description="Top coordinate as percentage (0.0 - 100.0)")
    width: float = Field(..., description="Width as percentage (0.0 - 100.0)")
    height: float = Field(..., description="Height as percentage (0.0 - 100.0)")
    text: Optional[str] = Field(default=None, description="Optional text enclosed within this bounding box")


class ImageProvenance(BaseModel):
    """
    Provenance metadata attributing extracted intelligence directly to the source image file.
    """
    source_image_name: str = Field(..., description="Name of the source diagram/image file")
    source_file_size_kb: float = Field(..., description="File size in kilobytes")
    total_extracted_nodes: int = Field(..., description="Total visual semantic nodes identified")
    extraction_timestamp: str = Field(..., description="UTC ISO 8601 timestamp of extraction")
    grounding_score_percent: float = Field(default=98.5, description="Attribution / grounding confidence percentage")
    resolution: Optional[Tuple[int, int]] = Field(default=None, description="Image dimensions (width, height)")
    total_detected_boxes: Optional[int] = Field(default=0, description="Total OCR bounding boxes detected on the image")


class GroundingAnchor(BaseModel):
    """
    Semantic visual anchor attributing extracted text to its relative position and exact 2D bounding box in the image.
    """
    id: str = Field(..., description="Unique citation key, e.g. 'src-1', 'img-1'")
    visual_anchor: str = Field(..., description="Visual position/origin in image (e.g. 'Top-Left', 'Central Hub')")
    extracted_verbatim: str = Field(..., description="Exact verbatim text read directly from the image node")
    category: str = Field(default="CORE_CONCEPT", description="Entity category: CORE_CONCEPT, BENEFIT, VULNERABILITY, THREAT_ACTOR, ACTION, TARGET_NODE, etc.")
    confidence: float = Field(default=0.95, ge=0.0, le=1.0, description="Extraction confidence score")
    bbox: Optional[BoundingBox] = Field(default=None, description="Normalized 2D bounding box coordinates (0-100%)")
    page_number: Optional[int] = Field(default=None, description="Page number if extracted from a visual PDF document")
    image_url: Optional[str] = Field(default=None, description="Direct URL/path to inspect the image artifact")
    all_boxes: Optional[List[Dict[str, Any]]] = Field(default=None, description="All OCR detected text boxes on the same canvas")


class EntitiesDetected(BaseModel):
    """
    Structured security entities identified in the visual diagram.
    """
    cves: List[str] = Field(default_factory=list, description="Extracted CVE identifiers")
    actors: List[str] = Field(default_factory=list, description="Identified threat actors / adversary groups")
    targets: List[str] = Field(default_factory=list, description="Target nodes, systems, or assets")


class PipelineResult(BaseModel):
    """
    The complete output contract for the image extraction pipeline.
    """
    metadata: ImageProvenance = Field(..., description="Image provenance and grounding metadata")
    title: str = Field(default="Cybersecurity Diagram Advisory", description="Inferred or extracted title of the diagram")
    summary: str = Field(..., description="Overview / narrative summary of the diagram")
    extracted_text_raw: str = Field(..., description="Complete verbatim raw text extracted from the image")
    grounding_sources: List[GroundingAnchor] = Field(..., description="List of visual grounding anchors with citation IDs")
    markdown_output: str = Field(..., description="Formatted markdown advisory with inline [^src-X] citations and provenance table")
    entities_detected: EntitiesDetected = Field(default_factory=EntitiesDetected, description="Detected security entities")
    execution_time_ms: int = Field(..., description="Total end-to-end execution time in milliseconds")
    mode: str = Field(default="live", description="Execution mode ('live' or 'mock')")
    model: str = Field(default="gemini-2.5-flash-lite", description="Underlying model identifier")
    all_boxes: Optional[List[Dict[str, Any]]] = Field(default_factory=list, description="Complete set of detected OCR bounding boxes")

    @property
    def anchors(self) -> List[GroundingAnchor]:
        """Convenience property for grounding sources."""
        return self.grounding_sources

